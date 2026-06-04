# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the new agent-improvement NemoJobs are discoverable + well-formed."""

from __future__ import annotations


def test_jobs_discovered_via_entry_points() -> None:
    from nemo_platform_plugin.discovery import discover_jobs

    jobs = discover_jobs()
    assert "agents.evaluate-suite" in jobs
    assert "agents.analyze" in jobs
    assert "agents.optimize-skills" in jobs
    assert "agents.triage-memory" in jobs


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


def test_triage_memory_job_metadata() -> None:
    from nemo_agents_plugin.jobs.triage_memory import TriageMemoryJob

    assert TriageMemoryJob.name == "triage-memory"
    assert TriageMemoryJob.container == "cpu-tasks"


def test_triage_memory_config_minimum_validation() -> None:
    from nemo_agents_plugin.jobs.triage_memory import TriageMemoryConfig

    cfg = TriageMemoryConfig.model_validate({"corpus": "./USER.md", "judges": ["azure-anthropic-claude-sonnet-4-6"]})
    assert cfg.corpus == "./USER.md"
    assert cfg.judges == ["azure-anthropic-claude-sonnet-4-6"]
    assert cfg.store_name == "pi-hermes:memory"
    assert cfg.workspace == "default"
    assert cfg.basename == "triage"
    assert cfg.max_tokens == 4096
    assert cfg.max_entries is None
    assert cfg.timeout_sec == 180
    assert cfg.igw_base_url is None


def test_triage_memory_config_rejects_empty_judges() -> None:
    # A council with no judges is meaningless; the spec must reject up-front
    # rather than letting the job fail later inside run_triage.
    import pytest
    from nemo_agents_plugin.jobs.triage_memory import TriageMemoryConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TriageMemoryConfig.model_validate({"corpus": "./USER.md", "judges": []})


def test_triage_memory_config_rejects_negative_max_tokens() -> None:
    import pytest
    from nemo_agents_plugin.jobs.triage_memory import TriageMemoryConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TriageMemoryConfig.model_validate(
            {"corpus": "./USER.md", "judges": ["x"], "max_tokens": 100}
        )  # below the 512 floor


def test_triage_memory_looks_pathy_dispatch() -> None:
    # Verify the path/fileset dispatch heuristic. Anything that starts with
    # a path sigil OR exists locally is treated as a path; everything else
    # falls through to fileset resolution.
    from nemo_agents_plugin.jobs.triage_memory import _looks_pathy

    assert _looks_pathy("./foo.md") is True
    assert _looks_pathy("/abs/path/USER.md") is True
    assert _looks_pathy("../USER.md") is True
    assert _looks_pathy("~/USER.md") is True
    # Bare names without a leading sigil and without a local file are
    # treated as fileset refs.
    assert _looks_pathy("my-corpus") is False
    assert _looks_pathy("my-workspace/user-corpus") is False


def test_triage_memory_resolve_corpus_yields_local_path(tmp_path) -> None:
    # When the corpus is a real local file, the resolver must yield it
    # unchanged (no fileset download attempted, no tempdir created).
    from nemo_agents_plugin.jobs.triage_memory import _resolve_corpus

    corpus = tmp_path / "USER.md"
    corpus.write_text("Entry one.\n\n§\n\nEntry two.\n", encoding="utf-8")
    with _resolve_corpus(str(corpus), workspace="default") as resolved:
        assert resolved == corpus.resolve()
        assert resolved.read_text(encoding="utf-8").startswith("Entry one.")


def test_triage_memory_resolve_corpus_missing_path_raises(tmp_path) -> None:
    from nemo_agents_plugin.jobs.triage_memory import _resolve_corpus

    with __import__("pytest").raises(RuntimeError, match="Corpus path does not exist"):
        with _resolve_corpus(str(tmp_path / "absent.md"), workspace="default"):
            pass
