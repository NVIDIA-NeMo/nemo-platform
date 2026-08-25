# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the profiling pipeline: split/partition resolution and envelope assembly."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from nemo_datasets_plugin.profiler.file_source import FileEntry, LocalFileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.pipeline import _peek_files, profile
from nemo_datasets_plugin.profiler.readers.base import FilePreview
from nemo_datasets_plugin.profiler.splits import infer_data_files, resolve_splits
from nemo_platform_plugin.files.dataset_profile import DatasetProfile

FIXED_TIME = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _write_parquet(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _entries(*paths):
    return [FileEntry(path=p, size_bytes=100) for p in paths]


# --- split resolution ----------------------------------------------------------------------------


def test_resolve_splits_infers_canonical_from_sharded_names():
    entries = _entries(
        "train-00000-of-00002.parquet",
        "train-00001-of-00002.parquet",
        "validation-00000-of-00001.parquet",
    )
    splits = {s.name: s for s in resolve_splits(entries)}
    assert set(splits) == {"train", "validation"}
    assert splits["train"].canonical == "train"
    assert splits["validation"].canonical == "validation"
    assert len(splits["train"].entries) == 2


def test_resolve_splits_normalizes_aliases():
    splits = {s.name: s.canonical for s in resolve_splits(_entries("val.jsonl", "dev.jsonl"))}
    assert splits == {"val": "validation", "dev": "validation"}


def test_resolve_splits_does_not_mistake_years_for_shard_numbers():
    # A bare trailing number only reads as a shard when it is zero-padded; otherwise dates and
    # versions were being stripped, e.g. covid-19.jsonl -> a "covid" split.
    assert [s.name for s in resolve_splits(_entries("covid-19.jsonl"))] == ["default"]
    names = {s.name for s in resolve_splits(_entries("train-00000-of-00002.parquet", "data-2024.jsonl"))}
    assert names == {"train", "data-2024"}


def test_resolve_splits_falls_back_to_single_default():
    splits = resolve_splits(_entries("shard-00000.parquet", "shard-00001.parquet"))
    assert len(splits) == 1
    assert splits[0].name == "default"
    assert splits[0].canonical is None
    assert len(splits[0].entries) == 2


# --- data_files glob inference --------------------------------------------------------------------


def _globs(*paths):
    """Infer a glob per split over ``paths``, verifying against the full listing (README included)."""
    data = [e for e in _entries(*paths) if e.path.endswith((".parquet", ".jsonl"))]
    return {s.name: infer_data_files(s.name, s.entries, list(paths)) for s in resolve_splits(data)}


@pytest.mark.parametrize(
    "label,paths,expected",
    [
        (
            "shards in one directory",
            (
                "data/train-00000-of-00002.parquet",
                "data/train-00001-of-00002.parquet",
                "data/test-00000-of-00001.parquet",
            ),
            {"train": "data/train*.parquet", "test": "data/test*.parquet"},
        ),
        (
            "a directory per split",
            ("default/train/0000.parquet", "default/train/0001.parquet", "default/test/0000.parquet"),
            {"train": "default/train/*.parquet", "test": "default/test/*.parquet"},
        ),
        (
            "files at the fileset root",
            ("train.jsonl", "validation.jsonl"),
            {"train": "train*.jsonl", "validation": "validation*.jsonl"},
        ),
        (
            "no split detected: the glob covers the partition",
            ("shard-00000.parquet", "shard-00001.parquet"),
            {"default": "*.parquet"},
        ),
        (
            "mixed formats drop the suffix rather than losing a file",
            ("train-00000-of-00002.parquet", "train-00001-of-00002.jsonl"),
            {"train": "train*"},
        ),
    ],
)
def test_data_files_glob_per_layout(label, paths, expected):
    assert _globs(*paths) == expected, label


def test_data_files_glob_excludes_a_readme_beside_the_shards():
    # `data/*` would sweep the card into the split. The suffix-qualified candidate is what survives
    # verification, and verification runs against every listed file, not just the data ones.
    assert _globs("data/train-00000-of-00001.parquet", "data/README.md") == {"train": "data/train*.parquet"}


def test_data_files_glob_keeps_a_separator_to_beat_a_sibling_split():
    # `train*` would also match train_prefs, so the simple form loses verification and the narrower
    # `train-*` is reached. Both splits still get a pattern; neither over-matches the other.
    assert _globs(
        "train-00000-of-00002.parquet", "train-00001-of-00002.parquet", "train_prefs-00000-of-00001.parquet"
    ) == {"train": "train-*.parquet", "train_prefs": "train_prefs*.parquet"}


def test_data_files_glob_refuses_rather_than_sweep_in_a_non_data_file():
    # Mixed suffixes leave no suffix to qualify with, and an unsplit-named set leaves no stem to
    # anchor on, so the only candidate left is `data/*` -- which would hand a reader the README as
    # if it were a shard. Verification is the whole of what stops that, and None is the answer.
    assert _globs("data/shard-00000.parquet", "data/shard-00001.jsonl", "data/README.md") == {"default": None}


def test_data_files_glob_is_none_when_shards_span_subdirectories():
    # Expressing this needs `**`, whose meaning differs between glob implementations. None is the
    # honest answer; a pattern that selects a different set in the reader than here would not be.
    assert _globs("train/part-a/0000.parquet", "train/part-b/0000.parquet") == {"train": None}


def test_data_files_glob_means_the_same_thing_to_pythons_own_glob(tmp_path):
    """The dialect claim, checked against an independent implementation rather than our matcher.

    A pattern is only worth emitting if a consumer resolves it to the files we said it selects.
    """
    for rel in (
        "data/train-00000-of-00002.parquet",
        "data/train-00001-of-00002.parquet",
        "data/test-00000-of-00001.parquet",
    ):
        _write_parquet(tmp_path / rel, [{"a": 1}])
    (tmp_path / "data" / "README.md").write_text("card")

    for split in profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0].splits:
        resolved = sorted(p.relative_to(tmp_path).as_posix() for p in Path(tmp_path).glob(split.data_files))
        assert len(resolved) == split.num_files, f"{split.name}: {split.data_files} -> {resolved}"
        assert all(name.startswith(f"data/{split.name}") for name in resolved)


