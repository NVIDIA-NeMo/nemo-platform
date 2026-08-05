# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the profiling pipeline: split/partition resolution and envelope assembly."""

import json
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
from nemo_datasets_plugin.profiler.file_source import FileEntry, LocalFileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.pipeline import _measure, profile
from nemo_datasets_plugin.profiler.splits import resolve_splits
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


# --- partition grouping --------------------------------------------------------------------------


def test_group_partitions_single_default_for_root_files():
    assert group_partitions(_entries("train.parquet", "test.parquet")) == [
        (None, _entries("train.parquet", "test.parquet"))
    ]


def test_group_partitions_collapses_single_container_dir():
    # One container directory is still one partition, but its identity stays the directory. Losing
    # "data" here is what let a partition's identity move when the surrounding layout changed.
    parts = group_partitions(_entries("data/train.parquet", "data/test.parquet"))
    assert [source_dir for source_dir, _ in parts] == ["data"]


def test_group_partitions_splits_multiple_top_dirs():
    parts = group_partitions(_entries("main/train.parquet", "socratic/train.parquet"))
    assert [source_dir for source_dir, _ in parts] == ["main", "socratic"]


def test_group_partitions_does_not_treat_split_dirs_as_partitions():
    # train/ and test/ are one dataset's splits, not two datasets.
    parts = group_partitions(_entries("train/data.parquet", "test/data.parquet"))
    assert [source_dir for source_dir, _ in parts] == [None]


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
    assert partition.name == "default"
    assert partition.file_formats == ["parquet"]

    splits = {s.name: s for s in partition.splits}
    assert set(splits) == {"train", "validation"}
    assert splits["train"].canonical == "train"
    assert splits["train"].num_examples == 2
    assert splits["validation"].num_examples == 1
    assert splits["train"].files[0].num_rows == 2

    # Row schema, stats, and classification are all derived now.
    assert [f.name for f in partition.features] == ["prompt"]
    assert partition.features[0].dtype == "string"
    assert partition.features[0].semantic_role == "prompt"
    assert partition.stats["prompt"].text is not None
    assert partition.classification.dataset_type == "prompt_only"  # a lone prompt column, no target

    # strategy is the policy, exhaustive is the outcome: a capped run over files that all fit under
    # the cap is still a full scan, which is why the contract keeps the two fields independent.
    assert result.sampling.strategy == "head_per_file"
    assert result.sampling.exhaustive is True
    assert result.sampling.per_file_row_cap == 1000
    assert result.sampling.rows_scanned == 3
    assert result.sampling.rows_total == 3
    assert result.sampling.files_scanned == 2


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
    assert [p.source_dir for p in result.partitions] == ["main", "socratic"]


def test_profile_top_level_split_dirs_become_one_partition(tmp_path):
    # train/ + test/ is one dataset with two splits, not two datasets. As separate partitions each
    # would derive its own schema and classification, and the split structure would disappear.
    _write_parquet(tmp_path / "train" / "data.parquet", [{"prompt": "a", "completion": "b"}])
    _write_parquet(tmp_path / "test" / "data.parquet", [{"prompt": "c", "completion": "d"}])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert [p.name for p in result.partitions] == ["default"]
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

    assert [p.name for p in result.partitions] == ["default"]
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
    assert partition.name == "default"
    assert partition.source_dir == "data"
    assert partition.file_formats == ["jsonl", "parquet"]
    assert {f.path.rsplit("/", 1)[-1]: f.file_format for s in partition.splits for f in s.files} == {
        "train-00000-of-00001.parquet": "parquet",
        "extra.jsonl": "jsonl",
    }
    # Both formats' columns reach features. Trusting the declared parquet schema would have erased
    # `question`, which only the schemaless file witnesses -- the defect the split worked around.
    assert sorted(f.name for f in partition.features) == ["prompt", "question"]
    assert result.sampling.rows_scanned == 3  # 1 parquet + 2 jsonl, each counted once
    assert result.sampling.exhaustive is True


