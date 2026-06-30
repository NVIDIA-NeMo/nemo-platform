# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin-native agent-evaluation job compiler.

Parallels :mod:`nemo_evaluator.jobs.compiler` (row/model eval), emitting a single
``cpu-tasks`` step that runs ``python -m nemo_evaluator.tasks.agent_evaluate`` in
the platform task environment. Metric/endpoint secrets are surfaced as
``from_secret`` environment variables; an agent *runner* target (e.g. Codex)
carries no endpoint secret of its own.
"""

from __future__ import annotations

from collections.abc import Iterator

from nemo_evaluator.jobs.agent_spec import AgentEvalSpec, AgentTarget, ModelTarget
from nemo_evaluator.jobs.secret_env import build_task_environment
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image

AGENT_EVAL_STEP_NAME = "agent-evaluate"

#: Container wiring for the agent-evaluate step: the shared cpu-tasks image, run via ``python -m``.
#: Constants (not inline literals) so the step definition and its tests share one source of truth.
#: (Making these spec-configurable is a possible future enhancement — see PR #496 discussion — but
#: they're fixed for the MVP.)
AGENT_EVAL_IMAGE = "nmp-cpu-tasks"
AGENT_EVAL_ENTRYPOINT = ["python", "-m"]
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
    return PlatformJobStep(
        name=AGENT_EVAL_STEP_NAME,
        executor=CPUExecutionProviderSpec(
            profile=profile or "default",
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image(AGENT_EVAL_IMAGE),
                entrypoint=AGENT_EVAL_ENTRYPOINT,
                command=AGENT_EVAL_COMMAND,
            ),
        ),
        config=spec.model_dump(mode="json"),
        environment=build_task_environment(_secret_refs(spec)),
    )
