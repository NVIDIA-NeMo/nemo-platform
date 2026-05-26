# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the new agent-improvement NemoJobs are discoverable + well-formed."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError


def test_jobs_discovered_via_entry_points() -> None:
    from nemo_platform_plugin.discovery import discover_jobs

    jobs = discover_jobs()
    assert "agents.evaluate-suite" in jobs
    assert "agents.analyze" in jobs
    assert "agents.optimize-skills" in jobs


def test_evaluate_suite_job_metadata() -> None:
    from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteJob

    assert EvaluateSuiteJob.name == "evaluate-suite"
    assert EvaluateSuiteJob.container == "cpu-tasks"


def test_analyze_job_metadata() -> None:
    from nemo_agents_plugin.jobs.analyze_batch import AnalyzeBatchJob

    assert AnalyzeBatchJob.name == "analyze"
    assert AnalyzeBatchJob.container == "cpu-tasks"


def test_optimize_skills_job_metadata() -> None:
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsJob

    assert OptimizeSkillsJob.name == "optimize-skills"
    assert OptimizeSkillsJob.container == "cpu-tasks"


def test_evaluate_suite_config_validation() -> None:
    from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteConfig

    cfg = EvaluateSuiteConfig.model_validate({"evals": "./my-evals"})
    assert cfg.evals == "./my-evals"
    assert cfg.runner == "auto"
    assert cfg.prefer == "nat"
    assert cfg.concurrency == 4


def test_optimize_skills_config_validation() -> None:
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsConfig

    cfg = OptimizeSkillsConfig.model_validate({"evals": "./e", "agent": "./a"})
    assert cfg.skills_path == ".agents/skills"
    assert cfg.iterations == 3
    assert cfg.repeats == 1
    assert cfg.open_pr is False


# ---------------------------------------------------------------------------
# compile() — platform-job dispatch shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_suite_compile_produces_single_subprocess_step() -> None:
    from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteConfig, EvaluateSuiteJob
    from nmp.common.jobs.constants import (
        DEFAULT_JOB_STORAGE_PATH,
        PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
    )

    spec = EvaluateSuiteConfig(evals="/abs/evals", agent="/abs/agent", output="/abs/out")
    platform_spec = await EvaluateSuiteJob.compile(
        workspace="default",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    steps = list(platform_spec["steps"])
    assert len(steps) == 1
    step = steps[0]
    assert step["name"] == "evaluate-suite"
    assert step["executor"]["provider"] == "subprocess"
    assert step["executor"]["command"] == ["python", "-m", "nemo_agents_plugin.tasks.evaluate_suite"]
    assert step["config"]["evals"] == "/abs/evals"
    assert step["config"]["agent"] == "/abs/agent"

    env = {e["name"]: e.get("value") for e in step["environment"]}
    assert env[PERSISTENT_JOB_STORAGE_PATH_ENVVAR] == DEFAULT_JOB_STORAGE_PATH


@pytest.mark.asyncio
async def test_evaluate_suite_compile_url_workspace_overrides_spec_workspace() -> None:
    from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteConfig, EvaluateSuiteJob

    spec = EvaluateSuiteConfig(evals="/abs/evals", agent="/abs/agent")
    platform_spec = await EvaluateSuiteJob.compile(
        workspace="staging",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    config = next(iter(platform_spec["steps"]))["config"]
    assert config["workspace"] == "staging"


@pytest.mark.asyncio
async def test_evaluate_suite_compile_rejects_relative_paths() -> None:
    from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteConfig, EvaluateSuiteJob

    spec = EvaluateSuiteConfig(evals="./my-evals", agent="/abs/agent")
    with pytest.raises(PlatformJobCompilationError, match="'evals' must be an absolute path"):
        await EvaluateSuiteJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )


@pytest.mark.asyncio
async def test_optimize_skills_compile_produces_single_subprocess_step() -> None:
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsConfig, OptimizeSkillsJob
    from nmp.common.jobs.constants import (
        DEFAULT_JOB_STORAGE_PATH,
        PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
    )

    spec = OptimizeSkillsConfig(evals="/abs/evals", agent="/abs/agent")
    platform_spec = await OptimizeSkillsJob.compile(
        workspace="default",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    steps = list(platform_spec["steps"])
    assert len(steps) == 1
    step = steps[0]
    assert step["name"] == "optimize-skills"
    executor = step["executor"]
    assert executor.get("provider") == "subprocess"
    assert executor.get("command") == ["python", "-m", "nemo_agents_plugin.tasks.optimize_skills"]

    env = {e["name"]: e for e in step["environment"]}
    assert env[PERSISTENT_JOB_STORAGE_PATH_ENVVAR]["value"] == DEFAULT_JOB_STORAGE_PATH
    # When ``anthropic_api_key_secret`` is unset, no ANTHROPIC_API_KEY env is declared.
    assert "ANTHROPIC_API_KEY" not in env


@pytest.mark.asyncio
async def test_optimize_skills_compile_injects_anthropic_secret_when_set() -> None:
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsConfig, OptimizeSkillsJob

    spec = OptimizeSkillsConfig(
        evals="/abs/evals",
        agent="/abs/agent",
        anthropic_api_key_secret="anthropic-api-key",
    )
    platform_spec = await OptimizeSkillsJob.compile(
        workspace="default",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    step = next(iter(platform_spec["steps"]))
    env = {e["name"]: e for e in step["environment"]}
    assert env["ANTHROPIC_API_KEY"]["from_secret"]["name"] == "anthropic-api-key"


@pytest.mark.asyncio
async def test_optimize_skills_compile_rejects_relative_paths() -> None:
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsConfig, OptimizeSkillsJob

    spec = OptimizeSkillsConfig(evals="/abs/evals", agent="./my-agent")
    with pytest.raises(PlatformJobCompilationError, match="'agent' must be an absolute path"):
        await OptimizeSkillsJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )
