# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for taskset-reference resolution on the agent-eval submit path."""

from __future__ import annotations

from typing import TypeVar

import pytest
from nemo_evaluator.api.schemas import MetadataItem, MetricRef, TaskInputs, TaskRef, TasksetRef
from nemo_evaluator.entities import TaskEntity, TaskRevisionEntity, TasksetEntity
from nemo_evaluator.jobs.agent_spec import AgentEvalTaskInput
from nemo_evaluator.revisions import head_digest, publish_revision
from nemo_evaluator.task_refs import resolve_agent_eval_tasks, resolve_taskset_ref
from nemo_platform_plugin.entities import EntityBase

_EntityT = TypeVar("_EntityT", bound=EntityBase)


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


async def _store(client, *entities: EntityBase):
    """Build a store and *publish* every task, so members resolve to a real revision.

    Tasks are published rather than merely inserted because taskset expansion now reads the pinned
    revision's content, not the head's — the same thing the service does on create.
    """
    for entity in entities:
        await client.create(entity)
        if isinstance(entity, TaskEntity):
            await publish_revision(client, client, entity, TaskRevisionEntity)
    return client


async def test_resolves_taskset_members_to_inline_task_inputs(entity_store) -> None:
    client = await _store(
        entity_store,
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


async def test_bare_member_ref_resolves_against_taskset_workspace(entity_store) -> None:
    client = await _store(entity_store, _task("t1", workspace="team"), _taskset("ts", ["t1"], workspace="team"))

    tasks = await resolve_taskset_ref(TasksetRef("team/ts"), workspace="default", entity_client=client)

    assert [t.id for t in tasks] == ["t1"]


async def test_unknown_taskset_raises_clear_error(entity_store) -> None:
    with pytest.raises(ValueError, match="Taskset reference 'default/missing' not found"):
        await resolve_taskset_ref(
            TasksetRef("default/missing"), workspace="default", entity_client=await _store(entity_store)
        )


async def test_missing_member_task_raises_clear_error(entity_store) -> None:
    client = await _store(entity_store, _taskset("geo", ["default/gone"]))
    with pytest.raises(ValueError, match="Task 'default/gone' referenced by taskset 'default/geo'"):
        await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=client)


async def test_empty_taskset_raises_clear_error(entity_store) -> None:
    client = await _store(entity_store, _taskset("empty", []))
    with pytest.raises(ValueError, match="has no member tasks"):
        await resolve_taskset_ref(TasksetRef("default/empty"), workspace="default", entity_client=client)


async def test_duplicate_expanded_task_ids_rejected(entity_store) -> None:
    # Two members from different workspaces share the name 'dup' -> ambiguous task id.
    client = await _store(
        entity_store,
        _task("dup", workspace="a"),
        _task("dup", workspace="b"),
        _taskset("geo", ["a/dup", "b/dup"]),
    )
    with pytest.raises(ValueError, match="more than one task named 'dup'"):
        await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=client)


async def test_taskset_ref_requires_entity_client(entity_store) -> None:
    with pytest.raises(ValueError, match="requires a platform connection"):
        await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=None)


async def test_resolve_agent_eval_tasks_passes_inline_list_through(entity_store) -> None:
    inline = [AgentEvalTaskInput(id="t", intent="x", metrics=[])]
    result = await resolve_agent_eval_tasks(inline, workspace="default", entity_client=None)
    assert result is inline


async def test_resolve_agent_eval_tasks_expands_a_taskset_ref(entity_store) -> None:
    client = await _store(entity_store, _task("only"), _taskset("geo", ["default/only"]))
    result = await resolve_agent_eval_tasks(TasksetRef("default/geo"), workspace="default", entity_client=client)
    assert [t.id for t in result] == ["only"]


async def test_expansion_uses_the_pinned_revision_not_current_content(entity_store) -> None:
    """The property the whole pinning design exists for: an evaluation re-run expands to the same
    content even after a member task has published newer content.

    Before this was wired, expansion read the member's *head*, silently defeating the pin — the
    taskset looked reproducible and wasn't.
    """
    task = _task("capital-of-france")
    client = await _store(entity_store, task)
    pinned_digest = head_digest(task)

    taskset = _taskset("geo", [f"default/capital-of-france#{pinned_digest}"])
    await client.create(taskset)

    # The member publishes newer content after the taskset was pinned.
    task.intent = "Something else entirely."
    await client.update(task)
    await publish_revision(client, client, task, TaskRevisionEntity)

    tasks = await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=client)

    assert tasks[0].intent == "Do capital-of-france.", "expansion must return the pinned content"


async def test_expansion_fails_loudly_when_a_pin_no_longer_resolves(entity_store) -> None:
    """Verify-on-read at the point it matters most: a pin that cannot be honoured must stop the
    evaluation rather than quietly substituting whatever is current."""
    client = await _store(entity_store, _task("only"))
    await client.create(_taskset("geo", [f"default/only#{'c' * 64}"]))

    with pytest.raises(ValueError, match="no longer resolves"):
        await resolve_taskset_ref(TasksetRef("default/geo"), workspace="default", entity_client=client)