# --- the fold ------------------------------------------------------------------------------------


def test_a_parquet_footer_declares_enough_to_fold_without_reading_rows(tmp_path):
    # The footer is what makes a fold possible at all: the schema, so accumulators can exist before
    # the first batch, and the exact row count, so a split can report an exact `num_examples` from a
    # run that never read to the end. A line-delimited file declares neither.
    _write_parquet(tmp_path / "train.parquet", [{"a": i} for i in range(7)])
    (tmp_path / "extra.jsonl").write_text('{"a": 1}\n')
    source = LocalFileSource(tmp_path)

    previews = _peek_files(source, source.list_files())

    assert previews["train.parquet"].num_rows == 7
    assert previews["train.parquet"].arrow_schema is not None
    assert previews["extra.jsonl"] == FilePreview()  # declares nothing, so the partition cannot fold


def test_the_folded_and_materialised_paths_measure_the_same_thing(tmp_path):
    # Parquet declares a schema and is folded batch by batch; jsonl declares none and is
    # materialised. The same rows have to measure the same either way, or the batch size -- an
    # implementation detail no reader of a profile can see -- would be visible in the numbers.
    rows = [{"prompt": f"question {i}", "completion": "answer " * (i % 7 + 1), "score": i % 5} for i in range(200)]
    _write_parquet(tmp_path / "pq" / "train.parquet", rows)
    (tmp_path / "jl").mkdir()
    (tmp_path / "jl" / "train.jsonl").write_text("\n".join(json.dumps(row) for row in rows))

    folded = profile(LocalFileSource(tmp_path / "pq"), created_at=FIXED_TIME).partitions[0]
    materialised = profile(LocalFileSource(tmp_path / "jl"), created_at=FIXED_TIME).partitions[0]

    assert folded.stats == materialised.stats
    assert folded.classification == materialised.classification
    assert [f.model_dump() for f in folded.features] == [f.model_dump() for f in materialised.features]


def test_an_exhaustive_fold_does_not_cost_more_than_a_budgeted_one(tmp_path):
    # The point of the whole exercise: reading every row costs what reading some of them costs, so
    # the budget stops being a memory guard. Same measurements, and `rows_complete` finally true.
    _write_parquet(tmp_path / "train.parquet", [{"t": f"row {i}" * (i % 5 + 1)} for i in range(5000)])

    budgeted = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=500)
    exhaustive = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=None)

    assert budgeted.sampling.rows_scanned == 500
    assert exhaustive.sampling.rows_scanned == 5000
    assert budgeted.partitions[0].rows_complete is False
    assert exhaustive.partitions[0].rows_complete is True
    # Exact where it claims to be exact: the longest row is found by reading all of them.
    assert exhaustive.partitions[0].stats["t"].text.chars.max >= budgeted.partitions[0].stats["t"].text.chars.max


# --- partition grouping --------------------------------------------------------------------------


def test_group_partitions_names_the_root_partition_with_the_empty_prefix():
    # "" is the path prefix root-level files share, and no directory can be named it -- which is what
    # keeps root files distinct from a directory literally called "default".
    assert group_partitions(_entries("train.parquet", "test.parquet")) == [
        ("", _entries("train.parquet", "test.parquet"))
    ]


def test_group_partitions_collapses_single_container_dir():
    # One container directory is still one partition, and it keeps that directory as its name.
    # Reporting "default" here discarded the only thing identifying the partition.
    parts = group_partitions(_entries("data/train.parquet", "data/test.parquet"))
    assert [name for name, _ in parts] == ["data"]


def test_group_partitions_splits_multiple_top_dirs():
    parts = group_partitions(_entries("main/train.parquet", "socratic/train.parquet"))
    assert [name for name, _ in parts] == ["main", "socratic"]


def test_group_partitions_does_not_treat_split_dirs_as_partitions():
    # train/ and test/ are one dataset's splits, not two datasets.
    parts = group_partitions(_entries("train/data.parquet", "test/data.parquet"))
    assert [name for name, _ in parts] == [""]


