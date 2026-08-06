# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the on-the-fly aggregate artifacts download handler."""

from __future__ import annotations

import io
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from nemo_auditor.jobs.artifacts_route import aggregate_artifacts_download
from nemo_platform_plugin.jobs.file_manager import TmpDirPath


def _make_result(name: str, artifact_url: str = "file:///fake") -> MagicMock:
    r = MagicMock()
    r.name = name
    r.artifact_url = artifact_url
    return r


def _make_results_page(*names: str) -> MagicMock:
    page = MagicMock()
    page.data = [_make_result(n) for n in names]
    return page


def _make_tmp_file(tmp_path: Path, name: str, content: bytes = b"data") -> TmpDirPath:
    tmp_dir = Path(tempfile.mkdtemp(dir=tmp_path))
    file_path = tmp_dir / name
    file_path.write_bytes(content)
    return TmpDirPath(path=file_path, tmp_dir=tmp_dir)


@dataclass
class _FakeSdk:
    pass


def _make_jobs_client_mock(results_page: Any) -> MagicMock:
    client = MagicMock()
    list_resp = MagicMock()
    list_resp.data.return_value = results_page
    client.list_job_results = AsyncMock(return_value=list_resp)
    return client


@pytest.mark.asyncio
class TestAggregateArtifactsDownload:
    async def test_happy_path_returns_tar_with_all_results(self, tmp_path: Path) -> None:
        results = _make_results_page("report-html", "report-jsonl")
        html_tmp = _make_tmp_file(tmp_path, "report-html", b"<html/>")
        jsonl_tmp = _make_tmp_file(tmp_path, "report-jsonl", b'{"probe":"x"}')

        download_side_effects = [
            ("report-html", html_tmp),
            ("report-jsonl", jsonl_tmp),
        ]

        background_tasks = MagicMock()
        sdk = _FakeSdk()

        with (
            patch(
                "nemo_auditor.jobs.artifacts_route.client_from_platform",
                return_value=_make_jobs_client_mock(results),
            ),
            patch(
                "nemo_auditor.jobs.artifacts_route.download_from_result_info",
                new=AsyncMock(side_effect=download_side_effects),
            ),
        ):
            response = await aggregate_artifacts_download(
                workspace="default",
                job="audit-job-123",
                background_tasks=background_tasks,
                sdk=sdk,  # type: ignore[arg-type]
            )

        assert isinstance(response, FileResponse)
        tar_path = Path(response.path)
        assert tar_path.exists()
        with tarfile.open(tar_path, "r:gz") as tar:
            members = {m.name for m in tar.getmembers()}
        assert "report-html" in members
        assert "report-jsonl" in members
        # cleanup scheduled for both individual tmp dirs + aggregate dir
        assert background_tasks.add_task.call_count == 3

    async def test_partial_results_skips_missing(self, tmp_path: Path) -> None:
        # Only report-html present; report-jsonl and report-hitlog-jsonl absent
        results = _make_results_page("report-html")
        html_tmp = _make_tmp_file(tmp_path, "report-html", b"<html/>")

        background_tasks = MagicMock()
        sdk = _FakeSdk()

        with (
            patch(
                "nemo_auditor.jobs.artifacts_route.client_from_platform",
                return_value=_make_jobs_client_mock(results),
            ),
            patch(
                "nemo_auditor.jobs.artifacts_route.download_from_result_info",
                new=AsyncMock(return_value=("report-html", html_tmp)),
            ),
        ):
            response = await aggregate_artifacts_download(
                workspace="default",
                job="audit-job-456",
                background_tasks=background_tasks,
                sdk=sdk,  # type: ignore[arg-type]
            )

        assert isinstance(response, FileResponse)
        with tarfile.open(Path(response.path), "r:gz") as tar:
            members = {m.name for m in tar.getmembers()}
        assert members == {"report-html"}

    async def test_no_relevant_results_raises_404(self) -> None:
        # Job has a result, but not one of the known Garak names
        results = _make_results_page("some-other-result")

        background_tasks = MagicMock()
        sdk = _FakeSdk()

        with (
            patch(
                "nemo_auditor.jobs.artifacts_route.client_from_platform",
                return_value=_make_jobs_client_mock(results),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await aggregate_artifacts_download(
                    workspace="default",
                    job="audit-job-789",
                    background_tasks=background_tasks,
                    sdk=sdk,  # type: ignore[arg-type]
                )

        assert exc_info.value.status_code == 404

    async def test_empty_results_raises_404(self) -> None:
        results = _make_results_page()

        background_tasks = MagicMock()
        sdk = _FakeSdk()

        with (
            patch(
                "nemo_auditor.jobs.artifacts_route.client_from_platform",
                return_value=_make_jobs_client_mock(results),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await aggregate_artifacts_download(
                    workspace="default",
                    job="audit-job-000",
                    background_tasks=background_tasks,
                    sdk=sdk,  # type: ignore[arg-type]
                )

        assert exc_info.value.status_code == 404
