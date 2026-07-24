# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared fileset staging helpers used by agents jobs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from nemo_agents_plugin.jobs.fileset_io import resolve_output, resolve_staged_config, split_fileset_ref
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.refs import FilesetRef


def test_resolve_staged_config_local_pass_through(tmp_path: Path, ctx: JobContext) -> None:
    target = str(tmp_path / "optimize.yml")
    with resolve_staged_config(target, None, workspace="default", ctx=ctx, sdk=None, kind="optimize-config") as p:
        assert p == Path(target)


@pytest.mark.parametrize("ref", ["", "/name", "workspace/", "workspace/name/extra"])
def test_split_fileset_ref_rejects_invalid_refs(ref: str) -> None:
    with pytest.raises(ValueError, match="invalid entity reference"):
        split_fileset_ref(ref, "default")


def test_resolve_staged_config_fileset_downloads_via_sdk(tmp_path: Path, ctx: JobContext) -> None:
    sdk = MagicMock()

    def _fake_download(local_path: str, fileset: str, workspace: str) -> None:
        Path(local_path, "optimize.yml").write_text("optimizer: {}")

    sdk.files.download.side_effect = _fake_download

    with resolve_staged_config(
        "optimize.yml",
        FilesetRef("nemo-agent-optimize-calc"),
        workspace="default",
        ctx=ctx,
        sdk=sdk,
        kind="optimize-config",
    ) as resolved:
        assert resolved.is_file()
        assert resolved.name == "optimize.yml"
        assert resolved.read_text() == "optimizer: {}"

    sdk.files.download.assert_called_once()
    kwargs = sdk.files.download.call_args.kwargs
    assert kwargs["fileset"] == "nemo-agent-optimize-calc"
    assert kwargs["workspace"] == "default"


def test_resolve_staged_config_fileset_without_sdk_raises(ctx: JobContext) -> None:
    with pytest.raises(Exception) as exc:
        with resolve_staged_config(
            "optimize.yml",
            FilesetRef("fs"),
            workspace="default",
            ctx=ctx,
            sdk=None,
            kind="optimize-config",
        ):
            pass
    assert "sdk" in str(exc.value).lower()


def test_resolve_staged_config_empty_fileset_ref_is_invalid(ctx: JobContext) -> None:
    with pytest.raises(ValueError, match="invalid entity reference"):
        with resolve_staged_config(
            "optimize.yml",
            FilesetRef(""),
            workspace="default",
            ctx=ctx,
            sdk=None,
            kind="optimize-config",
        ):
            pass


def test_resolve_staged_config_rejects_path_escape(ctx: JobContext) -> None:
    sdk = MagicMock()
    sdk.files.download.side_effect = lambda local_path, fileset, workspace: None
    with pytest.raises(ValueError, match="outside the downloaded fileset"):
        with resolve_staged_config(
            "../evil.yml",
            FilesetRef("fs"),
            workspace="default",
            ctx=ctx,
            sdk=sdk,
            kind="optimize-config",
        ):
            pass


def test_resolve_output_none_uses_persistent_results(ctx: JobContext) -> None:
    with resolve_output(None, workspace="default", ctx=ctx, sdk=None, kind="optimize") as base:
        assert base == ctx.storage.persistent / "results"
        assert base.is_dir()


def test_resolve_output_fileset_uploads_on_clean_exit(ctx: JobContext) -> None:
    sdk = MagicMock()
    sdk.files.upload.return_value = MagicMock(name="fake-fileset")

    with resolve_output(FilesetRef("optimize-out"), workspace="default", ctx=ctx, sdk=sdk, kind="optimize"):
        pass

    sdk.files.upload.assert_called_once()
    kwargs = sdk.files.upload.call_args.kwargs
    assert kwargs["fileset"] == "optimize-out"
    assert kwargs["workspace"] == "default"
    assert kwargs["fileset_auto_create"] is True
    assert kwargs["local_path"].endswith("/")


def test_resolve_output_fileset_skips_upload_when_body_raises(ctx: JobContext) -> None:
    sdk = MagicMock()
    with pytest.raises(RuntimeError, match="boom"):
        with resolve_output(FilesetRef("optimize-out"), workspace="default", ctx=ctx, sdk=sdk, kind="optimize"):
            raise RuntimeError("boom")
    sdk.files.upload.assert_not_called()


def test_resolve_output_empty_fileset_ref_is_invalid(ctx: JobContext) -> None:
    sdk = MagicMock()
    with pytest.raises(ValueError, match="invalid entity reference"):
        with resolve_output(FilesetRef(""), workspace="default", ctx=ctx, sdk=sdk, kind="optimize"):
            pass
    sdk.files.upload.assert_not_called()
