# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility-contract tests for Experimentalist evaluator models."""

import json
import warnings

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDependencyRuntime
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    CommandSpec,
    DatasetRef,
    DependencyRuntime,
    EvaluationResult,
    MetricResult,
    MetricSpec,
    ResourceRef,
    Task,
    TrialResult,
)
from pydantic import BaseModel

_TRIAL_RESULT_SCHEMA_METADATA = {
    "deprecated": True,
    "x-nemo-contract-status": "legacy",
    "x-nemo-coordination-required": True,
    "x-nemo-migration-target": "nemo_evaluator_sdk.agent_eval.trials.AgentEvalTrial",
    "x-nemo-migration-kind": "adapter",
    "x-nemo-migration-blockers": [
        "Retire the harbor_native evaluator.",
        "Preserve full Harbor exception_info in AgentEvalTrial metadata.",
        "Replace the shared job-directory adapter without changing trial semantics.",
    ],
}

_EVALUATION_RESULT_SCHEMA_METADATA = {
    "deprecated": True,
    "x-nemo-contract-status": "legacy",
    "x-nemo-coordination-required": True,
    "x-nemo-migration-target": "nemo_evaluator_sdk.agent_eval.results.AgentEvalResult",
    "x-nemo-migration-kind": "end-to-end",
    "x-nemo-migration-blockers": [
        "Complete the TrialResult migration.",
        "Migrate Evaluator.run(), aggregation, analyzers, ranking, and persisted candidate details.",
        "Define adoption of SDK scoring and summary semantics.",
    ],
}

_TRIAL_RESULT_JSON = {
    "id": "task-a__attempt-2",
    "task_id": "task-a",
    "attempt": 2,
    "status": "failed",
    "trace": {
        "uri": "file:///tmp/trace.jsonl",
        "description": "Agent trace",
        "metadata": {"format": "jsonl"},
    },
    "outputs": {"answer": "42"},
    "resources": {
        "workspace": {
            "uri": "file:///tmp/workspace",
            "description": "Final workspace",
            "metadata": {"kind": "directory"},
        }
    },
    "metrics": {
        "reward": {
            "name": "reward",
            "value": 0.0,
            "spec": {
                "name": "reward",
                "description": "Primary Harbor reward.",
                "ref": None,
            },
            "metadata": {"source": "harbor"},
        },
        "format_ok": {
            "name": "format_ok",
            "value": 1,
            "spec": None,
            "metadata": {},
        },
    },
    "error": {
        "type": "RuntimeError",
        "message": "agent failed",
        "traceback": "RuntimeError: agent failed",
    },
    "metadata": {"harbor_trial_dir": "/tmp/job/task-a__attempt-2"},
}


def _trial_result() -> TrialResult:
    return TrialResult.model_validate(_TRIAL_RESULT_JSON)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        pytest.param(TrialResult, _TRIAL_RESULT_SCHEMA_METADATA, id="trial-result"),
        pytest.param(EvaluationResult, _EVALUATION_RESULT_SCHEMA_METADATA, id="evaluation-result"),
    ],
)
def test_legacy_result_models_expose_coordination_metadata(
    model: type[BaseModel],
    expected: dict[str, object],
) -> None:
    """Removing or weakening the CI-visible legacy marker must require an intentional test edit."""
    schema = model.model_json_schema()

    assert {key: schema[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("model", "field_order", "required_fields"),
    [
        pytest.param(
            TrialResult,
            ["id", "task_id", "attempt", "status", "trace", "outputs", "resources", "metrics", "error", "metadata"],
            ["id", "task_id", "status"],
            id="trial-result",
        ),
        pytest.param(
            EvaluationResult,
            ["id", "aggregate_metrics", "trials", "metadata"],
            ["id"],
            id="evaluation-result",
        ),
    ],
)
def test_legacy_result_model_shape_is_locked(
    model: type[BaseModel],
    field_order: list[str],
    required_fields: list[str],
) -> None:
    """Accidental field additions, removals, reordering, or requiredness changes must fail CI."""
    assert list(model.model_fields) == field_order
    assert [name for name, field in model.model_fields.items() if field.is_required()] == required_fields


def test_legacy_result_models_round_trip_the_persisted_json_contract() -> None:
    """Nested resources, metrics, and errors must retain their persisted representation."""
    trial = _trial_result()
    evaluation = EvaluationResult(
        id="evaluation-1",
        aggregate_metrics={"reward": 0.0, "format_ok": 1},
        trials=[trial],
        metadata={"split": "validation"},
    )
    evaluation_json = {
        "id": "evaluation-1",
        "aggregate_metrics": {"reward": 0.0, "format_ok": 1},
        "trials": [_TRIAL_RESULT_JSON],
        "metadata": {"split": "validation"},
    }

    assert trial.model_dump(mode="json") == _TRIAL_RESULT_JSON
    assert TrialResult.model_validate_json(json.dumps(_TRIAL_RESULT_JSON)).model_dump(mode="json") == _TRIAL_RESULT_JSON
    assert evaluation.model_dump(mode="json") == evaluation_json
    assert EvaluationResult.model_validate_json(json.dumps(evaluation_json)).model_dump(mode="json") == evaluation_json


def test_legacy_result_models_do_not_warn_at_runtime() -> None:
    """Static schema deprecation must not add warning noise to optimization runs."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        trial = _trial_result()
        EvaluationResult(id="evaluation-1", trials=[trial]).model_dump_json()


@pytest.mark.parametrize(
    "model",
    [
        ResourceRef,
        CommandSpec,
        DependencyRuntime,
        MetricSpec,
        MetricResult,
        Task,
        DatasetRef,
        HarborDependencyRuntime,
    ],
)
def test_active_evaluator_models_are_not_deprecated(model: type[BaseModel]) -> None:
    """Active Experimentalist-specific models must not inherit the result-contract marker."""
    assert model.model_json_schema().get("deprecated") is not True
