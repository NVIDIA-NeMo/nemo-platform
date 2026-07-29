# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for taskset-reference resolution on the agent-eval submit path."""

from __future__ import annotations

from typing import TypeVar

import pytest
from nemo_evaluator.api.schemas import MetadataItem, MetricRef, TaskInputs, TaskRef, TasksetRef
from nemo_evaluator.entities import TaskEntity, TasksetEntity
from nemo_evaluator.jobs.agent_spec import AgentEvalTaskInput
from nemo_evaluator.task_refs import resolve_agent_eval_tasks, resolve_taskset_ref
from nemo_platform_plugin.entities import EntityBase
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError

_EntityT = TypeVar("_EntityT", bound=EntityBase)


class _FakeEntityClient:
    """Minimal entity store keyed by (type, workspace, name), mirroring EntityClient.get."""

    def __init__(self) -> None:
        self.entities: dict[tuple[str, str, str], EntityBase] = {}

    def add(self, entity: EntityBase) -> None:
        self.entities[(entity.__entity_type__, entity.workspace, entity.name)] = entity

    async def get(self, entity_type: type[_EntityT], *, workspace: str, name: str) -> _EntityT:
        key = (entity_type.__entity_type__, workspace, name)
        if key not in self.entities:
            raise NemoEntityNotFoundError(f"{workspace}/{name} not found")
        entity = self.entities[key]
        assert isinstance(entity, entity_type)
        return entity


def _task(name: str, *, workspace: str = "default", metric: str = "default/m") -> TaskEntity:
    return TaskEntity(
        name=name,
        workspace=workspace,
        intent=f"Do {name}.",
        inputs=TaskInputs(instruction=f"instruction for {name}"),
        metrics=[MetricRef(metric)],
        metadata=[MetadataItem(key="suite", value="geo")],
    )


def _taskset(name: str, task_refs: list[str], *, workspace: str = "default") -> TasksetEntity:
    return TasksetEntity(name=name, workspace=workspace, tasks=[TaskRef(r) for r in task_refs])


def _store(*entities: EntityBase) -> _FakeEntityClient:
    client = _FakeEntityClient()
    for entity in entities:
        client.add(entity)
    return client


async def test_resolves_taskset_members_to_inline_task_inputs() -> None:
    client = _store(
        _task("capital-of-france"),
        _task("capital-of-japan"),
        _taskset("geo", ["default/capital-of-france", "default/capital-of-japan"]),
    )

    tasks = await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=client)

    assert [t.id for t in tasks] == ["capital-of-france", "capital-of-japan"]
    assert all(isinstance(t, AgentEvalTaskInput) for t in tasks)
    # A stored task's refs pass through untouched (resolved to inline later in the metric pass).
    assert tasks[0].metrics == [MetricRef("default/m")]
    assert tasks[0].intent == "Do capital-of-france."
    assert tasks[0].inputs.instruction == "instruction for capital-of-france"
    # A stored task carries no grader-only reference.
    assert tasks[0].reference == {}


async def test_bare_member_ref_resolves_against_taskset_workspace() -> None:
    client = _store(_task("t1", workspace="team"), _taskset("ts", ["t1"], workspace="team"))

    tasks = await resolve_taskset_ref(TasksetRef("team/ts"), workspace="default", entity_client=client)

    assert [t.id for t in tasks] == ["t1"]


async def test_unknown_taskset_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Taskset reference 'default/missing' not found"):
        await resolve_taskset_ref(TasksetRef("default/missing"), workspace="default", entity_client=_store())


async def test_missing_member_task_raises_clear_error() -> None:
    client = _store(_taskset("geo", ["default/gone"]))
    with pytest.raises(ValueError, match="Task 'default/gone' referenced by taskset 'default/geo'"):
        await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=client)


async def test_empty_taskset_raises_clear_error() -> None:
    client = _store(_taskset("empty", []))
    with pytest.raises(ValueError, match="has no member tasks"):
        await resolve_taskset_ref(TasksetRef("default/empty"), workspace="default", entity_client=client)


async def test_duplicate_expanded_task_ids_rejected() -> None:
    # Two members from different workspaces share the name 'dup' -> ambiguous task id.
    client = _store(
        _task("dup", workspace="a"),
        _task("dup", workspace="b"),
        _taskset("geo", ["a/dup", "b/dup"]),
    )
    with pytest.raises(ValueError, match="more than one task named 'dup'"):
        await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=client)


async def test_taskset_ref_requires_entity_client() -> None:
    with pytest.raises(ValueError, match="requires a platform connection"):
        await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=None)


async def test_resolve_agent_eval_tasks_passes_inline_list_through() -> None:
    inline = [AgentEvalTaskInput(id="t", intent="x", metrics=[])]
    result = await resolve_agent_eval_tasks(inline, workspace="default", entity_client=None)
    assert result is inline


async def test_resolve_agent_eval_tasks_expands_a_taskset_ref() -> None:
    client = _store(_task("only"), _taskset("geo", ["default/only"]))
    result = await resolve_agent_eval_tasks(TasksetRef("default/geo"), workspace="default", entity_client=client)
    assert [t.id for t in result] == ["only"]
