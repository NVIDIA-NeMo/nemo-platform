# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minimal public models for Eval Author artifacts."""

from pathlib import Path

import pytest
from nemo_eval_author_plugin.eval_author import models
from nemo_eval_author_plugin.eval_author.models import (
    ArtifactDescriptor,
    EvalAuthorResult,
    MetricAuthoringResult,
)
from pydantic import ValidationError


def _artifact(name: str, digest: str) -> ArtifactDescriptor:
    return ArtifactDescriptor(uri=f"file:///artifacts/{name}", identity=f"sha256:{digest * 64}")


def test_overdesigned_public_models_and_inventory_module_are_absent() -> None:
    removed_models = {
        "AuthoredMetric",
        "AuthoredMetricContract",
        "EvalAuthorEvaluationContext",
        "EvalAuthorRequest",
        "FrozenJsonObject",
        "InsightRef",
        "ReadOnlyDatasetRef",
    }

    assert removed_models.isdisjoint(vars(models))
    assert not (Path(models.__file__).with_name("inventory.py")).exists()


def test_minimal_models_are_json_safe() -> None:
    authored = MetricAuthoringResult(
        metric_keys=("uses_correct_tool",),
        summary="Added a tool-use metric.",
    )
    result = EvalAuthorResult(
        task_set=_artifact("task-set", "a"),
        verifier_bundle=_artifact("verifier-bundle", "b"),
        metric_keys=authored.metric_keys,
        summary=authored.summary,
    )

    assert set(ArtifactDescriptor.model_fields) == {"uri", "identity"}
    assert set(MetricAuthoringResult.model_fields) == {"metric_keys", "summary"}
    assert set(EvalAuthorResult.model_fields) == {
        "task_set",
        "verifier_bundle",
        "metric_keys",
        "summary",
    }
    assert EvalAuthorResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "metric_keys",
    [
        (),
        ("",),
        ("uses_correct_tool", "uses_correct_tool"),
        ("reward", "score"),
    ],
)
def test_metric_authoring_requires_unique_non_generic_keys(metric_keys: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        MetricAuthoringResult(metric_keys=metric_keys, summary="Authored metrics.")


def test_eval_author_result_explicitly_supports_no_artifacts() -> None:
    result = EvalAuthorResult.no_artifacts("No trace refs on insight.")

    assert result.task_set is None
    assert result.verifier_bundle is None
    assert result.metric_keys == ()
    assert result.summary == "No trace refs on insight."


def test_eval_author_result_requires_both_artifacts_and_declared_metrics() -> None:
    with pytest.raises(ValidationError):
        EvalAuthorResult(
            task_set=_artifact("task-set", "a"),
            verifier_bundle=None,
            metric_keys=("uses_correct_tool",),
            summary="Incomplete.",
        )
    with pytest.raises(ValidationError):
        EvalAuthorResult(
            task_set=_artifact("task-set", "a"),
            verifier_bundle=_artifact("verifier-bundle", "b"),
            metric_keys=("reward",),
            summary="Generic only.",
        )
