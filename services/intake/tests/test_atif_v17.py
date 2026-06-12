# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ATIF v1.7 domain and mapper tests."""

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from nmp.intake.spans.api.spans_schemas import Span
from nmp.intake.spans.domain import SpanStatus
from nmp.intake.spans.ingest.atif import AtifIngestRequest
from nmp.intake.spans.ingest.atif_domain import (
    AtifAgent,
    AtifStepAgent,
    AtifStepUser,
    AtifSubagentTrajectoryRef,
    AtifTrajectory,
)
from nmp.intake.spans.ingest.atif_mapping import trajectory_to_spans
from nmp.intake.spans.ingest.evaluation_context import EvaluationContext, ExperimentContext
from pydantic import ValidationError

EVALUATION_CONTEXT: dict[str, Any] = {
    "evaluation_id": "eval-sample-agent-baseline",
    "evaluation_sha": "abc132901",
    "evaluation_run_id": "evalrun-01JZ8Q7K6V7R3X9N2M4P5A6B7C",
    "test_case_id": "sample-test-case",
    "metadata": {"attempt": 1},
}


def test_atif_v17_models_accept_new_fields() -> None:
    trajectory = AtifTrajectory.model_validate(
        {
            "schema_version": "ATIF-v1.7",
            "session_id": "trace-session-id",
            "trajectory_id": "root-trajectory",
            "agent": {"name": "sample-agent", "version": "1.0.0"},
            "steps": [
                {
                    "step_id": 1,
                    "source": "agent",
                    "message": "delegating",
                    "llm_call_count": 1,
                    "observation": {
                        "results": [
                            {
                                "content": "delegated",
                                "extra": {"retrieval_score": 0.92},
                                "subagent_trajectory_ref": [
                                    {"trajectory_id": "sub-trajectory", "session_id": "trace-session-id"}
                                ],
                            }
                        ]
                    },
                }
            ],
            "subagent_trajectories": [
                {
                    "schema_version": "ATIF-v1.7",
                    "session_id": "trace-session-id",
                    "trajectory_id": "sub-trajectory",
                    "agent": {"name": "subagent", "version": "1.0"},
                    "steps": [],
                }
            ],
        }
    )

    assert trajectory.schema_version == "ATIF-v1.7"
    assert trajectory.trajectory_id == "root-trajectory"
    assert trajectory.steps[0].llm_call_count == 1
    assert trajectory.subagent_trajectories is not None
    assert trajectory.subagent_trajectories[0].trajectory_id == "sub-trajectory"


def test_atif_v17_embedded_subagent_trajectories_are_preserved_but_not_expanded() -> None:
    trajectory = AtifTrajectory.model_validate(
        {
            "schema_version": "ATIF-v1.7",
            "session_id": "trace-session-id",
            "agent": {"name": "root", "version": "1.0"},
            "steps": [],
            "subagent_trajectories": [
                {
                    "schema_version": "ATIF-v1.7",
                    "session_id": "trace-session-id",
                    "trajectory_id": "sub-trajectory",
                    "agent": {"name": "subagent", "version": "1.0"},
                    "steps": [{"step_id": 1, "source": "user", "message": "subagent work"}],
                }
            ],
        }
    )

    spans = trajectory_to_spans(
        workspace="default",
        trajectory=trajectory,
        ingested_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )

    assert [span.name for span in spans] == ["root"]
    root_raw = json.loads(spans[0].attributes_string["atif.raw"])
    assert root_raw["subagent_trajectories"][0]["trajectory_id"] == "sub-trajectory"
    assert root_raw["subagent_trajectories"][0]["steps"][0]["message"] == "subagent work"