def test_root_files_and_a_directory_named_default_stay_distinct():
    # Both label as "default"; only source_dir tells them apart. Flattening the two into one string
    # produced two partitions with the same name and no way to reference either.
    parts = group_partitions(_entries("root.parquet", "default/inner.parquet"))
    assert [source_dir for source_dir, _ in parts] == ["default", None]


def test_an_unrelated_file_does_not_rename_a_partition(tmp_path):
    # Dropping a stray .jsonl into main/ used to turn partition "main" into "main:parquet" -- not
    # renamed, *gone*, so a stored reference resolved to nothing.
    _write_parquet(tmp_path / "main" / "train.parquet", [{"q": "a"}])
    _write_parquet(tmp_path / "socratic" / "train.parquet", [{"q": "b"}])
    before = [(p.name, p.source_dir) for p in profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions]

    (tmp_path / "main" / "notes.jsonl").write_text('{"note": "someone dropped this here"}\n')
    after = [(p.name, p.source_dir) for p in profile(LocalFileSource(tmp_path), created_at=FIXED_TIME).partitions]

    assert before == after == [("main", "main"), ("socratic", "socratic")]


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


def test_profile_isolates_unreadable_files(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "test-00000-of-00001.parquet").write_bytes(b"not a real parquet file")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    splits = {s.name: s for s in result.partitions[0].splits}
    assert splits["train"].num_examples == 1
    assert splits["test"].num_examples is None  # unreadable -> count unknown, not a crash
    assert splits["test"].files[0].num_rows is None
    assert splits["test"].files[0].error is not None  # ...and the profile says why
    assert result.sampling.exhaustive is False  # a file could not be fully parsed
    assert result.sampling.rows_total is None
    assert result.sampling.files_scanned == 1  # one file was actually read; the other never opened


def test_profile_row_cap_bounds_reads_and_says_so(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": i} for i in range(10)])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_cap=4)

    assert result.sampling.rows_scanned == 4
    assert result.sampling.per_file_row_cap == 4
    assert result.sampling.exhaustive is False  # 4 of 10 rows is not a full scan
    assert result.sampling.rows_total is None
    assert result.partitions[0].splits[0].num_examples == 10  # the footer count survives sampling


def test_profile_uncapped_read_is_a_full_scan(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": i} for i in range(10)])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_cap=None)

    assert result.sampling.strategy == "full"
    assert result.sampling.per_file_row_cap is None
    assert result.sampling.exhaustive is True
    assert result.sampling.rows_scanned == 10


def test_profile_cap_larger_than_a_jsonl_file_keeps_it_exhaustive(tmp_path):
    # jsonl has no footer, so a cap could easily cost the exact count on files that never hit it.
    # Reading to EOF under the cap must stay exact, or capping would degrade every small dataset.
    (tmp_path / "train.jsonl").write_text('{"a": 1}\n{"a": 2}\n')

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME, row_cap=1000)

    assert result.partitions[0].splits[0].num_examples == 2
    assert result.sampling.exhaustive is True
    assert result.sampling.rows_total == 2


def test_profile_reports_unsupported_data_files(tmp_path):
    # A directory of formats we cannot read must not profile as an exhaustively scanned empty
    # dataset — that is indistinguishable from a dataset that really is empty.
    (tmp_path / "train.csv").write_text("prompt,completion\na,b\n")
    (tmp_path / "test.arrow").write_bytes(b"\x00")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.partitions == []
    assert result.sampling.exhaustive is False  # we scanned nothing, and admit it
    assert result.sampling.rows_total is None  # not 0: "empty" would be a lie
    assert result.profiler_info["unsupported_files"] == ["test.arrow", "train.csv"]


def test_profile_ignores_non_data_files_without_penalty(tmp_path):
    # A README is genuinely not data, so it must not cost exhaustiveness the way a .csv does.
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "README.md").write_text("a dataset card")
    (tmp_path / "LICENSE").write_text("apache")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.sampling.exhaustive is True
    assert "unsupported_files" not in result.profiler_info