def test_resolve_splits_reads_the_split_directory():
    # The data/<split>/<shard> layout names every shard the same thing; only the directory carries
    # the split, so reading the stem alone would collapse the dataset into one split.
    splits = {s.name: s for s in resolve_splits(_entries("data/train/0000.parquet", "data/test/0000.parquet"))}
    assert set(splits) == {"train", "test"}
    assert splits["train"].canonical == "train"
    assert splits["test"].canonical == "test"


def test_resolve_splits_prefers_directory_over_stem():
    splits = resolve_splits(_entries("main/train-00000-of-00001.parquet"))
    assert [s.name for s in splits] == ["train"]  # no split dir on the path, so the stem is used


# --- end-to-end profile() ------------------------------------------------------------------------


def test_profile_parquet_dataset_builds_envelope(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"prompt": "a"}, {"prompt": "b"}])
    _write_parquet(tmp_path / "validation-00000-of-00001.parquet", [{"prompt": "c"}])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.profiler_info["name"] == "nemo-dataset-profiler"
    assert len(result.partitions) == 1
    partition = result.partitions[0]
    assert partition.name == ""  # root-level files: the empty path prefix
    assert partition.file_formats == ["parquet"]

    splits = {s.name: s for s in partition.splits}
    assert set(splits) == {"train", "validation"}
    assert splits["train"].canonical == "train"
    assert splits["train"].num_examples == 2
    assert splits["validation"].num_examples == 1
    assert splits["train"].num_files == 1

    # Row schema, stats, and classification are all derived now.
    assert [f.name for f in partition.features] == ["prompt"]
    assert partition.features[0].dtype == "string"
    assert partition.features[0].semantic_role == "prompt"
    assert partition.stats["prompt"].text is not None
    assert partition.classification.dataset_type == "prompt_only"  # a lone prompt column, no target

    # A budgeted run over files that all fit under their share is still a complete scan, which is
    # why the budget and the outcome are separate fields.
    assert partition.rows_complete is True
    assert result.sampling.rows_scanned == result.sampling.rows_present  # exhaustive by default
    assert result.sampling.rows_scanned == 3
    assert result.sampling.rows_present == 3
    assert result.sampling.files_read == result.sampling.files_present == 2


def test_profile_jsonl_dataset_counts_rows_exactly(tmp_path):
    (tmp_path / "train.jsonl").write_text('{"a": 1}\n{"a": 2}\n{"a": 3}\n')
    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    partition = result.partitions[0]
    assert partition.file_formats == ["jsonl"]
    assert partition.splits[0].name == "train"
    assert partition.splits[0].num_examples == 3
    assert result.sampling.rows_scanned == 3


def test_profile_multiple_directories_become_partitions(tmp_path):
    _write_parquet(tmp_path / "main" / "train-00000-of-00001.parquet", [{"q": "1"}])
    _write_parquet(tmp_path / "socratic" / "train-00000-of-00001.parquet", [{"q": "2"}])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert [p.name for p in result.partitions] == ["main", "socratic"]
    assert all(p.file_formats == ["parquet"] for p in result.partitions)


def test_profile_top_level_split_dirs_become_one_partition(tmp_path):
    # train/ + test/ is one dataset with two splits, not two datasets. As separate partitions each
    # would derive its own schema and classification, and the split structure would disappear.
    _write_parquet(tmp_path / "train" / "data.parquet", [{"prompt": "a", "completion": "b"}])
    _write_parquet(tmp_path / "test" / "data.parquet", [{"prompt": "c", "completion": "d"}])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert [p.name for p in result.partitions] == [""]
    splits = {s.name: s for s in result.partitions[0].splits}
    assert set(splits) == {"train", "test"}
    assert splits["train"].canonical == "train"
    assert splits["test"].num_examples == 1


def test_profile_nested_split_dirs_keep_splits_apart(tmp_path):
    # data/<split>/<shard> shards are all named alike, so only the directory distinguishes them.
    # Reading the stem alone pooled train and test into a single "default" split.
    _write_parquet(tmp_path / "data" / "train" / "0000.parquet", [{"prompt": "a"}, {"prompt": "b"}])
    _write_parquet(tmp_path / "data" / "test" / "0000.parquet", [{"prompt": "c"}])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert [p.name for p in result.partitions] == ["data"]  # the container directory, not "default"
    splits = {s.name: s for s in result.partitions[0].splits}
    assert set(splits) == {"train", "test"}
    assert splits["train"].num_examples == 2
    assert splits["test"].num_examples == 1


def test_profile_keeps_a_mixed_format_directory_as_one_partition(tmp_path):
    # A stray .jsonl beside .parquet shards is noise, not a second dataset. Splitting the partition
    # to keep a scalar `file_format` true invented structure that is not in the data *and* renamed
    # the real partition (default -> default:parquet). Format is a per-file fact instead.
    _write_parquet(tmp_path / "data" / "train-00000-of-00001.parquet", [{"prompt": "a"}])
    (tmp_path / "data" / "extra.jsonl").write_text('{"question": "b"}\n{"question": "c"}\n')

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert len(result.partitions) == 1
    partition = result.partitions[0]
    assert partition.name == "data"
    assert partition.file_formats == ["jsonl", "parquet"]
    # Both formats' columns reach features. Trusting the declared parquet schema would have erased
    # `question`, which only the schemaless file witnesses -- the defect the split worked around.
    assert sorted(f.name for f in partition.features) == ["prompt", "question"]
    assert result.sampling.rows_scanned == 3  # 1 parquet + 2 jsonl, each counted once
    assert partition.rows_complete is True


