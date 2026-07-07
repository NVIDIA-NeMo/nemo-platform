# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the dataset profiler engine (app/profiler.py)."""

import json

import pytest
from nmp.common.files.dataset_profile import (
    DatasetProfile,
    DetectedFormat,
    TrainingTask,
    to_dataset_metadata_content,
)
from nmp.common.files.metadata import DatasetMetadataContent
from nmp.core.files.app.backends.base import ByteRange, FileInfo, StorageImpl
from nmp.core.files.app.profiler import (
    STRATIFY_MIN_BYTES,
    profile_fileset_storage,
)


class DictStorage(StorageImpl):
    """Minimal in-memory storage for profiler tests."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    async def list_files(self, path: str | None = None) -> list[FileInfo]:
        prefix = path or ""
        return [
            FileInfo(path=p, size=len(d))
            for p, d in sorted(self.files.items())
            if p.startswith(prefix)
        ]

    async def download(self, path: str, byte_range: ByteRange | None = None):
        data = self.files[path]
        if byte_range:
            data = data[byte_range.start : byte_range.end + 1]
        yield data

    async def upload(self, path, fstream, content_length=None):  # pragma: no cover
        raise NotImplementedError

    async def delete(self, path):  # pragma: no cover
        raise NotImplementedError

    async def validate_storage(self):  # pragma: no cover
        pass


def jsonl(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in rows)


def tasks(profile: DatasetProfile, group: int = 0) -> dict[str, float]:
    return {
        c.task.value: c.confidence
        for c in profile.groups[group].semantics.task_candidates
    }


async def test_sft_jsonl_profile():
    storage = DictStorage(
        {"train.jsonl": jsonl([{"prompt": f"q{i}", "completion": f"a{i}"} for i in range(50)])}
    )
    profile = await profile_fileset_storage(storage)
    assert profile.primary == "group-0"
    g = profile.groups[0]
    assert g.semantics.detected_format == DetectedFormat.PROMPT_COMPLETION
    assert tasks(profile)["sft"] >= 0.8
    assert g.structure.num_rows == 50  # fully read => exact
    assert g.structure.row_schema["required"] == ["completion", "prompt"]


async def test_mixed_schema_shards_become_groups():
    storage = DictStorage(
        {
            "sft.jsonl": jsonl([{"prompt": f"q{i}", "completion": f"a{i}"} for i in range(50)]),
            "prefs.jsonl": jsonl(
                [{"prompt": f"q{i}", "chosen": "g", "rejected": "b"} for i in range(50)]
            ),
        }
    )
    profile = await profile_fileset_storage(storage)
    assert len(profile.groups) == 2
    formats = {g.semantics.detected_format for g in profile.groups}
    assert formats == {DetectedFormat.PROMPT_COMPLETION, DetectedFormat.PREFERENCE_BINARY}


async def test_stratified_ranged_reads_see_past_sorted_head():
    pad = "x" * 300
    rows = [{"text": f"{pad}{i}", "label": 0 if i < 2000 else 1} for i in range(4000)]
    data = jsonl(rows)
    assert len(data) >= STRATIFY_MIN_BYTES
    storage = DictStorage({"sorted.jsonl": data})
    p1 = await profile_fileset_storage(storage)
    p2 = await profile_fileset_storage(storage)
    assert p1 == p2  # deterministic => idempotent metadata writes
    g = p1.groups[0]
    assert g.sampling.strategy == "stratified"
    label_stats = next(s for s in g.statistics if s.column_name == "label")
    assert label_stats.column_statistics["n_unique"] == 2


async def test_preference_ambiguity_and_tie():
    storage = DictStorage(
        {"d.jsonl": jsonl([{"chosen": f"g{i}", "rejected": f"b{i}"} for i in range(30)])}
    )
    profile = await profile_fileset_storage(storage)
    t = tasks(profile)
    assert t["dpo"] == t["reward_model"]
    assert any("DPO vs reward-model" in a for a in profile.groups[0].semantics.ambiguities)


async def test_prompt_only_chat_is_rl_not_sft():
    storage = DictStorage(
        {
            "d.jsonl": jsonl(
                [{"messages": [{"role": "user", "content": f"solve {i}"}]} for i in range(30)]
            )
        }
    )
    profile = await profile_fileset_storage(storage)
    t = tasks(profile)
    assert "sft" not in t
    assert TrainingTask.GRPO.value in t


async def test_config_json_and_parquet_skipped():
    storage = DictStorage(
        {
            "dataset_infos.json": json.dumps({"default": {"description": "x"}}).encode(),
            "shard.parquet": b"PAR1notreallyparquet",
            "train.jsonl": jsonl([{"text": f"t{i}"} for i in range(20)]),
        }
    )
    profile = await profile_fileset_storage(storage)
    reasons = {s.path: s.reason for s in profile.source.files_skipped}
    assert reasons["dataset_infos.json"] == "packaging-metadata"
    assert reasons["shard.parquet"] == "parquet-not-yet-supported"
    assert len(profile.groups) == 1
    assert profile.groups[0].columns == ["text"]


async def test_csv_coercion():
    lines = ["text,label,score"] + [f"review {i},{i % 2},{i / 10}" for i in range(30)]
    storage = DictStorage({"d.csv": "\n".join(lines).encode() + b"\n"})
    profile = await profile_fileset_storage(storage)
    g = profile.groups[0]
    assert g.semantics.detected_format == DetectedFormat.TEXT_CLASSIFICATION
    assert g.structure.features["label"] == {"dtype": "int64", "_type": "Value"}


async def test_classlabel_never_leaks_free_text_values():
    storage = DictStorage(
        {
            "d.jsonl": jsonl(
                [{"prompt": f"q{i}", "completion": ["yes", "no", "maybe"][i % 3]} for i in range(30)]
            )
        }
    )
    profile = await profile_fileset_storage(storage)
    feats = profile.groups[0].structure.features
    assert feats["completion"] == {"dtype": "string", "_type": "Value"}
    assert "ClassLabel" not in json.dumps(feats)


async def test_files_hash_tracks_listing():
    files_a = [FileInfo(path="a.jsonl", size=10)]
    files_b = [FileInfo(path="a.jsonl", size=11)]
    from nmp.core.files.app.profiler import files_hash

    assert files_hash(files_a) != files_hash(files_b)
    assert files_hash(files_a) == files_hash(list(files_a))


async def test_bridge_output_satisfies_dataset_metadata_content():
    storage = DictStorage(
        {
            "sft.jsonl": jsonl([{"prompt": f"q{i}", "completion": f"a{i}"} for i in range(30)]),
            "prefs.jsonl": jsonl(
                [{"prompt": f"q{i}", "chosen": "g", "rejected": "b"} for i in range(30)]
            ),
        }
    )
    profile = await profile_fileset_storage(storage)
    content = DatasetMetadataContent(**to_dataset_metadata_content(profile))
    assert content.schema_ == profile.primary
    assert set(content.schemas_by_path) == {"sft.jsonl", "prefs.jsonl"}


async def test_empty_fileset_profiles_to_no_groups():
    profile = await profile_fileset_storage(DictStorage({}))
    assert profile.groups == []
    assert profile.primary is None


@pytest.mark.parametrize(
    ("rows", "expected_format"),
    [
        ([{"prompt": "q", "completion": "a", "label": True}] * 30, DetectedFormat.UNPAIRED_PREFERENCE),
        ([{"anchor": "a", "positive": "p", "negative": "n"}] * 30, DetectedFormat.EMBEDDING_TRIPLET),
        ([{"prompt": "solve", "solution": "42"}] * 30, DetectedFormat.PROMPT_WITH_GROUND_TRUTH),
        ([{"question": "q", "label": 1}] * 30, DetectedFormat.TEXT_CLASSIFICATION),
    ],
)
async def test_format_table(rows, expected_format):
    storage = DictStorage({"d.jsonl": jsonl(rows)})
    profile = await profile_fileset_storage(storage)
    assert profile.groups[0].semantics.detected_format == expected_format
