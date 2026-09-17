# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``AgentOptimizeJob.compile`` is an unimplemented stub; strategies write their own using the
shared ``_resolve_executor`` helper below, which these tests exercise directly."""

import asyncio
from typing import Any, ClassVar

import pytest
from nemo_agent_optimization_plugin import job_base
from nemo_agent_optimization_plugin.job_base import AgentOptimizeJob
from nemo_platform_plugin.jobs.exceptions import (
    PlatformJobCompilationError,
    PlatformJobDependencyUnavailableError,
)


class _Profile:
    def __init__(self, provider: str, profile: str) -> None:
        self.provider = provider
        self.profile = profile


def _resolve(monkeypatch: pytest.MonkeyPatch, profiles: list[Any], **kwargs: Any) -> Any:
    # ``_fetch_execution_profiles`` is genuinely async in job_base (it awaits
    # AsyncJobsClient.get_execution_profiles(), which returns an awaitable), and
    # ``_resolve_executor`` awaits it. The replacement here has to be an async callable
    # too so that await keeps working under the patch — a plain sync lambda would make
    # ``await _fetch_execution_profiles(...)`` fail with "object list can't be used in
    # 'await' expression".
    async def fake_fetch_execution_profiles(async_sdk: object) -> list[Any]:
        return profiles

    monkeypatch.setattr(job_base, "_fetch_execution_profiles", fake_fetch_execution_profiles)
    defaults = {
        "profile": "default",
        "async_sdk": object(),
        "task_module": "fake_plugin.tasks.agent_optimize",
        "task_image": "nmp-cpu-tasks",
    }
    return asyncio.run(job_base._resolve_executor(**{**defaults, **kwargs}))


def test_the_cpu_executor_runs_the_named_task_module(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _resolve(monkeypatch, [_Profile("cpu", "default")])

    assert executor.provider == "cpu"
    assert executor.container.command == ["fake_plugin.tasks.agent_optimize"]
    assert executor.container.entrypoint == ["python", "-m"]


def test_a_subprocess_profile_is_preferred_when_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_platform_plugin.jobs.execution_profiles import SubprocessJobExecutionProfile

    subprocess_profile = SubprocessJobExecutionProfile.model_construct(provider="subprocess", profile="default")
    executor = _resolve(monkeypatch, [subprocess_profile, _Profile("cpu", "default")])

    assert executor.provider == "subprocess"
    assert executor.command == ["python", "-m", "fake_plugin.tasks.agent_optimize"]


def test_no_matching_profile_is_a_compilation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(PlatformJobCompilationError, match="nowhere to run"):
        _resolve(monkeypatch, [_Profile("gpu", "other")])


def test_a_missing_async_sdk_is_retryable() -> None:
    with pytest.raises(PlatformJobDependencyUnavailableError, match="temporarily"):
        asyncio.run(
            job_base._resolve_executor(
                profile="default",
                async_sdk=None,
                task_module="fake_plugin.tasks.agent_optimize",
                task_image="nmp-cpu-tasks",
            )
        )


def test_the_base_class_compile_is_an_unimplemented_stub() -> None:
    class _Bare(AgentOptimizeJob):
        name: ClassVar[str] = "agent_optimize"
        strategy: ClassVar[str] = "bare"

    with pytest.raises(NotImplementedError, match="must override compile"):
        asyncio.run(
            _Bare.compile(
                workspace="my-ws",
                spec=None,
                entity_client=None,
                job_name=None,
                async_sdk=None,
            )
        )