def test_root_files_and_a_directory_named_default_stay_distinct():
    # The collision the empty-string sentinel exists to prevent: a derived label collapsed both to
    # "default", leaving two partitions with one name and no way to reference either.
    parts = group_partitions(_entries("root.parquet", "default/inner.parquet"))
    assert [name for name, _ in parts] == ["", "default"]


def test_an_unrelated_file_does_not_rename_a_partition(tmp_path):
    # Dropping a stray .jsonl into main/ used to turn partition "main" into "main:parquet" -- not
    # renamed, *gone*, so a stored reference resolved to nothing.
    _write_parquet(tmp_path / "main" / "train.parquet", [{"q": "a"}])
    _write_parquet(tmp_path / "socratic" / "train.parquet", [{"q": "b"}])
    before = [p.name for p in profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions]

    (tmp_path / "main" / "notes.jsonl").write_text('{"note": "someone dropped this here"}\n')
    after = [p.name for p in profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions]

    assert before == after == ["main", "socratic"]


def test_profile_unions_columns_across_shards(tmp_path):
    # A column that appears only in a later shard must still reach features/stats. Taking the first
    # shard's schema would drop it entirely.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"prompt": "a", "completion": "b"}])
    _write_parquet(tmp_path / "train-00001-of-00002.parquet", [{"prompt": "c", "completion": "d", "score": 3}])

    partition = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0]

    assert [f.name for f in partition.features] == ["prompt", "completion", "score"]
    assert partition.stats["score"].null_rate == 0.5  # absent in the first shard, and said so


def test_profile_is_invariant_to_shard_order(tmp_path, tmp_path_factory):
    # The same rows must profile the same way regardless of which shard sorts first. First-wins
    # schema selection made this data classify as prompt_completion or scored_response depending
    # purely on filename order.
    narrow = [{"prompt": "a", "completion": "b"}]
    wide = [{"prompt": "c", "completion": "d", "score": 3}]

    forward = tmp_path_factory.mktemp("forward")
    _write_parquet(forward / "train-00000-of-00002.parquet", narrow)
    _write_parquet(forward / "train-00001-of-00002.parquet", wide)

    reverse = tmp_path_factory.mktemp("reverse")
    _write_parquet(reverse / "train-00000-of-00002.parquet", wide)
    _write_parquet(reverse / "train-00001-of-00002.parquet", narrow)

    first = profile(LocalFileSource(forward), created_at=FIXED_TIME).partitions[0]
    second = profile(LocalFileSource(reverse), created_at=FIXED_TIME).partitions[0]

    assert [(f.name, f.dtype) for f in first.features] == [(f.name, f.dtype) for f in second.features]
    assert first.classification.dataset_type == second.classification.dataset_type == "scored_response"


def test_profile_survives_conflicting_shard_schemas(tmp_path):
    # Two shards disagreeing on a column's type has no right answer at the schema level; fall back to
    # inferring from the rows (which widens to json) rather than asserting one shard over the other.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"score": 1}])
    _write_parquet(tmp_path / "train-00001-of-00002.parquet", [{"score": "high"}])

    partition = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0]

    assert [f.name for f in partition.features] == ["score"]
    assert partition.features[0].dtype == "json"  # mixed, and honest about it


def test_an_unreadable_file_says_what_it_actually_is(tmp_path):
    # The payoff for the magic-byte checks, and the reason they cannot live in `peek` alone: `peek`
    # runs first and its failures are discarded, so this message only reaches a FileError because the
    # read path raises it too. Without it both shards report a decode error from inside the parser,
    # which reads like corrupt data rather than a file that was never this format.
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "test-00000-of-00001.parquet").write_bytes(b"<!DOCTYPE html><html>404</html>")
    (tmp_path / "extra.jsonl").write_bytes(b"\x1f\x8b\x08\x00" + b"\x00" * 32)

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    errors = {e.path: e.error for e in result.file_errors}
    assert "not a parquet file" in errors["test-00000-of-00001.parquet"]
    assert "gzip archive" in errors["extra.jsonl"]
    assert result.partitions[0].stats  # and the shard that was fine is still measured


def test_profile_isolates_unreadable_files(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "test-00000-of-00001.parquet").write_bytes(b"not a real parquet file")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    splits = {s.name: s for s in result.partitions[0].splits}
    assert splits["train"].num_examples == 1
    assert splits["test"].num_examples is None  # unreadable -> count unknown, not a crash
    assert [e.path for e in result.file_errors] == ["test-00000-of-00001.parquet"]  # named, with a reason
    assert result.file_errors[0].error
    assert result.partitions[0].rows_complete is False  # a file could not be fully parsed
    assert result.sampling.rows_present is None
    assert result.sampling.files_read == 1  # one file was actually read; the other never opened
    assert result.sampling.files_present == 2  # ...out of two that were there to read


