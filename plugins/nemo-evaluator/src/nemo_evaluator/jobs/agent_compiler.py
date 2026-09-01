# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin-native agent-evaluation job compiler.

Parallels :mod:`nemo_evaluator.jobs.compiler` (row/model eval), emitting a single
``cpu-tasks`` step that runs ``python -m nemo_evaluator.tasks.agent_evaluate`` in
the platform task environment. Metric/endpoint secrets are surfaced as
``from_secret`` environment variables; an agent *runner* target (e.g. Fabric)
carries no endpoint secret of its own.
"""

from __future__ import annotations

from collections.abc import Iterator

from nemo_evaluator.config import config
from nemo_evaluator.jobs.agent_spec import AgentEvalSpec, AgentTarget, GymRunnerTarget, ModelTarget
from nemo_evaluator.jobs.secret_env import build_task_environment
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image

AGENT_EVAL_STEP_NAME = "agent-evaluate"

#: Container wiring for agent-evaluate steps, run via ``python -m``. Gym targets use a dedicated image
#: because NeMo Gym requires Ray. This keeps Gym and Ray out of the shared CPU task image.
AGENT_EVAL_IMAGE = "nmp-cpu-tasks"
GYM_AGENT_EVAL_IMAGE = "nmp-gym-tasks"
AGENT_EVAL_ENTRYPOINT = ["python", "-m"]
GYM_AGENT_EVAL_ENTRYPOINT = ["/app/.venv/bin/python", "-m"]
AGENT_EVAL_COMMAND = ["nemo_evaluator.tasks.agent_evaluate"]


def compile_agent_eval_job(spec: AgentEvalSpec, *, profile: str | None = None) -> PlatformJobSpec:
    """Compile a canonical agent-evaluation spec into a plugin-native platform job."""
    return PlatformJobSpec(steps=[_agent_eval_step(spec, profile)])


def _secret_refs(spec: AgentEvalSpec) -> Iterator[tuple[str, str]]:
    """Yield ``(env_name, secret_name)`` for each metric secret and the endpoint target's api key."""
    for task in spec.tasks:
        for bundle in task.metrics:
            for env_name, secret_ref in bundle.secrets.items():
                yield env_name, secret_ref.root

    endpoint = None
    if isinstance(spec.target, ModelTarget):
        endpoint = spec.target.model
    elif isinstance(spec.target, AgentTarget):
        endpoint = spec.target.agent
    if endpoint is not None and endpoint.api_key_secret is not None and endpoint.api_key_env:
        yield endpoint.api_key_env, endpoint.api_key_secret.root


def _agent_eval_step(spec: AgentEvalSpec, profile: str | None) -> PlatformJobStep:
    is_gym_target = isinstance(spec.target, GymRunnerTarget)
    image = (
        config.gym_tasks_image
        if is_gym_target and config.gym_tasks_image is not None
        else get_qualified_image(GYM_AGENT_EVAL_IMAGE if is_gym_target else AGENT_EVAL_IMAGE)
    )
    return PlatformJobStep(
        name=AGENT_EVAL_STEP_NAME,
        executor=CPUExecutionProviderSpec(
            profile=profile or "default",
            provider="cpu",
            container=ContainerSpec(
                image=image,
                entrypoint=GYM_AGENT_EVAL_ENTRYPOINT if is_gym_target else AGENT_EVAL_ENTRYPOINT,
                command=AGENT_EVAL_COMMAND,
            ),
        ),
        config=spec.model_dump(mode="json"),
        environment=build_task_environment(_secret_refs(spec)),
    )
