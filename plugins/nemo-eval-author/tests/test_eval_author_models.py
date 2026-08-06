# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minimal public models for Eval Author artifacts."""

from pathlib import Path

import pytest
from nemo_eval_author_plugin.eval_author import models
from nemo_eval_author_plugin.eval_author.models import EvalAuthorResult, MetricAuthoringResult
from nemo_experimentalist_plugin.entities import Dataset
from pydantic import ValidationError


def _dataset(name: str) -> Dataset:
    return Dataset(id=name)


def test_overdesigned_public_models_and_inventory_module_are_absent() -> None:
    removed_models = {
        "AuthoredMetric",
        "AuthoredMetricContract",
        "ArtifactDescriptor",
        "EvalAuthorEvaluationContext",
        "EvalAuthorRequest",
        "FrozenJsonObject",
        "InsightRef",
        "ReadOnlyDatasetRef",
    }

    assert removed_models.isdisjoint(vars(models))
    assert not (Path(models.__file__).with_name("inventory.py")).exists()


def test_result_returns_the_same_dataset_objects() -> None:
    authored = MetricAuthoringResult(
        metric_keys=("uses_correct_tool",),
        summary="Added a tool-use metric.",
    )
    train_dataset = _dataset("train")
    validation_dataset = _dataset("validation")
    insight_suite = _dataset("insight")
    result = EvalAuthorResult(
        train_dataset=train_dataset,
        validation_dataset=validation_dataset,
        insight_suite=insight_suite,
        insight_suite_identity=f"sha256:{'a' * 64}",
        metric_keys=authored.metric_keys,
        summary=authored.summary,
    )

    assert set(MetricAuthoringResult.model_fields) == {"metric_keys", "summary"}
    assert set(EvalAuthorResult.model_fields) == {
        "train_dataset",
        "validation_dataset",
        "insight_suite",
        "insight_suite_identity",
        "metric_keys",
        "summary",
    }
    assert result.train_dataset is train_dataset
    assert result.validation_dataset is validation_dataset
    assert result.insight_suite is insight_suite


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


def test_eval_author_result_supports_unchanged_datasets_without_authored_tasks() -> None:
    result = EvalAuthorResult(
        train_dataset=_dataset("train"),
        validation_dataset=_dataset("validation"),
        summary="No trace refs on insight.",
    )

    assert result.insight_suite is None
    assert result.insight_suite_identity is None
    assert result.metric_keys == ()
    assert result.summary == "No trace refs on insight."


def test_eval_author_result_stores_normalized_metric_keys() -> None:
    result = EvalAuthorResult(
        train_dataset=_dataset("train"),
        validation_dataset=_dataset("validation"),
        insight_suite=_dataset("insight"),
        insight_suite_identity=f"sha256:{'a' * 64}",
        metric_keys=("  uses_correct_tool  ",),
        summary="Normalized keys.",
    )

    assert result.metric_keys == ("uses_correct_tool",)


def test_eval_author_result_requires_suite_identity_and_declared_metrics_together() -> None:
    with pytest.raises(ValidationError):
        EvalAuthorResult(
            train_dataset=_dataset("train"),
            validation_dataset=_dataset("validation"),
            metric_keys=("uses_correct_tool",),
            summary="Incomplete.",
        )
    with pytest.raises(ValidationError):
        EvalAuthorResult(
            train_dataset=_dataset("train"),
            validation_dataset=_dataset("validation"),
            insight_suite=_dataset("insight"),
            metric_keys=("uses_correct_tool",),
            summary="Missing identity.",
        )
    with pytest.raises(ValidationError):
        EvalAuthorResult(
            train_dataset=_dataset("train"),
            validation_dataset=_dataset("validation"),
            insight_suite=_dataset("insight"),
            insight_suite_identity=f"sha256:{'a' * 64}",
            metric_keys=("reward",),
            summary="Generic only.",
        )
    with pytest.raises(ValidationError):
        EvalAuthorResult(
            train_dataset=_dataset("train"),
            validation_dataset=_dataset("validation"),
            insight_suite=_dataset("insight"),
            insight_suite_identity=f"sha256:{'a' * 64}",
            summary="Missing metric keys.",
        )