def test_profile_row_budget_bounds_reads_and_says_so(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": i} for i in range(10)])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=4)

    assert result.sampling.rows_scanned == 4
    assert result.partitions[0].rows_complete is False  # 4 of 10 rows is not a full scan
    # The footer knows the total even though the cap stopped the read. Gating this on completeness
    # nulled it exactly when it carried information: "4 of 10" is a ratio, "4 of unknown" is not.
    assert result.sampling.rows_present == 10
    assert result.partitions[0].splits[0].num_examples == 10  # the footer count survives sampling


def test_profile_uncapped_read_is_a_full_scan(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": i} for i in range(10)])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=None)

    assert result.partitions[0].rows_complete is True
    assert result.sampling.rows_scanned == result.sampling.rows_present == 10


def test_profile_cap_larger_than_a_jsonl_file_keeps_it_exhaustive(tmp_path):
    # jsonl has no footer, so a cap could easily cost the exact count on files that never hit it.
    # Reading to EOF under the cap must stay exact, or capping would degrade every small dataset.
    (tmp_path / "train.jsonl").write_text('{"a": 1}\n{"a": 2}\n')

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=1000)

    assert result.partitions[0].splits[0].num_examples == 2
    assert result.partitions[0].rows_complete is True
    assert result.sampling.rows_present == 2


def test_profile_reports_unsupported_data_files(tmp_path):
    # A directory of formats we cannot read must not profile as an exhaustively scanned empty
    # dataset — that is indistinguishable from a dataset that really is empty.
    (tmp_path / "train.csv").write_text("prompt,completion\na,b\n")
    (tmp_path / "test.arrow").write_bytes(b"\x00")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.partitions == []
    assert result.sampling.rows_present is None  # not 0: "empty" would be a lie
    assert result.sampling.files_read == 0
    assert result.sampling.files_present == 2  # both are data; neither could be read
    # ...and they still weigh what they weigh. This is the case `bytes_present` exists for: no
    # partition grouped these files, so summing the splits reports zero -- the same lie as "empty".
    on_disk = (tmp_path / "train.csv").stat().st_size + (tmp_path / "test.arrow").stat().st_size
    assert result.sampling.bytes_present == on_disk
    assert sum(s.size_bytes for p in result.partitions for s in p.splits) == 0
    # Typed records now, each saying why -- not bare paths tucked into a free-form dict.
    assert [e.path for e in result.file_errors] == ["test.arrow", "train.csv"]
    assert all("no reader" in e.error for e in result.file_errors)


def test_profile_ignores_non_data_files_without_penalty(tmp_path):
    # A README is genuinely not data, so it must not cost exhaustiveness the way a .csv does.
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "README.md").write_text("a dataset card")
    (tmp_path / "LICENSE").write_text("apache")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.partitions[0].rows_complete is True
    assert result.file_errors == []
    assert result.sampling.files_present == 1  # the README and LICENSE are not data, counted nowhere
    # Nor does their weight land on the dataset: a card is not part of what has to be moved.
    assert result.sampling.bytes_present == (tmp_path / "train-00000-of-00001.parquet").stat().st_size


def test_split_size_survives_a_shard_it_could_not_read(tmp_path):
    # Size comes from the listing and a row count from reading, so they go unknown independently.
    # A shard that fails to parse still weighs what it weighs, where the split's row count cannot.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"a": 1}, {"a": 2}])
    (tmp_path / "train-00001-of-00002.parquet").write_bytes(b"not parquet")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    on_disk = sum(p.stat().st_size for p in tmp_path.glob("*.parquet"))
    split = result.partitions[0].splits[0]
    assert split.num_files == 2
    assert split.size_bytes == on_disk  # both shards, including the one that would not open
    assert split.num_examples is None  # the broken shard's rows are unknowable...
    assert split.size_bytes > 0  # ...but its bytes are not
    assert result.sampling.bytes_present == on_disk


def test_profile_records_a_partial_jsonl_read(tmp_path):
    # One corrupt line costs that line, not the file — but the profile must still say the file was
    # only partly understood, rather than presenting a clean-looking count.
    (tmp_path / "train.jsonl").write_text('{"a": 1}\n{"a": 2\n{"a": 3}\n')

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.partitions[0].splits[0].num_examples == 2  # the readable rows survived
    assert [e.path for e in result.file_errors] == ["train.jsonl"]
    assert "line 2" in result.file_errors[0].error
    assert result.partitions[0].rows_complete is False  # a line was lost, so not a full scan


def test_profile_classifies_roles_type_and_verifiability(tmp_path):
    _write_parquet(
        tmp_path / "train-00000-of-00001.parquet",
        [{"problem": "q1", "solution": "steps #### 5"}, {"problem": "q2", "solution": "steps #### 6"}],
    )
    partition = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0]

    assert {f.semantic_role for f in partition.features} == {"prompt", "completion"}
    assert partition.classification.dataset_type == "prompt_completion"
    assert partition.classification.verifiability.method == "extractable_final_answer"
    assert partition.classification.verifiability.coverage == 1.0


def test_profile_from_value_dataset_is_a_chat_dataset(tmp_path):
    # End to end: {from, value} must reach the messages dtype, carry stats, and classify as chat
    # rather than falling through to `unknown` with nothing measured.
    conversation = [{"from": "human", "value": "hi"}, {"from": "gpt", "value": "hello"}]
    (tmp_path / "train.jsonl").write_text(json.dumps({"conversations": conversation}) + "\n")

    partition = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0]

    assert partition.features[0].dtype == "messages"
    assert partition.features[0].semantic_role == "messages"
    assert partition.classification.dataset_type == "messages"
    assert partition.stats["conversations"].messages.roles_seen == ["human", "gpt"]


