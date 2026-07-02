# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Serialization round-trip tests for TaskEntity.

The entity store persists custom fields with ``model_dump(exclude=base, mode="json")`` into a JSON
column and rebuilds them with ``model_validate``. This exercises that round-trip for the fields that
carry non-trivial nested types — the metric references and views. (A persisted task only ever holds
metric refs; inline metrics are normalized to derived stored metrics in the service before storage.)
"""

from __future__ import annotations

import json

from nemo_evaluator.api.schemas import MetricRef
from nemo_evaluator.entities import TaskEntity
from nemo_evaluator_sdk.agent_eval.tasks import SemanticReducer, SemanticView, ViewSignal


def _entity() -> TaskEntity:
    return TaskEntity(
        name="task-1",
        workspace="default",
        intent="Answer the question.",
        inputs={"instruction": "What is 2+2?"},
        # A persisted task holds metric references only — a workspace-qualified ref and a bare name.
        metrics=[MetricRef("default/stored-metric"), MetricRef("derived.abc123")],
        views={
            "correctness": SemanticView(
                reducer=SemanticReducer.SINGLE,
                signals=[ViewSignal(metric="exact-match", output="score")],
            )
        },
        metadata=[{"key": "suite", "value": "smoke"}],
    )


def _roundtrip(entity: TaskEntity) -> TaskEntity:
    data = entity.model_dump(exclude=TaskEntity.__base_fields__, exclude_computed_fields=True, mode="json")
    data = json.loads(json.dumps(data))  # prove JSON-serializable (the store uses a JSON column)
    return TaskEntity.model_validate({"name": entity.name, "workspace": entity.workspace, **data})


def test_roundtrip_preserves_task_fields() -> None:
    entity = _entity()

    restored = _roundtrip(entity)

    assert restored.intent == "Answer the question."
    assert restored.inputs.instruction == "What is 2+2?"
    assert [(m.key, m.value) for m in restored.metadata] == [("suite", "smoke")]
    # Metric refs survive as RootModel strings.
    assert isinstance(restored.metrics[0], MetricRef)
    assert restored.metrics[0].root == "default/stored-metric"
    assert isinstance(restored.metrics[1], MetricRef)
    assert restored.metrics[1].root == "derived.abc123"
    # Nested SemanticView survives the JSON column.
    assert restored.views == entity.views


def test_entity_type_is_task() -> None:
    assert TaskEntity.__entity_type__ == "task"
