# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The contract every agent optimization strategy implements.

A strategy is a job.  ``compile`` and ``run`` are unimplemented on this base —
every concrete strategy subclass writes its own, since strategies differ
enough (fileset-required vs. plain-path configs, what gets staged, what the
optimized spec looks like) that a shared body papered over real differences.
This module still ships the pieces most strategies need — staging a bundle,
resolving an execution profile, fetching the source agent's stored config —
as plain functions a strategy's own ``compile``/``run`` can call.

Keep this module a leaf: ``discovery`` imports plugin job classes, which
import this, so importing ``discovery`` (or the router) from here would cycle.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, cast

import yaml
from nemo_agent_optimization_plugin.schemas.optimize import AgentOptimizeSpec
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import InternalServerError, NemoResponseValidationError, NemoTransportError
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    ExecutorSpec,
    PlatformJobSpec,
    SubprocessExecutionProviderSpec,
)
from nemo_platform_plugin.jobs.client import AsyncJobsClient
from nemo_platform_plugin.jobs.exceptions import (
    PlatformJobCompilationError,
    PlatformJobDependencyUnavailableError,
)
from nemo_platform_plugin.jobs.execution_profiles import SubprocessJobExecutionProfile
from nemo_platform_plugin.jobs.image import get_qualified_image
from nemo_platform_plugin.run_dependencies import LocalRunError
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentOptimizeJob(NemoJob):
    """Base for every agent optimization strategy job."""

    # ``NemoJob``'s ``run`` is the only method the platform's ``_NamedPlugin``
    # metaclass tracks via ``abc.abstractmethod``; overriding it here makes this
    # class register as "fully concrete" the moment the class body executes,
    # which trips ``_NamedPlugin.__init_subclass__``'s "must define name"
    # check. ``optimize`` is deliberately *not* ``@abstractmethod`` (see its
    # docstring below), so it can't carry that abstractness forward instead.
    # A placeholder satisfies the check on this base; every concrete strategy
    # subclass sets its own ``name`` for real job/CLI/entry-point identity.
    name: ClassVar[str] = "agent_optimize_base"
    strategy: ClassVar[str]
    container: ClassVar[str] = "cpu-tasks"
    job_collection_path: ClassVar[str | None] = None
    generate_legacy_verbs: ClassVar[bool] = False
    spec_schema: ClassVar[type[BaseModel]] = AgentOptimizeSpec

    @classmethod
    async def compile(  # ty: ignore[invalid-method-override]
        cls,
        *,
        workspace: str,
        spec: AgentOptimizeSpec,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Compile *spec* into the ``PlatformJobSpec`` the Jobs service submits.

        Every strategy owns this: what must be staged up front (a fileset vs.
        a plain host path), which execution profile it needs, and what its
        step config looks like are strategy-specific.  Use
        :func:`_resolve_executor` to pick a subprocess/cpu executor from the
        profiles the platform has registered.
        """
        raise NotImplementedError(f"{cls.__name__} must override compile() to be remote-capable.")

    def run(self, config: dict, *, ctx: JobContext, sdk: NeMoPlatform | None = None) -> dict:
        """Run the strategy locally or as the remote job's step.

        Every strategy owns this: what gets staged, how the source agent's
        config is transformed, and how the optimized result is registered
        differ enough between strategies that a shared body papered over
        those differences.  :func:`split_agent_ref`, :func:`fetch_agent_config`,
        :func:`_staged_bundle`, and :func:`_bundle_workdir` are the pieces most
        strategies need; :func:`register_optimized_agent` (from
        ``nemo_agent_optimization_plugin.registration``) publishes the result.
        """
        raise NotImplementedError(f"{type(self).__name__} must override run().")


def _profiles_unavailable(profile: str) -> PlatformJobDependencyUnavailableError:
    """A retryable failure while resolving the backend for *profile*."""
    return PlatformJobDependencyUnavailableError(
        f"Unable to resolve execution profile '{profile}': the Jobs service is temporarily "
        "unavailable.  Retry the submission."
    )


async def _fetch_execution_profiles(async_sdk: object) -> list:
    """The execution profiles the platform has registered.

    Split out from :func:`_resolve_executor` purely so tests can replace the network call
    without faking the whole SDK.  Kept module-level (not a nested closure) so
    ``monkeypatch.setattr(job_base, "_fetch_execution_profiles", ...)`` can intercept it.
    """
    return (
        await client_from_platform(cast(AsyncNeMoPlatform, async_sdk), AsyncJobsClient).get_execution_profiles()
    ).data()


async def _resolve_executor(*, profile: str, async_sdk: object, task_module: str, task_image: str) -> ExecutorSpec:
    """Pick the executor for *profile* from the backends the platform actually registered.

    Optimization prefers ``subprocess``: a study drives trials that may need the host's
    Docker daemon and a venv carrying the agent's harness adapters.  Deployments that do
    not register a subprocess backend (Helm / Minikube) get the ``cpu`` provider instead,
    which the platform maps to whichever backend it registered for that profile.
    """
    if async_sdk is None:
        raise _profiles_unavailable(profile)

    entrypoint = ["python", "-m"]
    command = [task_module]

    try:
        profiles = await _fetch_execution_profiles(async_sdk)
    except (NemoTransportError, NemoResponseValidationError, InternalServerError) as exc:
        raise _profiles_unavailable(profile) from exc

    if any(
        isinstance(candidate, SubprocessJobExecutionProfile) and candidate.profile == profile for candidate in profiles
    ):
        return SubprocessExecutionProviderSpec(provider="subprocess", profile=profile, command=[*entrypoint, *command])

    # Jobs keys execution profiles by (provider, profile); "cpu" is whatever container
    # backend the deployment registered under that name.
    if any(candidate.provider == "cpu" and candidate.profile == profile for candidate in profiles):
        return CPUExecutionProviderSpec(
            provider="cpu",
            profile=profile,
            container=ContainerSpec(image=get_qualified_image(task_image), entrypoint=entrypoint, command=command),
        )

    available = sorted({f"{candidate.provider}/{candidate.profile}" for candidate in profiles})
    raise PlatformJobCompilationError(
        f"No 'subprocess' or 'cpu' execution profile named {profile!r} is registered, so the "
        f"agent-optimize step has nowhere to run.  Available profiles: {available or ['<none>']}."
    )


def split_agent_ref(agent: str, *, workspace: str) -> tuple[str, str]:
    """Split an ``agent`` ref into ``(workspace, name)``, defaulting to *workspace*."""
    ws, _, name = agent.rpartition("/")
    return ws or workspace, name


def fetch_agent_config(agent: str, *, workspace: str, sdk: NeMoPlatform) -> dict[str, Any]:
    """Fetch a platform agent's stored ``nemo-agents-spec-v1`` config."""
    ws, name = split_agent_ref(agent, workspace=workspace)
    stored = sdk.agents.get(name, workspace=ws)
    config = stored["config"] if isinstance(stored, dict) else getattr(stored, "config", {})
    if not isinstance(config, dict) or not config:
        raise LocalRunError(f"Agent '{ws}/{name}' has an empty or invalid stored config.")
    logger.info("Resolved agent %r to %s/%s", agent, ws, name)
    return config


@contextlib.contextmanager
def _staged_bundle(spec: AgentOptimizeSpec, *, ctx: JobContext, sdk: NeMoPlatform) -> Iterator[tuple[Path, Path]]:
    """Yield ``(config path, bundle root)`` for the run."""
    # Soft dependency, mirroring registration.py's lazy imports.
    from nemo_agents_plugin.jobs.fileset_io import resolve_staged_config

    with resolve_staged_config(
        spec.optimize_config,
        spec.optimize_config_fileset,
        workspace=spec.workspace,
        ctx=ctx,
        sdk=sdk,
        kind="optimize-config",
    ) as config_path:
        yield config_path, _bundle_root_of(config_path, spec.optimize_config)


def _bundle_root_of(config_path: Path, config_rel_path: str) -> Path:
    """The download dir *config_rel_path* was resolved inside."""
    root = config_path
    for _ in PurePosixPath(config_rel_path).parts:
        root = root.parent
    return root


@contextlib.contextmanager
def _bundle_workdir(bundle_root: Path) -> Iterator[None]:
    """Run the strategy with *bundle_root* as the working directory.

    Relative paths in a strategy config are fileset-root-relative and are
    consumed in many places (datasets, Fabric ``base_dir``, hook paths, MCP
    config paths).  Moving the process resolves them all at once instead of
    chasing every schema that can hold a path.  The task subprocess runs
    exactly one job, so the process-global chdir is contained.
    """
    previous = Path.cwd()
    os.chdir(bundle_root)
    logger.info("Resolving config paths against staged bundle root %s", bundle_root)
    try:
        yield
    finally:
        os.chdir(previous)


def _load_yaml(path: Path) -> dict[str, Any]:
    """Read a strategy config, expanding ``${VAR}`` against the task environment."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"optimization config must be a mapping: {path}")
    return _expand_env(raw)


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value