def test_profile_degrades_one_partition_when_measurement_fails(tmp_path, monkeypatch):
    # Reads are isolated per file, but schema/stats/classification ran unguarded, so one odd value
    # could abort an otherwise complete profile. Structure must survive a measurement failure.
    from nemo_datasets_plugin.profiler import pipeline as pipeline_module

    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}, {"a": 2}])
    monkeypatch.setattr(pipeline_module, "classify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)  # must not raise

    partition = result.partitions[0]
    assert partition.splits[0].num_examples == 2  # structure survives
    assert partition.stats == {}
    assert partition.classification.dataset_type == "unknown"
    assert [e.kind for e in partition.classification.evidence] == ["error"]
    assert "RuntimeError" in partition.classification.evidence[0].detail  # says what failed


def test_a_read_failure_does_not_look_like_a_measurement_failure(tmp_path):
    # The two failure domains have to stay distinguishable: a bad *file* is a FileError, and the
    # rows that were readable still measure and classify normally. Folding the read and measure
    # loops together is what would blur this, so it is pinned before that happens.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"prompt": "q", "completion": "a"}])
    (tmp_path / "train-00001-of-00002.parquet").write_bytes(b"not parquet")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    part = result.partitions[0]
    assert [e.path for e in result.file_errors] == ["train-00001-of-00002.parquet"]
    assert part.classification.dataset_type == "prompt_completion"  # the readable rows still classify
    assert "error" not in {e.kind for e in part.classification.evidence}
    assert part.stats  # ...and are still measured


def test_a_measurement_failure_does_not_look_like_a_read_failure(tmp_path, monkeypatch):
    from nemo_datasets_plugin.profiler import pipeline as pipeline_module

    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    monkeypatch.setattr(pipeline_module, "classify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.file_errors == []  # the file was fine; the data was odd
    assert [e.kind for e in result.partitions[0].classification.evidence] == ["error"]
    # `rows_complete` speaks to rows read, and every row *was* read -- so it stays True even though
    # there are no stats. Pinned as it stands; the field means what it says once Phase 5 renames it.
    assert result.partitions[0].rows_complete is True


def test_one_unmeasurable_column_does_not_cost_the_partition_its_classification(tmp_path, monkeypatch):
    # The narrow guard, end to end. The column's failure reaches the profile as evidence, and
    # everything the partition could still establish -- the other column's stats, the roles, the
    # dataset type -- survives it.
    from nemo_datasets_plugin.profiler import stats as stats_module

    real_accumulator_for = stats_module._accumulator_for

    class Boom(stats_module.ColumnAccumulator):
        def _observe(self, present):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        stats_module,
        "_accumulator_for",
        lambda feature: Boom() if feature.name == "completion" else real_accumulator_for(feature),
    )
    _write_parquet(tmp_path / "train.parquet", [{"prompt": "q", "completion": "a"}])

    part = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0]

    assert "prompt" in part.stats and "completion" not in part.stats
    assert part.classification.dataset_type == "prompt_completion"  # roles come from names, not stats
    assert any(e.kind == "error" and "'completion'" in e.detail for e in part.classification.evidence)
    # The reasoning for the classification still reads first; the failure is a caveat on it.
    assert part.classification.evidence[0].kind != "error"


def test_a_measurement_failure_is_scoped_to_its_own_partition(tmp_path, monkeypatch):
    from nemo_datasets_plugin.profiler import pipeline as pipeline_module

    real_classify = pipeline_module.classify

    def poison_one_partition(features, stats, **kwargs):
        if any(feature.name == "poison" for feature in features):
            raise RuntimeError("boom")
        return real_classify(features, stats, **kwargs)

    _write_parquet(tmp_path / "good" / "train.parquet", [{"prompt": "q", "completion": "a"}])
    _write_parquet(tmp_path / "bad" / "train.parquet", [{"poison": 1}])
    monkeypatch.setattr(pipeline_module, "classify", poison_one_partition)

    partitions = {p.name: p for p in profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions}

    assert partitions["bad"].classification.dataset_type == "unknown"
    assert partitions["good"].classification.dataset_type == "prompt_completion"
    assert partitions["good"].stats  # a neighbour's bad data costs this partition nothing


def test_a_file_that_fails_partway_still_counts_what_it_contributed(tmp_path, monkeypatch):
    # A read used to be all-or-nothing, so a failure meant no rows at all and the envelope could be
    # written after it. A fold cannot give rows back: batches already folded are in the statistics
    # whatever happens next, and counting the file as unread left `rows_scanned` describing fewer
    # rows than the stats were built from.
    from nemo_datasets_plugin.profiler import pipeline as pipeline_module

    _write_parquet(tmp_path / "train.parquet", [{"a": i} for i in range(4000)])
    real_update = pipeline_module._PartitionFolds.update
    calls = {"n": 0}

    def fail_on_the_third_batch(self, rows):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom mid-file")
        return real_update(self, rows)

    monkeypatch.setattr(pipeline_module._PartitionFolds, "update", fail_on_the_third_batch)
    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.sampling.rows_scanned == 2048  # two batches of 1024 were folded before it failed
    assert result.sampling.files_read == 1  # the file *was* read from, just not to its end
    assert result.partitions[0].stats["a"].numeric is not None  # and those rows shaped the stats
    assert [e.path for e in result.file_errors] == ["train.parquet"]
    assert result.partitions[0].rows_complete is False


