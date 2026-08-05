# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Serializable contract tests for Eval Author requests and results."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from nemo_eval_author_plugin.eval_author.models import (
    ArtifactDescriptor,
    AuthoredMetric,
    AuthoredMetricContract,
    EvalAuthorEvaluationContext,
    EvalAuthorRequest,
    EvalAuthorResult,
    FrozenJsonObject,
    InsightRef,
    MetricAuthoringResult,
)
from nemo_experimentalist_plugin.entities import DatasetRef, ResourceRef
from pydantic import TypeAdapter, ValidationError


def _metric(key: str = "uses_inventory_lookup") -> AuthoredMetric:
    return AuthoredMetric(
        key=key,
        description="Measures whether the agent consulted live inventory before answering.",
        runtime_evidence=("OTLP tool spans under /logs/artifacts/traces",),
    )


def test_eval_author_request_round_trips_through_cli_safe_json() -> None:
    source_insight = ResourceRef(uri="insight://workspace-a/insight-123")
    request = EvalAuthorRequest(
        insight=source_insight,
        evaluation_context=EvalAuthorEvaluationContext(
            task_template=DatasetRef(uri="fileset://workspace-a/templates/inventory"),
            reference_task_sets=(
                DatasetRef(uri="fileset://workspace-a/benchmarks/a", metadata={"split": "train"}),
                DatasetRef(uri="fileset://workspace-a/benchmarks/b", metadata={"split": "validation"}),
            ),
        ),
    )

    payload = request.model_dump_json()
    restored = EvalAuthorRequest.model_validate_json(payload)

    assert restored == request
    assert isinstance(restored.insight, InsightRef)
    assert json.loads(payload) == request.model_dump(mode="json")
    assert EvalAuthorRequest.model_json_schema()["type"] == "object"
    assert restored.evaluation_context.reference_task_sets == request.evaluation_context.reference_task_sets
    source_insight.uri = "insight://workspace-a/changed"
    assert request.insight.uri == "insight://workspace-a/insight-123"
    with pytest.raises(ValidationError, match="frozen"):
        request.insight.uri = "insight://workspace-a/mutated"  # type: ignore[misc]


def test_evaluation_context_is_immutable_and_split_agnostic() -> None:
    source_reference = DatasetRef(uri="file:///reference-a")
    context = EvalAuthorEvaluationContext(
        task_template=DatasetRef(uri="file:///task-template"),
        reference_task_sets=(source_reference, DatasetRef(uri="file:///reference-b")),
    )

    assert isinstance(context.reference_task_sets, tuple)
    assert all(isinstance(reference, DatasetRef) for reference in context.reference_task_sets)
    assert set(type(context).model_fields) == {"task_template", "reference_task_sets"}
    with pytest.raises(ValidationError, match="frozen"):
        context.reference_task_sets = ()  # type: ignore[misc]
    with pytest.raises(ValidationError, match="frozen"):
        context.reference_task_sets[0].uri = "file:///mutated"  # type: ignore[misc]
    source_reference.uri = "file:///changed-outside-context"
    assert context.reference_task_sets[0].uri == "file:///reference-a"


def test_request_metadata_is_deeply_immutable_and_defensively_copied() -> None:
    caller_metadata = {
        "nested": {
            "items": [
                {"name": "first", "enabled": True},
            ]
        }
    }
    source_reference = DatasetRef(uri="file:///reference", metadata=caller_metadata)
    request = EvalAuthorRequest(
        insight=ResourceRef(uri="insight-123", metadata=caller_metadata),
        evaluation_context=EvalAuthorEvaluationContext(
            task_template=DatasetRef(uri="file:///template", metadata=caller_metadata),
            reference_task_sets=(source_reference,),
        ),
    )

    cast(dict[str, object], cast(dict[str, object], caller_metadata["nested"])["items"][0])["name"] = "changed"
    cast(dict[str, object], cast(dict[str, object], source_reference.metadata["nested"])["items"][0])["enabled"] = False

    dumped = request.model_dump(mode="json")
    assert dumped["insight"]["metadata"]["nested"]["items"] == [{"enabled": True, "name": "first"}]
    nested = cast(Mapping[str, object], request.evaluation_context.reference_task_sets[0].metadata["nested"])
    items = cast(tuple[object, ...], nested["items"])
    first = cast(Mapping[str, object], items[0])
    with pytest.raises(TypeError):
        first["name"] = "mutated"  # type: ignore[index]
    with pytest.raises(AttributeError):
        items.append("mutated")  # type: ignore[attr-defined]
    assert EvalAuthorRequest.model_validate_json(request.model_dump_json()) == request


@pytest.mark.parametrize(
    "invalid_metadata",
    [
        {"nested": {"path": Path("/not-json")}},
        {"nested": {"not_finite": float("nan")}},
        {"nested": {"tuple": ("not", "json")}},
    ],
)
def test_request_rejects_non_json_metadata(invalid_metadata: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="JSON"):
        EvalAuthorRequest(
            insight={"uri": "insight-123", "metadata": invalid_metadata},
            evaluation_context={
                "task_template": {"uri": "file:///template"},
                "reference_task_sets": [],
            },
        )


