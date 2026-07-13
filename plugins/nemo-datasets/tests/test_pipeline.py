# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the profiling pipeline: digest, split/partition resolution, and envelope assembly."""

from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
from nemo_datasets_plugin.profiler.digest import content_digest
from nemo_datasets_plugin.profiler.file_source import FileEntry, LocalFileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.pipeline import profile
from nemo_datasets_plugin.profiler.splits import resolve_splits

FIXED_TIME = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _write_parquet(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _entries(*paths):
    return [FileEntry(path=p, size_bytes=100) for p in paths]


# --- content digest ------------------------------------------------------------------------------


def test_content_digest_is_stable_and_order_independent():
    a = _entries("train.parquet", "test.parquet")
    b = list(reversed(a))
    assert content_digest(a) == content_digest(b)
    assert content_digest(a).startswith("sha256:")


def test_content_digest_changes_with_size():
    base = _entries("train.parquet")
    bigger = [FileEntry(path="train.parquet", size_bytes=200)]
    assert content_digest(base) != content_digest(bigger)


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


def test_resolve_splits_falls_back_to_single_default():
    splits = resolve_splits(_entries("shard-00000.parquet", "shard-00001.parquet"))
    assert len(splits) == 1
    assert splits[0].name == "default"
    assert splits[0].canonical is None
    assert len(splits[0].entries) == 2


# --- partition grouping --------------------------------------------------------------------------


def test_group_partitions_single_default_for_root_files():
    assert group_partitions(_entries("train.parquet", "test.parquet")) == [
        ("default", _entries("train.parquet", "test.parquet"))
    ]


def test_group_partitions_collapses_single_container_dir():
    parts = group_partitions(_entries("data/train.parquet", "data/test.parquet"))
    assert [name for name, _ in parts] == ["default"]


def test_group_partitions_splits_multiple_top_dirs():
    parts = group_partitions(_entries("main/train.parquet", "socratic/train.parquet"))
    assert [name for name, _ in parts] == ["main", "socratic"]


# --- end-to-end profile() ------------------------------------------------------------------------


def test_profile_parquet_dataset_builds_envelope(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"prompt": "a"}, {"prompt": "b"}])
    _write_parquet(tmp_path / "validation-00000-of-00001.parquet", [{"prompt": "c"}])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert result.content_digest.startswith("sha256:")
    assert result.profiler_info["name"] == "nemo-dataset-profiler"
    assert len(result.partitions) == 1
    partition = result.partitions[0]
    assert partition.name == "default"
    assert partition.file_format == "parquet"

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

    assert result.sampling.exhaustive is True
    assert result.sampling.strategy == "full"
    assert result.sampling.rows_scanned == 3
    assert result.sampling.rows_total == 3
    assert result.sampling.files_scanned == 2


def test_profile_jsonl_dataset_counts_rows_exactly(tmp_path):
    (tmp_path / "train.jsonl").write_text('{"a": 1}\n{"a": 2}\n{"a": 3}\n')
    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    partition = result.partitions[0]
    assert partition.file_format == "jsonl"
    assert partition.splits[0].name == "train"
    assert partition.splits[0].num_examples == 3
    assert result.sampling.rows_scanned == 3


def test_profile_multiple_directories_become_partitions(tmp_path):
    _write_parquet(tmp_path / "main" / "train-00000-of-00001.parquet", [{"q": "1"}])
    _write_parquet(tmp_path / "socratic" / "train-00000-of-00001.parquet", [{"q": "2"}])

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    assert [p.name for p in result.partitions] == ["main", "socratic"]
    assert all(p.file_format == "parquet" for p in result.partitions)


def test_profile_isolates_unreadable_files(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    (tmp_path / "test-00000-of-00001.parquet").write_bytes(b"not a real parquet file")

    result = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    splits = {s.name: s for s in result.partitions[0].splits}
    assert splits["train"].num_examples == 1
    assert splits["test"].num_examples is None  # unreadable -> count unknown, not a crash
    assert splits["test"].files[0].num_rows is None
    assert result.sampling.exhaustive is False  # a file could not be fully parsed
    assert result.sampling.rows_total is None


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


def test_profile_digest_covers_only_stored_files(tmp_path):
    _write_parquet(tmp_path / "train-00000-of-00001.parquet", [{"a": 1}])
    without_card = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    (tmp_path / "README.md").write_text("a dataset card")  # a non-data file, never stored as a FileRecord
    with_card = profile(LocalFileSource(tmp_path), created_at=FIXED_TIME)

    # A file the profile does not store must not move the digest...
    assert without_card.content_digest == with_card.content_digest
    # ...and the digest is recomputable from exactly the FileRecords the profile stores.
    stored = [
        FileEntry(path=f.path, size_bytes=f.size_bytes, checksum=f.checksum)
        for partition in with_card.partitions
        for split in partition.splits
        for f in split.files
    ]
    assert content_digest(stored) == with_card.content_digest


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