def test_reading_everything_is_the_default(tmp_path):
    # The point of the whole exercise. The budget existed to keep a materialised partition off the
    # heap; nothing is materialised, so the default should not answer the question worse than it can
    # be answered.
    _write_parquet(tmp_path / "train.parquet", [{"t": f"row {i}"} for i in range(5_000)])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.sampling.rows_scanned == 5_000 == result.sampling.rows_present
    assert result.partitions[0].rows_complete is True


def test_rows_complete_speaks_to_rows_read_not_to_exactness(tmp_path):
    # It was `stats_complete`, which promised more than it delivered: the length quantiles are
    # estimates by construction, whatever it says. Renamed to what it actually measures.
    _write_parquet(tmp_path / "train.parquet", [{"t": f"row {i}"} for i in range(100)])

    short = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=10)
    whole = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert short.partitions[0].rows_complete is False  # ten of a hundred rows
    assert whole.partitions[0].rows_complete is True
    # True either way, and it is the measurements themselves that say whether they are exact.
    assert whole.partitions[0].stats["t"].text.chars.max == max(len(f"row {i}") for i in range(100))


def test_profile_is_deterministic(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}, {"a": 2}])
    source = LocalFileSource(tmp_path)
    first = profile(source, created_at=FIXED_TIME)
    second = profile(source, created_at=FIXED_TIME)
    assert first.model_dump_json() == second.model_dump_json()


def test_profile_tolerates_non_object_jsonl_lines(tmp_path):
    # A valid-JSON-but-non-object line parses cleanly, so the reader (not the read) must handle it;
    # otherwise it would poison the unprotected schema/stats stage and abort the whole profile.
    (tmp_path / "train.jsonl").write_text('{"a": 1}\n[1, 2, 3]\n{"a": 2}\n')
    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.partitions[0].splits[0].num_examples == 2  # objects counted, stray array dropped
    assert result.partitions[0].rows_complete is True


def test_profile_survives_a_hostile_directory(tmp_path):
    """Everything that can go wrong at once must still yield a profile that says what went wrong.

    Each of these individually used to either abort the run or vanish silently; this is the shape of
    bug that got through, so it is worth asserting as one scenario rather than only in isolation.
    """
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"prompt": "a", "completion": "b"}])
    (tmp_path / "train-00001-of-00002.parquet").write_bytes(b"not a parquet file")  # corrupt
    (tmp_path / "extra.jsonl").write_text(
        '{"messages": [{"role": 1, "content": "hi"}]}\n'  # non-string role
        '{"messages": [{"role": "user"\n'  # truncated line
        "[1, 2, 3]\n"  # valid JSON, not a row
        '{"messages": [{"role": "user", "content": "ok"}]}\n'
    )
    (tmp_path / "leftovers.csv").write_text("a,b\n1,2\n")  # recognizable data, no reader
    (tmp_path / "README.md").write_text("a dataset card")  # not data at all

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)  # must not raise

    # Nothing here is exhaustive, and the profile says so rather than looking clean.
    assert result.partitions[0].rows_complete is False
    assert result.sampling.rows_present is None
    # One channel for every file the profiler could not use, whether or not a partition grouped it:
    # the .csv it never read, the corrupt shard, and the jsonl it only partly parsed.
    assert [e.path for e in result.file_errors] == [
        "extra.jsonl",
        "leftovers.csv",
        "train-00001-of-00002.parquet",
    ]

    # One partition, not one per format: the stray .jsonl is noise, not a second dataset.
    assert len(result.partitions) == 1
    partition = result.partitions[0]
    assert partition.file_formats == ["jsonl", "parquet"]
    # The readable parquet rows still produced a real classification...
    assert partition.classification.dataset_type == "prompt_completion"
    # ...and the odd jsonl rows were measured rather than aborting the run.
    assert partition.stats["messages"].messages.roles_seen == ["1", "user"]

    # The whole thing still round-trips as a stored profile.
    assert DatasetProfile.model_validate_json(result.model_dump_json()) == result


def test_split_file_counts_account_for_every_data_file(tmp_path):
    # The contract promises split membership is exhaustive and disjoint. With per-file records gone
    # the counts are all that carries it, so the invariant is worth asserting on them directly --
    # a count that silently dropped a file would look exactly like a smaller dataset.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"a": 1}])
    _write_parquet(tmp_path / "train-00001-of-00002.parquet", [{"a": 2}])
    _write_parquet(tmp_path / "test-00000-of-00001.parquet", [{"a": 3}])
    (tmp_path / "README.md").write_text("a dataset card")  # not data; never becomes a FileRecord

    source = LocalFileSource(tmp_path)
    result = profile(source, created_at=FIXED_TIME)

    counted = sum(split.num_files for partition in result.partitions for split in partition.splits)
    listed = [e.path for e in source.list_files() if e.path.endswith(".parquet")]
    assert counted == len(listed)  # exhaustive and disjoint: each file lands in exactly one split