def test_frozen_json_public_constructor_canonicalizes_and_copies_nested_values() -> None:
    caller_value = {
        "z": [{"enabled": True, "name": "first"}],
        "a": {"count": 1},
    }

    frozen = FrozenJsonObject(caller_value)
    cast(dict[str, object], cast(list[object], caller_value["z"])[0])["name"] = "changed"
    cast(dict[str, object], caller_value["a"])["count"] = 2

    assert frozen.to_json() == {
        "a": {"count": 1},
        "z": [{"enabled": True, "name": "first"}],
    }
    nested_list = cast(tuple[object, ...], frozen["z"])
    with pytest.raises(AttributeError):
        nested_list.append("mutated")  # type: ignore[attr-defined]
    adapter = TypeAdapter(FrozenJsonObject)
    assert adapter.validate_json(adapter.dump_json(frozen)) == frozen


@pytest.mark.parametrize(
    "invalid_value",
    [
        {"path": Path("/not-json")},
        {"not_finite": float("inf")},
        {"tuple": ("not", "json")},
        {1: "non-string-key"},
        ["not", "a", "json-object"],
    ],
)
def test_frozen_json_public_constructor_rejects_non_json_values(
    invalid_value: object,
) -> None:
    with pytest.raises(ValueError, match="JSON"):
        FrozenJsonObject(cast(Mapping[object, object], invalid_value))


def test_frozen_json_validation_revalidates_preexisting_instances() -> None:
    forged = object.__new__(FrozenJsonObject)
    object.__setattr__(forged, "_items", (("mutable", {"bad": Path("/not-json")}),))

    with pytest.raises(ValueError, match="JSON"):
        FrozenJsonObject(forged)
    with pytest.raises(ValidationError, match="JSON"):
        EvalAuthorRequest(
            insight={"uri": "insight-123", "metadata": forged},
            evaluation_context={
                "task_template": {"uri": "file:///template"},
                "reference_task_sets": [],
            },
        )


def test_authored_metric_contract_rejects_empty_and_duplicate_keys() -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        AuthoredMetric(
            key="   ",
            description="A useful metric.",
            runtime_evidence=("runtime trace",),
        )

    with pytest.raises(ValidationError, match="duplicate metric key"):
        AuthoredMetricContract(metrics=(_metric("same_key"), _metric("same_key")))


def test_authored_metric_contract_enforces_fixed_scale_and_direction() -> None:
    metric = _metric()

    assert metric.scale == "unit_interval"
    assert metric.direction == "higher_is_better"
    with pytest.raises(ValidationError):
        AuthoredMetric.model_validate(
            {
                **metric.model_dump(),
                "scale": "unbounded",
            }
        )
    with pytest.raises(ValidationError):
        AuthoredMetric.model_validate(
            {
                **metric.model_dump(),
                "direction": "lower_is_better",
            }
        )


def test_authored_metric_requires_description_and_runtime_evidence() -> None:
    with pytest.raises(ValidationError):
        AuthoredMetric(
            key="useful_metric",
            description=" ",
            runtime_evidence=("runtime trace",),
        )
    with pytest.raises(ValidationError):
        AuthoredMetric(
            key="useful_metric",
            description="A useful metric.",
            runtime_evidence=(),
        )


def test_eval_author_result_round_trips_artifact_descriptors_and_metric_contract() -> None:
    contract = AuthoredMetricContract(metrics=(_metric(),))
    result = EvalAuthorResult(
        task_set=ArtifactDescriptor(
            uri="file:///artifacts/task-set",
            identity=f"sha256:{'a' * 64}",
        ),
        verifier_patch=ArtifactDescriptor(
            uri="file:///artifacts/verifier-patch",
            identity=f"sha256:{'b' * 64}",
        ),
        metric_contract=contract,
        summary="Authored one portable verifier metric.",
    )

    assert EvalAuthorResult.model_validate_json(result.model_dump_json()) == result
    assert "train_dataset" not in type(result).model_fields
    assert "validation_dataset" not in type(result).model_fields
    assert "insight_suite" not in type(result).model_fields


def test_eval_author_result_represents_no_trace_outcome_without_dataset_passthrough() -> None:
    result = EvalAuthorResult.no_artifacts("No trace refs on insight — nothing to analyze.")

    assert result.task_set is None
    assert result.verifier_patch is None
    assert result.metric_contract is None
    assert result.summary == "No trace refs on insight — nothing to analyze."
    assert EvalAuthorResult.model_validate_json(result.model_dump_json()) == result


def test_metric_authoring_result_is_structured_and_serializable() -> None:
    authored = MetricAuthoringResult(
        metric_contract=AuthoredMetricContract(metrics=(_metric(),)),
        summary="Added uses_inventory_lookup from OTLP tool spans.",
    )

    assert authored.metric_contract.keys == ("uses_inventory_lookup",)
    assert MetricAuthoringResult.model_validate_json(authored.model_dump_json()) == authored
