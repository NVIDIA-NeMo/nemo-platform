# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the agent-improvement NemoJobs: discovery + metadata + spec shape.

The memory-triage NemoJobs that used to live here moved to the
``nemo-memory`` plugin (bd ``mdubrinsky-eha``). See
``plugins/nemo-memory/tests/unit/test_jobs.py`` for their equivalents.
"""

from __future__ import annotations


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
