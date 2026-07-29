# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""References to persisted tasksets and their resolution into inline tasks.

An agent-eval submission carries ``tasks`` as either an inline list of
:class:`~nemo_evaluator.jobs.agent_spec.AgentEvalTaskInput` or a
:class:`~nemo_evaluator.api.schemas.TasksetRef` pointing at a stored taskset. During spec resolution
(``AgentEvalJob.to_spec``) a taskset reference is loaded from storage and its member tasks are
expanded into the same inline task DTOs, so the rest of the pipeline (metric-ref resolution, the
canonical :class:`~nemo_evaluator.jobs.agent_spec.AgentEvalSpec`) only ever sees inline tasks.

This mirrors :mod:`nemo_evaluator.metric_refs`: references are loaded here, next to the entity types,
so the job's ``to_spec`` stays a thin orchestration over ref-resolution helpers.
"""

from __future__ import annotations

from nemo_evaluator.api.schemas import TasksetRef, parse_entity_ref
from nemo_evaluator.entities import TaskEntity, TasksetEntity
from nemo_evaluator.jobs.agent_spec import AgentEvalTaskInput
from nemo_platform_plugin.entity_client import NemoAnyEntityGetterProtocol, NemoEntityNotFoundError


def _entity_to_task_input(entity: TaskEntity) -> AgentEvalTaskInput:
    """Project a stored task onto the submitter-facing inline task DTO.

    The task's stable ``id`` is its record ``name``. A stored task holds metric *references* (inline
    metrics were normalized to derived stored metrics on create); those resolve to inline bundles in
    the shared metric-ref pass that runs after expansion. A stored task carries no grader-only
    ``reference`` (the entity has no such field), so taskset-driven tasks run with an empty one.
    """
    return AgentEvalTaskInput(
        id=entity.name,
        intent=entity.intent,
        inputs=entity.inputs,
        metrics=list(entity.metrics),
        views=entity.views,
        metadata=entity.metadata,
    )


async def resolve_taskset_ref(
    ref: TasksetRef,
    *,
    workspace: str,
    entity_client: NemoAnyEntityGetterProtocol | None,
) -> list[AgentEvalTaskInput]:
    """Load a stored taskset and expand its members into inline task DTOs.

    Loading needs only the entity store (metrics stay as refs, resolved downstream), so unlike
    metric-ref resolution this does not require an async SDK / file I/O.
    """
    if entity_client is None:
        raise ValueError(
            "A TasksetRef requires a platform connection (entity store) to resolve; it cannot be used "
            "in local execution. Pass an inline task list instead."
        )
    ref_workspace, name = parse_entity_ref(ref.root, workspace)
    try:
        taskset = await entity_client.get(TasksetEntity, name=name, workspace=ref_workspace)
    except NemoEntityNotFoundError as exc:
        raise ValueError(
            f"Taskset reference '{ref.root}' not found. "
            f"Ensure a stored taskset named '{name}' exists in workspace '{ref_workspace}', "
            "or pass an inline task list instead."
        ) from exc

    if not taskset.tasks:
        raise ValueError(f"Taskset '{ref.root}' has no member tasks; an agent evaluation needs at least one task.")

    tasks: list[AgentEvalTaskInput] = []
    seen_ids: set[str] = set()
    for task_ref in taskset.tasks:
        task_workspace, task_name = parse_entity_ref(task_ref.root, ref_workspace)
        try:
            entity = await entity_client.get(TaskEntity, name=task_name, workspace=task_workspace)
        except NemoEntityNotFoundError as exc:
            raise ValueError(
                f"Task '{task_ref.root}' referenced by taskset '{ref.root}' was not found; "
                "the stored task may have been deleted after the taskset was created."
            ) from exc
        # Agent-eval task ids must be unique within a run. Member refs are unique per (workspace,
        # name), but refs from different workspaces can share a name — surface that as a clear error
        # rather than letting the SDK evaluator reject duplicate ids deeper in the run.
        if entity.name in seen_ids:
            raise ValueError(
                f"Taskset '{ref.root}' expands to more than one task named '{entity.name}'; "
                "task ids must be unique within an evaluation."
            )
        seen_ids.add(entity.name)
        tasks.append(_entity_to_task_input(entity))
    return tasks


async def resolve_agent_eval_tasks(
    tasks: TasksetRef | list[AgentEvalTaskInput],
    *,
    workspace: str,
    entity_client: NemoAnyEntityGetterProtocol | None,
) -> list[AgentEvalTaskInput]:
    """Normalize an agent-eval ``tasks`` field to an inline task list.

    An inline list passes through unchanged; a :class:`TasksetRef` is loaded and expanded.
    """
    if isinstance(tasks, TasksetRef):
        return await resolve_taskset_ref(tasks, workspace=workspace, entity_client=entity_client)
    return tasks