def test_atif_v17_subagent_ref_requires_resolution_key() -> None:
    with pytest.raises(ValidationError, match="trajectory_id, trajectory_path, or session_id"):
        AtifSubagentTrajectoryRef()

    assert AtifSubagentTrajectoryRef(session_id="trace-session-id").session_id == "trace-session-id"

    with pytest.raises(ValidationError, match="trajectory_id or trajectory_path"):
        AtifTrajectory.model_validate(
            {
                "schema_version": "ATIF-v1.7",
                "session_id": "trace-session-id",
                "agent": {"name": "root", "version": "1.0"},
                "steps": [
                    {
                        "step_id": 1,
                        "source": "agent",
                        "message": "delegating",
                        "observation": {
                            "results": [
                                {"subagent_trajectory_ref": [{"session_id": "trace-session-id"}]},
                            ]
                        },
                    }
                ],
            }
        )

    legacy = AtifTrajectory.model_validate(
        {
            "schema_version": "ATIF-v1.6",
            "session_id": "trace-session-id",
            "agent": {"name": "root", "version": "1.0"},
            "steps": [
                {
                    "step_id": 1,
                    "source": "agent",
                    "message": "delegating",
                    "observation": {
                        "results": [
                            {"subagent_trajectory_ref": [{"session_id": "trace-session-id"}]},
                        ]
                    },
                }
            ],
        }
    )
    assert isinstance(legacy.steps[0], AtifStepAgent)
    assert legacy.steps[0].observation is not None
    legacy_refs = legacy.steps[0].observation.results[0].subagent_trajectory_ref
    assert legacy_refs is not None
    legacy_ref = legacy_refs[0]
    assert legacy_ref.session_id == "trace-session-id"

    assert AtifSubagentTrajectoryRef(trajectory_id="sub-trajectory").trajectory_id == "sub-trajectory"
    assert AtifSubagentTrajectoryRef(trajectory_path="subagents/sub-trajectory.json").trajectory_path is not None


def test_experiment_context_maps_to_storage_context() -> None:
    context = ExperimentContext(experiment_id="exp-1", test_case_id="case-1")
    storage_context = context.to_evaluation_context()

    assert storage_context.evaluation_id == "exp-1"
    assert storage_context.evaluation_run_id is None
    assert storage_context.test_case_id == "case-1"


def test_deprecated_evaluation_context_accepts_missing_run_id() -> None:
    assert EvaluationContext() == EvaluationContext(metadata={})
    assert EvaluationContext(evaluation_run_id="evalrun-1").evaluation_run_id == "evalrun-1"
    assert EvaluationContext(evaluation_id="eval-1").evaluation_id == "eval-1"


def test_atif_ingest_request_rejects_legacy_top_level_project() -> None:
    body = {
        "schema_version": "ATIF-v1.7",
        "session_id": "trace-session-id",
        "project": "legacy-project",
        "agent": {"name": "sample-agent", "version": "1.0.0"},
        "steps": [],
    }

    with pytest.raises(ValidationError) as exc_info:
        AtifIngestRequest.model_validate(body)

    error_locations = {tuple(error["loc"]) for error in exc_info.value.errors()}
    assert ("project",) in error_locations


def test_atif_mapping_writes_evaluation_context_only_on_root_span() -> None:
    trajectory = AtifTrajectory(
        schema_version="ATIF-v1.5",
        session_id="trace-session-id",
        evaluation_context=EvaluationContext.model_validate(EVALUATION_CONTEXT),
        agent=AtifAgent(
            name="sample-agent",
            version="1.0.0",
            model_name="provider/sample-model",
        ),
        steps=[AtifStepUser(step_id=1, source="user", message="solve")],
    )

    spans = trajectory_to_spans(
        workspace="default",
        trajectory=trajectory,
        ingested_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )

    root = next(span for span in spans if span.name == "sample-agent")
    child = next(span for span in spans if span.name == "user-1")
    assert root.attributes_string["nemo.experiment.id"] == EVALUATION_CONTEXT["evaluation_id"]
    assert root.attributes_string["nemo.experiment.sha"] == EVALUATION_CONTEXT["evaluation_sha"]
    assert root.attributes_string["nemo.experiment.run_id"] == EVALUATION_CONTEXT["evaluation_run_id"]
    assert "evaluation.id" not in root.attributes_string
    assert root.attributes_string["nemo.test_case.id"] == EVALUATION_CONTEXT["test_case_id"]
    assert json.loads(root.attributes_string["nemo.experiment.metadata"]) == EVALUATION_CONTEXT["metadata"]

    root_response = Span.from_domain(root)
    assert root_response.evaluation_context is not None
    assert root_response.evaluation_context.evaluation_id == EVALUATION_CONTEXT["evaluation_id"]
    assert root_response.evaluation_context.evaluation_sha == EVALUATION_CONTEXT["evaluation_sha"]
    assert root_response.evaluation_context.evaluation_run_id == EVALUATION_CONTEXT["evaluation_run_id"]
    assert root_response.evaluation_context.test_case_id == EVALUATION_CONTEXT["test_case_id"]
    assert root_response.evaluation_context.metadata == EVALUATION_CONTEXT["metadata"]
    assert root_response.raw_attributes is not None
    root_raw = json.loads(root_response.raw_attributes)
    assert "evaluation_context" not in root_raw
    assert "evaluation.metadata" not in root_raw
    assert "nemo.experiment.metadata" not in root_raw

    child_response = Span.from_domain(child)
    assert child_response.evaluation_context is None
    assert "evaluation.id" not in child.attributes_string
    assert "nemo.experiment.id" not in child.attributes_string
    assert "nemo.test_case.id" not in child.attributes_string


