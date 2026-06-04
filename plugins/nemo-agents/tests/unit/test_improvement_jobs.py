# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the new agent-improvement NemoJobs are discoverable + well-formed."""

from __future__ import annotations

from pathlib import Path


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
    # output defaults to None — falls back to ctx.storage.persistent / 'triage-output'
    # at run time, matching the EvaluateAgent convention. The Pydantic-level
    # default is None rather than a path string so the platform's persistent
    # volume is the source of truth, not the caller's CWD.
    assert cfg.output is None
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
    # unchanged (no fileset download attempted, no tempdir created). The
    # sdk argument is ignored on the path branch — passing None proves it.
    from nemo_agents_plugin.jobs.triage_memory import _resolve_corpus

    corpus = tmp_path / "USER.md"
    corpus.write_text("Entry one.\n\n§\n\nEntry two.\n", encoding="utf-8")
    with _resolve_corpus(str(corpus), workspace="default", sdk=None) as resolved:
        assert resolved == corpus.resolve()
        assert resolved.read_text(encoding="utf-8").startswith("Entry one.")


def test_triage_memory_resolve_corpus_missing_path_raises(tmp_path) -> None:
    from nemo_agents_plugin.jobs.triage_memory import _resolve_corpus

    with __import__("pytest").raises(RuntimeError, match="Corpus path does not exist"):
        with _resolve_corpus(str(tmp_path / "absent.md"), workspace="default", sdk=None):
            pass


def test_triage_memory_resolve_corpus_fileset_without_sdk_raises() -> None:
    # Fileset-shaped refs require an SDK; the helper raises early with an
    # actionable message rather than failing later inside the SDK call.
    import pytest
    from nemo_agents_plugin.jobs.triage_memory import _resolve_corpus

    with pytest.raises(RuntimeError, match="requires a 'sdk: NeMoPlatform'"):
        with _resolve_corpus("my-corpus-fileset", workspace="default", sdk=None):
            pass


def test_triage_memory_resolve_output_none_uses_persistent(tmp_path) -> None:
    # output=None falls back to ctx.storage.persistent / 'triage-output'
    # so artifacts survive across runs in the platform-injected volume.
    from nemo_agents_plugin.jobs.triage_memory import _resolve_output

    ctx = _make_fake_ctx(tmp_path)
    with _resolve_output(None, workspace="default", basename="x", ctx=ctx, sdk=None) as out:
        assert out == ctx.storage.persistent / "triage-output"
        assert out.is_dir()


def test_triage_memory_resolve_output_local_dir(tmp_path) -> None:
    # LocalDir-shaped output uses the path directly, mkdir -p semantics.
    from nemo_agents_plugin.jobs.triage_memory import _resolve_output
    from nemo_platform_plugin.refs import LocalDir

    ctx = _make_fake_ctx(tmp_path)
    target = tmp_path / "artifacts" / "subdir"
    with _resolve_output(LocalDir(str(target)), workspace="default", basename="x", ctx=ctx, sdk=None) as out:
        assert out == target.resolve()
        assert out.is_dir()


def test_triage_memory_resolve_output_fileset_without_sdk_raises(tmp_path) -> None:
    # Fileset output without an SDK raises BEFORE staging — we don't want
    # to run the job for 10min and then fail to deliver artifacts.
    import pytest
    from nemo_agents_plugin.jobs.triage_memory import _resolve_output
    from nemo_platform_plugin.refs import FilesetRef

    ctx = _make_fake_ctx(tmp_path)
    with pytest.raises(RuntimeError, match="requires a 'sdk: NeMoPlatform'"):
        with _resolve_output(
            FilesetRef("my-artifact-fileset"),
            workspace="default",
            basename="x",
            ctx=ctx,
            sdk=None,
        ):
            pass


def test_triage_memory_resolve_output_fileset_uploads_on_success(tmp_path) -> None:
    # Happy-path fileset upload: yields a tempdir, after the with-block
    # exits cleanly the helper calls sdk.files.upload for each artifact
    # (basename.json + basename.md) with fileset_auto_create=True.
    from nemo_agents_plugin.jobs.triage_memory import _resolve_output
    from nemo_platform_plugin.refs import FilesetRef

    ctx = _make_fake_ctx(tmp_path)
    sdk = _FakeSDK()
    with _resolve_output(
        FilesetRef("ws-x/my-artifact-fileset"),
        workspace="default",
        basename="run1",
        ctx=ctx,
        sdk=sdk,  # type: ignore[arg-type]
    ) as staging:
        # Simulate write_artifacts: produce the two-file pair.
        (staging / "run1.json").write_text("{}", encoding="utf-8")
        (staging / "run1.md").write_text("# triage\n", encoding="utf-8")

    # Both files uploaded with the inlined workspace, auto-create on.
    assert len(sdk.uploads) == 2
    suffixes = {Path(u["local_path"]).suffix for u in sdk.uploads}
    assert suffixes == {".json", ".md"}
    for upload in sdk.uploads:
        assert upload["fileset"] == "my-artifact-fileset"
        assert upload["workspace"] == "ws-x"
        assert upload["fileset_auto_create"] is True


def test_triage_memory_resolve_output_fileset_skips_upload_on_error(tmp_path) -> None:
    # If the job body raises inside the with-block, the upload is skipped —
    # we don't want partial / broken artifacts polluting the fileset.
    from nemo_agents_plugin.jobs.triage_memory import _resolve_output
    from nemo_platform_plugin.refs import FilesetRef

    ctx = _make_fake_ctx(tmp_path)
    sdk = _FakeSDK()
    with __import__("pytest").raises(RuntimeError, match="simulated"):
        with _resolve_output(
            FilesetRef("my-artifact-fileset"),
            workspace="default",
            basename="run1",
            ctx=ctx,
            sdk=sdk,  # type: ignore[arg-type]
        ):
            raise RuntimeError("simulated job-body failure")

    assert sdk.uploads == []


class _FakeSDK:
    """Minimal SDK double for fileset-upload tests.

    Records every files.upload call so the test can assert on what would
    have been uploaded without actually contacting the platform.
    """

    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.files = self

    def upload(self, **kwargs):  # noqa: ANN003 — mirror sdk.files.upload's kwargs-only shape
        self.uploads.append(kwargs)


def _make_fake_ctx(tmp_path):
    # Build the minimum JobContext shape _resolve_output reads from: a
    # storage.persistent / storage.ephemeral pair backed by real dirs.
    from types import SimpleNamespace

    persistent = tmp_path / "persistent"
    ephemeral = tmp_path / "ephemeral"
    persistent.mkdir()
    ephemeral.mkdir()
    return SimpleNamespace(storage=SimpleNamespace(persistent=persistent, ephemeral=ephemeral))