def test_profile_records_a_partial_jsonl_read(tmp_path):
    # One corrupt line costs that line, not the file — but the profile must still say the file was
    # only partly understood, rather than presenting a clean-looking count.
    (tmp_path / "train.jsonl").write_text('{"a": 1}\n{"a": 2\n{"a": 3}\n')

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    record = result.partitions[0].splits[0].files[0]
    assert record.num_rows == 2  # the readable rows survived
    assert record.error is not None and "line 2" in record.error
    assert result.sampling.exhaustive is False  # a line was lost, so this is not a full scan


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


def test_profile_sharegpt_dataset_is_a_chat_dataset(tmp_path):
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
    monkeypatch.setattr(pipeline_module, "derive_stats", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)  # must not raise

    partition = result.partitions[0]
    assert partition.splits[0].num_examples == 2  # structure survives
    assert partition.stats == {}
    assert partition.classification.dataset_type == "unknown"
    assert [e.kind for e in partition.classification.evidence] == ["error"]
    assert "RuntimeError" in partition.classification.evidence[0].detail  # says what failed


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
    assert result.sampling.exhaustive is True


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
    assert result.sampling.exhaustive is False
    assert result.sampling.rows_total is None
    assert result.profiler_info["unsupported_files"] == ["leftovers.csv"]

    records = {f.path: f for p in result.partitions for s in p.splits for f in s.files}
    assert records["train-00001-of-00002.parquet"].error is not None  # corrupt file, named and explained
    assert records["extra.jsonl"].error is not None  # partial parse, named and explained

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


def test_stored_file_records_reproduce_the_input_list(tmp_path):
    # The contract promises split membership is exhaustive and disjoint, which is what lets a
    # consumer compare a stored profile against a fresh listing to decide whether it is current.
    # That comparison is the whole reason the records carry path/size/checksum, so the invariant is
    # worth asserting directly rather than through a digest that happened to depend on it.
    _write_parquet(tmp_path / "train-00000-of-00002.parquet", [{"a": 1}])
    _write_parquet(tmp_path / "train-00001-of-00002.parquet", [{"a": 2}])
    _write_parquet(tmp_path / "test-00000-of-00001.parquet", [{"a": 3}])
    (tmp_path / "README.md").write_text("a dataset card")  # not data; never becomes a FileRecord

    source = LocalFileSource(tmp_path)
    result = profile(source, created_at=FIXED_TIME)

    stored = [f.path for partition in result.partitions for split in partition.splits for f in split.files]
    listed = [e.path for e in source.list_files() if e.path.endswith(".parquet")]
    assert sorted(stored) == sorted(listed)  # exhaustive
    assert len(stored) == len(set(stored))  # and disjoint


def test_profile_isolates_detected_format_with_no_reader(tmp_path, monkeypatch):
    # If detect_format recognizes an extension the registry has no reader for, that file must be
    # isolated like a corrupt one, not crash the whole profile.
    from nemo_datasets_plugin.profiler.readers import base

    monkeypatch.setitem(base._EXTENSION_FORMATS, ".xyz", "xyz-no-reader")
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "extra.xyz").write_text("whatever")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)  # must not raise

    records = {f.path: f for p in result.partitions for s in p.splits for f in s.files}
    assert records["extra.xyz"].num_rows is None  # kept, but unreadable
    assert result.sampling.exhaustive is False


def test_measure_infers_from_rows_when_some_files_declared_no_schema():
    # derive_features uses the declared schema *if present at all*, so a group where only some files
    # declare one erased every column the schemaless files were the sole witness for. That is the
    # defect `_split_by_format` worked around by making partitions format-homogeneous; the fix
    # belongs in schema derivation, and dropping that homogeneity is what makes this path reachable.
    declared = pa.schema([pa.field("prompt", pa.string())])
    rows = [{"prompt": "a"}, {"prompt": "b", "extra": "only in the schemaless file"}]

    features, stats, _ = _measure(rows, [declared], exhaustive=True, all_declared=False)
    assert [f.name for f in features] == ["prompt", "extra"]  # the sole witness survives
    assert set(stats) <= {f.name for f in features}

    features, _, _ = _measure(rows, [declared], exhaustive=True, all_declared=True)
    assert [f.name for f in features] == ["prompt"]  # declared schema trusted when it covers everything
