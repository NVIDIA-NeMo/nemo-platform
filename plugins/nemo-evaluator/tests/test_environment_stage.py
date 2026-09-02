# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from unittest.mock import Mock

import pytest
from nemo_evaluator.jobs.environment_stage import EnvironmentStageJob
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults


def _context(tmp_path: Path) -> JobContext:
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    return JobContext(
        workspace="dev",
        job_id="job-1",
        storage=StoragePaths(ephemeral=tmp_path / "ephemeral", persistent=persistent),
        results=LocalJobResults(tmp_path / "results"),
    )


def test_stages_environment_at_fixed_persistent_path(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    sdk = Mock()

    def download(**kwargs) -> None:
        Path(kwargs["local_path"], "nemo-environment.yaml").write_text("format: wheels-v1\n")

    sdk.files.download.side_effect = download

    result = EnvironmentStageJob().run(
        {"environment": "shared/custom-gym"},
        ctx=ctx,
        sdk=sdk,
    )

    sdk.files.download.assert_called_once_with(
        fileset="custom-gym",
        workspace="shared",
        local_path=str(ctx.storage.persistent / ".environment-staging"),
    )
    assert (ctx.storage.persistent / "environment" / "nemo-environment.yaml").is_file()
    assert (ctx.storage.persistent / "workspace").is_dir()
    assert not (ctx.storage.persistent / ".environment-staging").exists()
    assert result["path"] == str(ctx.storage.persistent / "environment")


def test_staged_fileset_preserves_wheels_tree(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    sdk = Mock()
    wheel_name = "xmltodict-1.0.4-py3-none-any.whl"
    config_rel = Path("resources_servers") / "structeval" / "configs" / "structeval_nonrenderable.yaml"

    def download(**kwargs) -> None:
        root = Path(kwargs["local_path"])
        (root / "nemo-environment.yaml").write_text("format: wheels-v1\n")
        config = root / config_rel
        config.parent.mkdir(parents=True)
        config.write_text("structeval: {}\n")
        wheels = root / "wheels"
        wheels.mkdir()
        (wheels / wheel_name).write_bytes(b"wheel")

    sdk.files.download.side_effect = download

    EnvironmentStageJob().run({"environment": "dev/structeval-wheels"}, ctx=ctx, sdk=sdk)

    environment = ctx.storage.persistent / "environment"
    assert (environment / "nemo-environment.yaml").is_file()
    assert (environment / config_rel).is_file()
    assert (environment / "wheels" / wheel_name).read_bytes() == b"wheel"
    assert not (ctx.storage.persistent / ".environment-staging").exists()


def test_failed_download_removes_partial_staging_without_replacing_environment(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    environment = ctx.storage.persistent / "environment"
    environment.mkdir()
    (environment / "existing.txt").write_text("complete")
    sdk = Mock()

    def fail_download(**kwargs) -> None:
        Path(kwargs["local_path"], "partial.txt").write_text("partial")
        raise RuntimeError("download failed")

    sdk.files.download.side_effect = fail_download

    with pytest.raises(RuntimeError, match="download failed"):
        EnvironmentStageJob().run(
            {"environment": "custom-gym"},
            ctx=ctx,
            sdk=sdk,
        )

    assert (environment / "existing.txt").read_text() == "complete"
    assert not (ctx.storage.persistent / ".environment-staging").exists()
    assert (ctx.storage.persistent / "workspace").is_dir()