def test_profile_isolates_detected_format_with_no_reader(tmp_path, monkeypatch):
    # If detect_format recognizes an extension the registry has no reader for, that file must be
    # isolated like a corrupt one, not crash the whole profile.
    from nemo_datasets_plugin.profiler.readers import base

    monkeypatch.setitem(base._EXTENSION_FORMATS, ".xyz", "xyz-no-reader")
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "extra.xyz").write_text("whatever")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)  # must not raise

    assert "extra.xyz" in {e.path for e in result.file_errors}  # named, not silently dropped
    assert result.partitions[0].rows_complete is False


def test_a_column_only_a_schemaless_file_witnessed_survives(tmp_path):
    # A group where only some files declare a schema used to trust that schema and erase every column
    # the schemaless files were the sole witness for. Now the partition infers its schema from the
    # rows as it folds them, so the sole witness is heard.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"prompt": "a"}])
    (tmp_path / "train-00001-of-00002.jsonl").write_text(json.dumps({"prompt": "b", "extra": "only here"}))

    part = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0]

    assert [f.name for f in part.features] == ["prompt", "extra"]
    assert set(part.stats) <= {f.name for f in part.features}


def test_a_declared_schema_is_trusted_when_it_covers_every_file(tmp_path):
    # The other half: when every file declares one, the schema is authoritative and the rows are not
    # consulted for it. That is what lets the partition fold with its accumulators chosen up front.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"prompt": "a"}])
    _write_parquet(tmp_path / "train-00001-of-00002.parquet", [{"prompt": "b"}])

    part = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions[0]

    assert [f.name for f in part.features] == ["prompt"]


def test_rows_completeness_is_per_partition(tmp_path):
    # A corrupt shard in one partition says nothing about the measurements in another, but a
    # fileset-wide flag downgraded every partition to the worst one. It was never even the value
    # that gated quoting a proven enumeration -- that was decided per partition and never stored.
    rows = [{"label": t} for t in (True, False, True)]
    _write_parquet(tmp_path / "main" / "train.parquet", rows)
    _write_parquet(tmp_path / "socratic" / "train.parquet", rows)
    (tmp_path / "socratic" / "broken.parquet").write_bytes(b"not a parquet file")

    partitions = {p.name: p for p in profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions}

    assert partitions["main"].rows_complete is True
    assert partitions["socratic"].rows_complete is False
    # Quoting is decided by role, not by completeness, so both keep their label vocabulary --
    # rows_complete is what tells a consumer whether socratic's list is the whole of it.
    assert partitions["main"].stats["label"].categorical.values == ["False", "True"]
    assert partitions["socratic"].stats["label"].categorical.values == ["False", "True"]


def test_dataset_wide_completeness_is_one_expression(tmp_path):
    # SamplingInfo no longer carries `exhaustive`; the contract documents this derivation in its
    # place. It has to keep working, or dropping the flag cost consumers something -- and it now
    # says *which* half failed, which the single bit could not.
    _write_parquet(tmp_path / "train.parquet", [{"a": 1}])
    clean = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)
    assert all(p.rows_complete for p in clean.partitions) and not clean.file_errors

    (tmp_path / "extra.csv").write_text("a,b\n1,2\n")
    with_csv = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)
    assert all(p.rows_complete for p in with_csv.partitions)  # the parquet rows are still complete
    assert with_csv.file_errors  # but there is data here that went unprofiled
    assert with_csv.sampling.files_read == 1 and with_csv.sampling.files_present == 2


def test_row_budget_is_divided_across_a_partitions_files(tmp_path):
    for shard in range(4):
        _write_parquet(tmp_path / f"train-{shard:05d}-of-00004.parquet", [{"a": i} for i in range(200)])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=400)

    assert result.sampling.rows_scanned == 400  # 400 / 4 files = 100 rows each


def test_rows_read_do_not_grow_when_a_dataset_is_resharded(tmp_path_factory):
    # The property the budget exists for. Under a per-file cap the same data split ten ways further
    # cost ten times the peak memory while describing exactly the same rows.
    def rows_read(shards, per_shard):
        root = tmp_path_factory.mktemp(f"shards{shards}")
        for shard in range(shards):
            _write_parquet(root / f"train-{shard:05d}-of-{shards:05d}.parquet", [{"a": i} for i in range(per_shard)])
        return profile(LocalFileSource(root), created_at=FIXED_TIME, row_budget=400).sampling.rows_scanned

    assert rows_read(4, 200) == rows_read(40, 20) == 400


def test_row_budget_keeps_a_floor_under_very_thin_shards(tmp_path):
    # Below the floor a file cannot witness the columns only it holds, which is the reason every file
    # is opened rather than a subset sampled. Overshooting the budget there is the right trade, and
    # the arithmetic share would be 1, so the floor holds and the budget is deliberately exceeded.
    for shard in range(10):
        _write_parquet(tmp_path / f"train-{shard:05d}-of-00010.parquet", [{"a": i} for i in range(50)])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_budget=10)

    assert result.sampling.rows_scanned == 100  # 10 files x the 10-row floor, over the budget of 10
