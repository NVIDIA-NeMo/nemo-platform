# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for nmp.common.files.dataset_profile."""

import pytest
from pydantic import ValidationError

from nmp.common.files.dataset_profile import (
    DatasetProfile,
    DetectedFormat,
    TrainingTask,
    to_dataset_metadata_content,
)
from nmp.common.files.metadata import DatasetMetadataContent, FilesetMetadata


def make_profile(groups: list[dict] | None = None, primary: str | None = "group-0") -> dict:
    if groups is None:
        groups = [make_group("group-0", ["train.jsonl"])]
    return {
        "schema_version": "2.1",
        "profiler": {"name": "nmp-dataset-profiler", "version": "0.4.0",
                     "method": "sampled", "sampled_rows": 50},
        "source": {"kind": "storage", "path": "", "files_hash": "sha256:abc",
                   "files_skipped": [], "files_truncated": 0},
        "groups": groups,
        "primary": primary,
    }


def make_group(name: str, files: list[str]) -> dict:
    return {
        "name": name,
        "files": files,
        "columns": ["completion", "prompt"],
        "sampling": {"strategy": "head", "strata": None, "rows_sampled": 50},
        "structure": {
            "row_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"prompt": {"type": "string"}, "completion": {"type": "string"}},
                "required": ["completion", "prompt"],
            },
            "features": {"prompt": {"dtype": "string", "_type": "Value"},
                         "completion": {"dtype": "string", "_type": "Value"}},
            "num_rows": 50,
            "num_bytes": 1234,
        },
        "statistics": [
            {"column_name": "prompt", "column_type": "string_text",
             "column_statistics": {"nan_count": 0, "nan_proportion": 0.0}},
        ],
        "semantics": {
            "canonical_roles": {"prompt": "prompt", "completion": "completion"},
            "detected_format": "prompt_completion",
            "task_candidates": [
                {"task": "sft", "confidence": 0.8, "reason": "prompt/completion pairs"},
            ],
            "ambiguities": [],
        },
    }


def test_round_trip():
    profile = DatasetProfile.model_validate(make_profile())
    assert profile.primary_group() is not None
    assert profile.groups[0].semantics.detected_format == DetectedFormat.PROMPT_COMPLETION
    assert profile.groups[0].semantics.task_candidates[0].task == TrainingTask.SFT
    dumped = profile.model_dump(mode="json")
    assert DatasetProfile.model_validate(dumped) == profile


def test_unknown_task_rejected():
    raw = make_profile()
    raw["groups"][0]["semantics"]["task_candidates"][0]["task"] = "automodel"  # a backend!
    with pytest.raises(ValidationError):
        DatasetProfile.model_validate(raw)


def test_primary_must_name_a_group():
    with pytest.raises(ValidationError):
        DatasetProfile.model_validate(make_profile(primary="group-99"))
    with pytest.raises(ValidationError):
        DatasetProfile.model_validate(make_profile(primary=None))  # groups present


def test_empty_profile_allows_null_primary():
    profile = DatasetProfile.model_validate(make_profile(groups=[], primary=None))
    assert profile.primary_group() is None


def test_invalid_row_schema_rejected():
    raw = make_profile()
    raw["groups"][0]["structure"]["row_schema"] = {"type": 42}
    with pytest.raises(ValidationError):
        DatasetProfile.model_validate(raw)


def test_confidence_bounds():
    raw = make_profile()
    raw["groups"][0]["semantics"]["task_candidates"][0]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        DatasetProfile.model_validate(raw)


def test_bridge_and_metadata_integration():
    profile = DatasetProfile.model_validate(
        make_profile(
            groups=[make_group("group-0", ["a.jsonl"]), make_group("group-1", ["b.jsonl"])]
        )
    )
    bridge = to_dataset_metadata_content(profile)
    content = DatasetMetadataContent(**bridge)
    assert content.schema_ == "group-0"
    assert content.schemas_by_path == {"a.jsonl": "group-0", "b.jsonl": "group-1"}
    # nests inside FilesetMetadata and serializes by alias
    metadata = FilesetMetadata(dataset=content)
    dumped = metadata.model_dump(mode="json")
    assert dumped["dataset"]["schema"] == "group-0"