def test_atif_mapping_writes_experiment_context_to_experiment_attributes() -> None:
    body = AtifIngestRequest.model_validate(
        {
            "schema_version": "ATIF-v1.7",
            "session_id": "trace-session-id",
            "experiment_context": {"experiment_id": "exp-1", "test_case_id": "case-1"},
            "agent": {"name": "sample-agent", "version": "1.0.0"},
            "steps": [{"step_id": 1, "source": "user", "message": "solve"}],
        }
    )

    spans = trajectory_to_spans(
        workspace="default",
        trajectory=body.to_trajectory(),
        ingested_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )

    root = next(span for span in spans if span.name == "sample-agent")
    assert root.attributes_string["nemo.experiment.id"] == "exp-1"
    assert root.attributes_string["nemo.test_case.id"] == "case-1"
    assert "evaluation.id" not in root.attributes_string


def test_atif_mapping_uses_root_final_metrics_when_steps_have_no_metrics() -> None:
    trajectory = AtifTrajectory.model_validate(
        {
            "schema_version": "ATIF-v1.7",
            "session_id": "trace-session-id",
            "agent": {"name": "sample-agent", "version": "1.0.0"},
            "steps": [
                {"step_id": 1, "source": "user", "message": "solve the task"},
                {"step_id": 2, "source": "agent", "message": "final answer"},
            ],
            "final_metrics": {
                "total_prompt_tokens": 10,
                "total_completion_tokens": 5,
                "total_cached_tokens": 2,
                "total_cost_usd": 0.25,
            },
        }
    )

    spans = trajectory_to_spans(
        workspace="default",
        trajectory=trajectory,
        ingested_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )

    root_response = Span.from_domain(spans[0])
    child_response = Span.from_domain(next(span for span in spans if span.name == "agent-2"))
    assert root_response.input_tokens == 10
    assert root_response.output_tokens == 5
    assert root_response.cached_tokens == 2
    assert root_response.total_tokens == 15
    assert root_response.cost_total_usd == 0.25
    assert child_response.input_tokens is None
    assert child_response.cost_total_usd is None


def test_atif_mapping_does_not_duplicate_final_metrics_when_step_metrics_exist() -> None:
    trajectory = AtifTrajectory.model_validate(
        {
            "schema_version": "ATIF-v1.7",
            "session_id": "trace-session-id",
            "agent": {"name": "sample-agent", "version": "1.0.0"},
            "steps": [
                {"step_id": 1, "source": "user", "message": "solve the task"},
                {
                    "step_id": 2,
                    "source": "agent",
                    "message": "final answer",
                    "metrics": {"prompt_tokens": 3, "completion_tokens": 2, "cost_usd": 0.04},
                },
            ],
            "final_metrics": {
                "total_prompt_tokens": 10,
                "total_completion_tokens": 5,
                "total_cost_usd": 0.25,
            },
        }
    )

    spans = trajectory_to_spans(
        workspace="default",
        trajectory=trajectory,
        ingested_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )

    root_response = Span.from_domain(spans[0])
    child_response = Span.from_domain(next(span for span in spans if span.name == "agent-2"))
    assert root_response.input_tokens is None
    assert root_response.output_tokens is None
    assert root_response.cost_total_usd is None
    assert child_response.input_tokens == 3
    assert child_response.output_tokens == 2
    assert child_response.total_tokens == 5
    assert child_response.cost_total_usd == 0.04


