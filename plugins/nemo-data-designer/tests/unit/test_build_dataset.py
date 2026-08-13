# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

import pandas as pd
import pytest
from nemo_data_designer_plugin.jobs.build_dataset import (
    DATASET_CONTRACT,
    DATASET_DATA_PATH,
    AgentEvalDatasetRow,
    BuildDatasetConfig,
    run_build_dataset,
)
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.files.metadata import FilesetMetadata
from nemo_platform_plugin.job_context import JobContext


class _Result:
    def __init__(self, name: str, value: float) -> None:
        self.name = name
        self.value = value

    def to_dict(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {"name": self.name, "value": self.value, "data_type": "numeric"}


class _FilesClient:
    def __init__(self) -> None:
        self.filesets: dict[tuple[str, str], SimpleNamespace] = {}
        self.deleted: list[tuple[str, str]] = []

    def create_fileset(self, *, workspace: str, body) -> SimpleNamespace:
        key = (workspace, body.name)
        if key in self.filesets:
            raise RuntimeError("fileset already exists")
        output = SimpleNamespace(
            name=body.name,
            workspace=workspace,
            purpose=body.purpose,
            metadata=body.metadata,
            custom_fields=body.custom_fields,
        )
        self.filesets[key] = output
        return output

    def get_fileset(self, *, workspace: str, name: str) -> SimpleNamespace:
        fileset = self.filesets[(workspace, name)]
        return SimpleNamespace(data=lambda: fileset)

    def delete_fileset(self, *, workspace: str, name: str) -> SimpleNamespace:
        self.deleted.append((workspace, name))
        return self.filesets.pop((workspace, name))


class _Files:
    def __init__(self) -> None:
        self.client = _FilesClient()
        self.content: dict[tuple[str, str, str], bytes] = {}
        self.fail_path: str | None = None

    def upload_content(self, *, content, remote_path: str, fileset: str, workspace: str):
        if remote_path == self.fail_path:
            raise RuntimeError("upload failed")
        payload = content.encode() if isinstance(content, str) else bytes(content)
        self.content[(workspace, fileset, remote_path)] = payload
        return self.client.get_fileset(workspace=workspace, name=fileset).data()

    def download_content(self, *, remote_path: str, fileset: str, workspace: str) -> bytes:
        return self.content[(workspace, fileset, remote_path)]


class _SDK:
    def __init__(self) -> None:
        self.files = _Files()
        trace = SimpleNamespace(
            id="trace-1",
            root_span_id="span-1",
            session_id="session-1",
            agent_name="tea",
            input="Make tea",
            output="Tea is ready",
            status="success",
            started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
            evaluation_context=SimpleNamespace(evaluation_id="eval-1", test_case_id="case-1"),
        )
        root_span = SimpleNamespace(
            agent_name="tea",
            raw_attributes=json.dumps({"extra": {"oracle": {"outcome": "success"}}}),
        )
        self.intake = SimpleNamespace(
            traces=SimpleNamespace(retrieve=lambda *_args, **_kwargs: trace),
            spans=SimpleNamespace(
                retrieve=lambda *_args, **_kwargs: root_span,
                evaluator_results=SimpleNamespace(list=lambda *_args, **_kwargs: [_Result("default/quality", 1.0)]),
            ),
        )


def _trace_config(name: str = "tea-traces") -> BuildDatasetConfig:
    return BuildDatasetConfig.model_validate(
        {
            "destination": {"name": name},
            "source": {
                "kind": "intake-traces",
                "agent_name": "tea",
                "trace_ids": ["trace-1"],
                "grader_refs": ["default/testcrew-tea-quality-v1"],
            },
        }
    )


def _rows(files: _Files, fileset: str) -> list[dict[str, object]]:
    content = files.content[("default", fileset, DATASET_DATA_PATH)]
    return pd.read_parquet(io.BytesIO(content)).to_dict(orient="records")


def _run(config: BuildDatasetConfig, sdk: _SDK) -> dict[str, object]:
    return run_build_dataset(
        config,
        ctx=cast(JobContext, SimpleNamespace(workspace="default")),
        sdk=cast(NeMoPlatform, sdk),
    )


def test_trace_selection_requires_unique_trace_ids() -> None:
    with pytest.raises(ValueError, match="trace_ids must be unique"):
        BuildDatasetConfig.model_validate(
            {
                "destination": {"name": "bad"},
                "source": {
                    "kind": "intake-traces",
                    "agent_name": "tea",
                    "trace_ids": ["trace-1", "trace-1"],
                },
            }
        )


def test_builds_reviewable_dataset_from_selected_traces() -> None:
    sdk = _SDK()

    result = _run(_trace_config(), sdk)

    assert result["exit_code"] == 0
    assert result["dataset_ref"] == "default/tea-traces"
    assert result["record_count"] == 1
    [row] = _rows(sdk.files, "tea-traces")
    parsed = AgentEvalDatasetRow.model_validate(row)
    assert parsed.instruction == "Make tea"
    assert parsed.observed_output == "Tea is ready"
    assert json.loads(parsed.reference) == {"oracle": {"outcome": "success"}}
    assert json.loads(parsed.grader_refs) == ["default/testcrew-tea-quality-v1"]
    assert json.loads(parsed.grader_results)[0]["name"] == "default/quality"
    assert json.loads(parsed.lineage)[0]["ref"] == "default/trace-1"

    fileset = sdk.files.client.get_fileset(workspace="default", name="tea-traces").data()
    assert fileset.custom_fields["dataset.contract"] == DATASET_CONTRACT
    metadata = fileset.metadata.dataset
    assert metadata.record_count == 1
    assert metadata.data_path == DATASET_DATA_PATH
    assert metadata.grader_refs == ["default/testcrew-tea-quality-v1"]
    assert metadata.lineage.sources[0].attributes == {"agent_name": "tea"}


def test_recovers_input_and_final_output_from_raw_atif_messages() -> None:
    sdk = _SDK()
    trace = sdk.intake.traces.retrieve(None)
    trace.input = None
    trace.output = '{"tool_calls": [{"function_name": "LangGraph"}]}'
    root_span = sdk.intake.spans.retrieve(None)
    root_span.raw_attributes = json.dumps(
        {
            "schema_version": "ATIF-v1.7",
            "extra": {
                "observed_events": [
                    {"data": {"messages": [{"role": "user", "content": "What is 144 / 12?"}]}},
                    {
                        "data": {
                            "messages": [
                                {"data": {"type": "human", "content": "What is 144 / 12?"}},
                                {"data": {"type": "ai", "content": "12"}},
                            ]
                        }
                    },
                ]
            },
        }
    )

    result = _run(_trace_config(), sdk)

    assert result["exit_code"] == 0
    [row] = _rows(sdk.files, "tea-traces")
    assert row["instruction"] == "What is 144 / 12?"
    assert row["observed_output"] == "12"


def test_rejects_trace_from_a_different_agent() -> None:
    sdk = _SDK()
    sdk.intake.traces.retrieve(None).agent_name = "planner"

    result = _run(_trace_config(), sdk)

    assert result["exit_code"] == 1
    assert "belongs to agent 'planner'" in str(result["error"])
    assert sdk.files.client.filesets == {}


def test_composes_agent_datasets_and_preserves_row_lineage() -> None:
    sdk = _SDK()
    assert _run(_trace_config("tea-a"), sdk)["exit_code"] == 0
    assert _run(_trace_config("tea-b"), sdk)["exit_code"] == 0

    config = BuildDatasetConfig.model_validate(
        {
            "destination": {"name": "qa-catalog"},
            "source": {"kind": "datasets", "datasets": ["default/tea-a", "default/tea-b"]},
        }
    )
    result = _run(config, sdk)

    assert result["exit_code"] == 0
    assert result["record_count"] == 1
    [row] = _rows(sdk.files, "qa-catalog")
    lineage = json.loads(str(row["lineage"]))
    assert {item["ref"] for item in lineage if item["kind"] == "dataset"} == {
        "default/tea-a",
        "default/tea-b",
    }
    metadata = sdk.files.client.get_fileset(workspace="default", name="qa-catalog").data().metadata.dataset
    assert [item.ref for item in metadata.lineage.sources] == ["default/tea-a", "default/tea-b"]


def test_partial_publish_is_rolled_back() -> None:
    sdk = _SDK()
    sdk.files.fail_path = DATASET_DATA_PATH

    result = _run(_trace_config(), sdk)

    assert result["exit_code"] == 1
    assert sdk.files.client.deleted == [("default", "tea-traces")]
    assert sdk.files.client.filesets == {}


def test_dataset_metadata_remains_backward_compatible() -> None:
    metadata = FilesetMetadata.model_validate({"dataset": {"schema": {"type": "object"}}})

    assert metadata.dataset is not None
    assert metadata.dataset.data_path is None
    assert metadata.dataset.record_count is None
    assert metadata.dataset.grader_refs == []
    assert metadata.dataset.lineage is None
