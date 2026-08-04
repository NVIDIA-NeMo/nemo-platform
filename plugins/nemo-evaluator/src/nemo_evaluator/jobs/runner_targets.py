# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runner runtime -> wire target conversion.

The inverse of :meth:`~nemo_evaluator.jobs.agent_evaluate.AgentEvalJob._resolve_target`: that
rebuilds a runner from its spec job-side, this describes a live runner as the spec that can be
submitted. Both directions are platform concerns, so both live here in the plugin — the SDK
runtimes know nothing about job specs, target kinds, or the wire at all. They expose their own
configuration as ordinary attributes and this module decides how it is spelled.

Two rules make a submitted run trustworthy:

* **Environment-supplied arguments never travel.** Working directories, sandbox providers, and
  process factories belong to whoever executes the run; the job supplies its own from its storage
  and runtime, so carrying the caller's would be meaningless at best and wrong at worst.
* **Unrepresentable state raises.** A runner configured with something the wire has no field for —
  injected skills, a custom prompt builder — is refused rather than quietly downgraded, because a
  submitted run that silently differs from the local one it mirrors is worse than one that will
  not start.
"""

from __future__ import annotations

import asyncio

from nemo_evaluator.jobs.agent_spec import (
    AgentRunnerTarget,
    CodexRunnerTarget,
    FabricRunnerTarget,
    FabricSandboxSpec,
)
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import CodexCliAgentRuntime
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.container_runtime import FabricContainerRuntime
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.runtime import FabricAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentTaskRunner


class UnsubmittableRunnerError(TypeError):
    """A live runner cannot be described as a submittable target spec.

    Raised both for runner types with no wire form at all and for a supported runner configured
    with state the wire cannot carry.
    """


def runner_to_target(runner: AgentTaskRunner) -> AgentRunnerTarget:
    """Describe a live agent runner as the target spec that reproduces it job-side.

    Raises:
        UnsubmittableRunnerError: If the runner has no wire form, or carries state that would be
            lost in translation.
    """
    if isinstance(runner, FabricContainerRuntime):
        return _fabric_container_target(runner)
    if isinstance(runner, FabricAgentRuntime):
        return _fabric_host_target(runner)
    if isinstance(runner, CodexCliAgentRuntime):
        return _codex_target(runner)
    raise UnsubmittableRunnerError(
        f"{type(runner).__name__} has no target spec, so it cannot be submitted as a job. Run it "
        "in-process with Evaluator(), or pass a runner target spec directly."
    )


def _codex_target(runner: CodexCliAgentRuntime) -> CodexRunnerTarget:
    """``CodexCliAgentRuntime`` -> ``CodexRunnerTarget``.

    ``work_root`` is deliberately dropped: a submitted run works under the job's own storage.
    """
    _reject_customizations(
        "CodexCliAgentRuntime",
        {
            "codex_bin": runner.codex_bin != "codex",
            "prompt_builder": runner.prompt_builder is not AgentEvalTask.agent_prompt,
            "process_factory": runner.process_factory is not asyncio.create_subprocess_exec,
            "runtime_name": runner.runtime_name != "codex_cli",
        },
        carried="'model' and 'timeout_s'",
    )
    return CodexRunnerTarget(model=runner.model, timeout_s=runner.timeout_s)


def _fabric_host_target(runner: FabricAgentRuntime) -> FabricRunnerTarget:
    """``FabricAgentRuntime`` -> ``FabricRunnerTarget`` with no sandbox (harness on the job's fs)."""
    _reject_skills("FabricAgentRuntime", runner.skills)
    if runner.base_dir is not None:
        raise UnsubmittableRunnerError(
            "FabricAgentRuntime cannot be submitted with an explicit base_dir: it anchors relative "
            "config paths on the local filesystem, which a job cannot reproduce. Make the config's "
            "paths self-contained, or run it in-process with Evaluator()."
        )
    _reject_customizations(
        "FabricAgentRuntime",
        {"runtime_name": runner.runtime_name != "fabric"},
        carried="'config', 'model', 'timeout_s' and 'capture_trajectory'",
    )
    return FabricRunnerTarget(
        config=dict(runner.config),
        model=runner.model,
        timeout_s=runner.timeout_s,
        capture_trajectory=runner.capture_trajectory,
    )


def _fabric_container_target(runner: FabricContainerRuntime) -> FabricRunnerTarget:
    """``FabricContainerRuntime`` -> ``FabricRunnerTarget`` carrying a sandbox spec.

    Only the provider's *name* travels — the instance holds process-wide resources the job
    constructs for itself. Secrets travel as unresolved references, so a runner whose secrets were
    already resolved still yields a spec with no credential in it.
    """
    _reject_skills("FabricContainerRuntime", runner.skills)
    return FabricRunnerTarget(
        config=dict(runner.config),
        sandbox=FabricSandboxSpec(
            # An unknown provider name fails the spec's provider union here, which is the intended
            # outcome: the job could not have rebuilt that provider anyway.
            provider=runner.provider.name,
            image=runner.image,
            secrets=dict(runner.secrets),
        ),
    )


def _reject_skills(runner_name: str, skills: tuple[object, ...]) -> None:
    """Refuse a skill-bearing runner: skills are local directories with no wire representation."""
    if not skills:
        return
    names = ", ".join(getattr(skill, "name", str(skill)) for skill in skills)
    raise UnsubmittableRunnerError(
        f"{runner_name} cannot be submitted with injected skills ({names}): skill bundles are local "
        "directories and the fabric target spec has no field to carry them. Submitting would run a "
        "skill-free arm under the treated arm's name. Run it in-process with Evaluator(), or drop "
        "the skills."
    )


def _reject_customizations(runner_name: str, customized: dict[str, bool], *, carried: str) -> None:
    """Refuse construction arguments the target spec has no field for."""
    unsupported = sorted(name for name, is_customized in customized.items() if is_customized)
    if not unsupported:
        return
    raise UnsubmittableRunnerError(
        f"{runner_name} cannot be submitted with non-default {', '.join(unsupported)}: its target "
        f"spec carries only {carried}. Run it in-process with Evaluator(), or drop the customization."
    )