def test_atif_mapping_uses_root_cost_when_step_metrics_have_tokens_only() -> None:
    trajectory = AtifTrajectory.model_validate(
        {
            "schema_version": "ATIF-v1.7",
            "session_id": "trace-session-id",
            "agent": {"name": "sample-agent", "version": "1.0.0"},
            "steps": [
                {"step_id": 1, "source": "user", "message": "solve the task"},
                {
                    "step_id": 2,
                    "source": "agent",
                    "message": "final answer",
                    "metrics": {"prompt_tokens": 3, "completion_tokens": 2, "cached_tokens": 1},
                },
            ],
            "final_metrics": {
                "total_prompt_tokens": 10,
                "total_completion_tokens": 5,
                "total_cached_tokens": 2,
                "total_cost_usd": 0.25,
            },
        }
    )

    spans = trajectory_to_spans(
        workspace="default",
        trajectory=trajectory,
        ingested_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )

    root_response = Span.from_domain(spans[0])
    child_response = Span.from_domain(next(span for span in spans if span.name == "agent-2"))
    assert root_response.input_tokens is None
    assert root_response.output_tokens is None
    assert root_response.cached_tokens is None
    assert root_response.cost_total_usd == 0.25
    assert child_response.input_tokens == 3
    assert child_response.output_tokens == 2
    assert child_response.cached_tokens == 1
    assert child_response.cost_total_usd is None


def test_atif_mapping_populates_root_content_and_rolls_child_errors() -> None:
    trajectory = AtifTrajectory.model_validate(
        {
            "schema_version": "ATIF-v1.7",
            "session_id": "trace-session-id",
            "agent": {"name": "sample-agent", "version": "1.0.0"},
            "steps": [
                {"step_id": 1, "source": "user", "message": "solve the task"},
                {
                    "step_id": 2,
                    "source": "agent",
                    "message": "using a tool",
                    "tool_calls": [{"tool_call_id": "call-1", "function_name": "Bash"}],
                    "observation": {
                        "results": [
                            {
                                "source_call_id": "call-1",
                                "content": "Exit code 1\n[error] failed",
                            }
                        ]
                    },
                },
                {"step_id": 3, "source": "agent", "message": "final answer"},
            ],
        }
    )

    spans = trajectory_to_spans(
        workspace="default",
        trajectory=trajectory,
        ingested_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )

    root = spans[0]
    assert root.name == "sample-agent"
    assert root.input == "solve the task"
    assert root.output == "final answer"
    assert root.status == SpanStatus.ERROR


def test_atif_mapping_span_ids_are_trace_native_and_ignore_evaluation_run_id() -> None:
    base = {
        "schema_version": "ATIF-v1.5",
        "session_id": "trace-session-id",
        "agent": {"name": "sample-agent", "version": "1.0.0"},
        "steps": [{"step_id": 1, "source": "user", "message": "solve"}],
    }
    first = AtifTrajectory.model_validate(
        {**base, "evaluation_context": {**EVALUATION_CONTEXT, "evaluation_run_id": "evalrun-a"}}
    )
    second = AtifTrajectory.model_validate(
        {**base, "evaluation_context": {**EVALUATION_CONTEXT, "evaluation_run_id": "evalrun-b"}}
    )

    ingested_at = datetime(2026, 5, 18, tzinfo=timezone.utc)
    first_ids = {
        span.name: span.external_span_id
        for span in trajectory_to_spans(workspace="default", trajectory=first, ingested_at=ingested_at)
    }
    second_ids = {
        span.name: span.external_span_id
        for span in trajectory_to_spans(workspace="default", trajectory=second, ingested_at=ingested_at)
    }

    assert first_ids == second_ids
