# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the memory-plugin NemoJobs: discovery, metadata, config validation.

The end-to-end triage / eval / export logic is covered by the per-primitive
tests in this directory; this file focuses on the job wrappers themselves
(name + container + spec validation + the path/fileset dispatch helpers).
"""

from __future__ import annotations

from pathlib import Path


def test_memory_jobs_discovered_via_entry_points() -> None:
    from nemo_platform_plugin.discovery import discover_jobs

    jobs = discover_jobs()
    assert "memory.triage" in jobs
    assert "memory.eval" in jobs
    assert "memory.export" in jobs


def test_triage_job_metadata() -> None:
    from nemo_memory_plugin.jobs.triage import TriageJob

    assert TriageJob.name == "triage"
    assert TriageJob.container == "cpu-tasks"


def test_triage_config_minimum_validation() -> None:
    from nemo_memory_plugin.jobs.triage import TriageConfig

    cfg = TriageConfig.model_validate({"corpus": "./USER.md", "judges": ["azure-anthropic-claude-sonnet-4-6"]})
    assert cfg.corpus == "./USER.md"
    assert cfg.judges == ["azure-anthropic-claude-sonnet-4-6"]
    assert cfg.store_name == "pi-hermes:memory"
    assert cfg.workspace == "default"
    # output defaults to None — falls back to ctx.storage.persistent / 'triage-output'
    # at run time. The Pydantic-level default is None so the platform's
    # persistent volume is the source of truth, not the caller's CWD.
    assert cfg.output is None
    assert cfg.basename == "triage"
    assert cfg.max_tokens == 4096
    assert cfg.max_entries is None
    assert cfg.timeout_sec == 180
    assert cfg.igw_base_url is None


def test_triage_config_rejects_empty_judges() -> None:
    # A council with no judges is meaningless; the spec must reject up-front
    # rather than letting the job fail later inside run_triage.
    import pytest
    from nemo_memory_plugin.jobs.triage import TriageConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TriageConfig.model_validate({"corpus": "./USER.md", "judges": []})


def test_triage_config_rejects_negative_max_tokens() -> None:
    import pytest
    from nemo_memory_plugin.jobs.triage import TriageConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TriageConfig.model_validate({"corpus": "./USER.md", "judges": ["x"], "max_tokens": 100})  # below the 512 floor


def test_eval_job_metadata() -> None:
    from nemo_memory_plugin.jobs.eval import EvalJob

    assert EvalJob.name == "eval"
    assert EvalJob.container == "cpu-tasks"


def test_eval_config_minimum_validation() -> None:
    from nemo_memory_plugin.jobs.eval import EvalConfig

    cfg = EvalConfig.model_validate({"baseline": "./a.json", "candidate": "./b.json"})
    assert cfg.baseline == "./a.json"
    assert cfg.candidate == "./b.json"
    assert cfg.workspace == "default"
    assert cfg.output is None  # falls back to ctx.storage.persistent at run time
    assert cfg.basename == "memory-eval"


def test_eval_config_requires_both_inputs() -> None:
    # Without either baseline or candidate the spec is meaningless; the
    # Pydantic validation should reject up-front, not let the job fail
    # later trying to load None.
    import pytest
    from nemo_memory_plugin.jobs.eval import EvalConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EvalConfig.model_validate({"baseline": "./a.json"})
    with pytest.raises(ValidationError):
        EvalConfig.model_validate({"candidate": "./b.json"})


def test_export_job_metadata() -> None:
    from nemo_memory_plugin.jobs.export import ExportJob

    assert ExportJob.name == "export"
    assert ExportJob.container == "cpu-tasks"


def test_export_config_minimum_validation() -> None:
    from nemo_memory_plugin.jobs.export import ExportConfig

    cfg = ExportConfig.model_validate(
        {
            "triage_artifact": "./triage.json",
            "corpus": "./USER.md",
            "reference_judge": "azure-anthropic-claude-sonnet-4-5",
        }
    )
    assert cfg.triage_artifact == "./triage.json"
    assert cfg.corpus == "./USER.md"
    assert cfg.reference_judge == "azure-anthropic-claude-sonnet-4-5"
    assert cfg.candidate_judge is None
    assert cfg.only_disagreements is False
    assert cfg.basename == "finetune-corpus"


def test_export_config_requires_required_inputs() -> None:
    import pytest
    from nemo_memory_plugin.jobs.export import ExportConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExportConfig.model_validate({"triage_artifact": "./a.json", "corpus": "./b.md"})
    with pytest.raises(ValidationError):
        ExportConfig.model_validate({"corpus": "./b.md", "reference_judge": "sonnet"})
    with pytest.raises(ValidationError):
        ExportConfig.model_validate({"triage_artifact": "./a.json", "reference_judge": "sonnet"})


# ---------------------------------------------------------------------------
# Path/fileset dispatch helpers + output-resolution context manager.
# ---------------------------------------------------------------------------


def test_looks_pathy_dispatch() -> None:
    # Verify the path/fileset dispatch heuristic. Anything that starts with
    # a path sigil OR exists locally is treated as a path; everything else
    # falls through to fileset resolution.
    from nemo_memory_plugin.triage.fileset_io import looks_pathy as _looks_pathy

    assert _looks_pathy("./foo.md") is True
    assert _looks_pathy("/abs/path/USER.md") is True
    assert _looks_pathy("../USER.md") is True
    assert _looks_pathy("~/USER.md") is True
    # Bare names without a leading sigil and without a local file are
    # treated as fileset refs.
    assert _looks_pathy("my-corpus") is False
    assert _looks_pathy("my-workspace/user-corpus") is False


def test_resolve_corpus_yields_local_path(tmp_path) -> None:
    # When the corpus is a real local file, the resolver must yield it
    # unchanged (no fileset download attempted, no tempdir created). The
    # sdk argument is ignored on the path branch — passing None proves it.
    from nemo_memory_plugin.jobs.triage import _resolve_corpus

    corpus = tmp_path / "USER.md"
    corpus.write_text("Entry one.\n\n§\n\nEntry two.\n", encoding="utf-8")
    with _resolve_corpus(str(corpus), workspace="default", sdk=None) as resolved:
        assert resolved == corpus.resolve()
        assert resolved.read_text(encoding="utf-8").startswith("Entry one.")


def test_resolve_corpus_missing_path_raises(tmp_path) -> None:
    from nemo_memory_plugin.jobs.triage import _resolve_corpus

    with __import__("pytest").raises(RuntimeError, match="Corpus path does not exist"):
        with _resolve_corpus(str(tmp_path / "absent.md"), workspace="default", sdk=None):
            pass


def test_resolve_corpus_fileset_without_sdk_raises() -> None:
    # Fileset-shaped refs require an SDK; the helper raises early with an
    # actionable message rather than failing later inside the SDK call.
    import pytest
    from nemo_memory_plugin.jobs.triage import _resolve_corpus

    with pytest.raises(RuntimeError, match="requires a 'sdk: NeMoPlatform'"):
        with _resolve_corpus("my-corpus-fileset", workspace="default", sdk=None):
            pass


def test_resolve_output_none_uses_persistent(tmp_path) -> None:
    # output=None falls back to ctx.storage.persistent / persistent_subdir
    # so artifacts survive across runs in the platform-injected volume.
    from nemo_memory_plugin.triage.fileset_io import resolve_output_target

    ctx = _make_fake_ctx(tmp_path)
    with resolve_output_target(
        None,
        workspace="default",
        basename="x",
        ctx=ctx,
        sdk=None,
        persistent_subdir="triage-output",
        job_label="triage",
    ) as out:
        assert out == ctx.storage.persistent / "triage-output"
        assert out.is_dir()


def test_resolve_output_local_dir(tmp_path) -> None:
    # LocalDir-shaped output uses the path directly, mkdir -p semantics.
    from nemo_memory_plugin.triage.fileset_io import resolve_output_target
    from nemo_platform_plugin.refs import LocalDir

    ctx = _make_fake_ctx(tmp_path)
    target = tmp_path / "artifacts" / "subdir"
    with resolve_output_target(
        LocalDir(str(target)),
        workspace="default",
        basename="x",
        ctx=ctx,
        sdk=None,
        persistent_subdir="triage-output",
        job_label="triage",
    ) as out:
        assert out == target.resolve()
        assert out.is_dir()


def test_resolve_output_fileset_without_sdk_raises(tmp_path) -> None:
    # Fileset output without an SDK raises BEFORE staging — we don't want
    # to run the job for 10min and then fail to deliver artifacts.
    import pytest
    from nemo_memory_plugin.triage.fileset_io import resolve_output_target
    from nemo_platform_plugin.refs import FilesetRef

    ctx = _make_fake_ctx(tmp_path)
    with pytest.raises(RuntimeError, match="requires a 'sdk: NeMoPlatform'"):
        with resolve_output_target(
            FilesetRef("my-artifact-fileset"),
            workspace="default",
            basename="x",
            ctx=ctx,
            sdk=None,
            persistent_subdir="triage-output",
            job_label="triage",
        ):
            pass


def test_resolve_output_fileset_uploads_on_success(tmp_path) -> None:
    # Happy-path fileset upload: yields a tempdir, after the with-block
    # exits cleanly the helper calls sdk.files.upload for each artifact
    # (basename.json + basename.md) with fileset_auto_create=True.
    from nemo_memory_plugin.triage.fileset_io import resolve_output_target
    from nemo_platform_plugin.refs import FilesetRef

    ctx = _make_fake_ctx(tmp_path)
    sdk = _FakeSDK()
    with resolve_output_target(
        FilesetRef("ws-x/my-artifact-fileset"),
        workspace="default",
        basename="run1",
        ctx=ctx,
        sdk=sdk,  # type: ignore[arg-type]
        persistent_subdir="triage-output",
        job_label="triage",
    ) as staging:
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


def test_resolve_output_fileset_skips_upload_on_error(tmp_path) -> None:
    # If the job body raises inside the with-block, the upload is skipped —
    # we don't want partial / broken artifacts polluting the fileset.
    from nemo_memory_plugin.triage.fileset_io import resolve_output_target
    from nemo_platform_plugin.refs import FilesetRef

    ctx = _make_fake_ctx(tmp_path)
    sdk = _FakeSDK()
    with __import__("pytest").raises(RuntimeError, match="simulated"):
        with resolve_output_target(
            FilesetRef("my-artifact-fileset"),
            workspace="default",
            basename="run1",
            ctx=ctx,
            sdk=sdk,  # type: ignore[arg-type]
            persistent_subdir="triage-output",
            job_label="triage",
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

    def upload(self, **kwargs):  # noqa: ANN003
        self.uploads.append(kwargs)


def _make_fake_ctx(tmp_path):
    # Build the minimum JobContext shape resolve_output_target reads from:
    # a storage.persistent / storage.ephemeral pair backed by real dirs.
    from types import SimpleNamespace

    persistent = tmp_path / "persistent"
    ephemeral = tmp_path / "ephemeral"
    persistent.mkdir()
    ephemeral.mkdir()
    return SimpleNamespace(storage=SimpleNamespace(persistent=persistent, ephemeral=ephemeral))
