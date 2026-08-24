# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared customization file_io runner."""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest


def _make_runner(sdk, *, service_source: str = "unsloth", workspace: str = "default", storage_path: Path | None = None):
    from nmp.customization_common.service.context import NMPJobContext
    from nmp.customization_common.tasks.file_io.run import FileIORunner
    from nmp.customization_common.tasks.file_io_progress_reporter import NoOpProgressReporter

    job_ctx = NMPJobContext(
        workspace=workspace,
        job_id="job-1",
        attempt_id="attempt-0",
        step="model-upload",
        task="task-1",
        jobs_url=None,
        files_url=None,
        storage_path=storage_path or Path("/tmp"),
        config_path=Path("/tmp/cfg.json"),
    )
    return FileIORunner(
        sdk=sdk,
        progress_reporter=NoOpProgressReporter(),
        job_ctx=job_ctx,
        service_source=service_source,
    )


def _make_sdk() -> MagicMock:
    sdk = MagicMock()
    sdk.with_options.return_value = sdk
    return sdk


def _raise_runner_conflict() -> None:
    import sys

    run_mod = sys.modules["nmp.customization_common.tasks.file_io.run"]
    raise run_mod.ConflictError.__new__(run_mod.ConflictError, "already exists")


def _make_dir(tmp_path: Path) -> Path:
    src = tmp_path / "checkpoint"
    src.mkdir()
    (src / "adapter_model.safetensors").write_bytes(b"\x00" * 16)
    (src / "tokenizer.json").write_text("{}")
    return src


class TestCreateFileset:
    @patch("nmp.customization_common.tasks.file_io.run.client_from_platform")
    def test_creates_fileset_with_service_source_and_metadata(self, mock_cfp) -> None:
        from nemo_platform_plugin.files.types import CreateFilesetRequest
        from nmp.customization_common.schemas.file_io import FileSetRef

        mock_fc = MagicMock()
        mock_fc.with_options.return_value = mock_fc
        mock_cfp.return_value = mock_fc
        sdk = _make_sdk()
        runner = _make_runner(sdk, service_source="automodel")
        metadata = {"model": {"tool_calling": {"tool_call_parser": "llama3_json"}}}
        dest = FileSetRef(workspace="default", name="qwen-test")

        runner.create_fileset(dest, metadata=metadata)

        mock_fc.create_fileset.assert_called_once()
        call = mock_fc.create_fileset.call_args
        assert call.kwargs["workspace"] == "default"
        body = call.kwargs["body"]
        assert isinstance(body, CreateFilesetRequest)
        assert body.name == "qwen-test"
        assert body.custom_fields == {"service_source": "automodel"}
        assert body.metadata is not None
        assert body.metadata.model is not None
        assert body.metadata.model.tool_calling.tool_call_parser == "llama3_json"

    @patch("nmp.customization_common.tasks.file_io.run.client_from_platform")
    def test_conflict_patches_metadata_on_existing(self, mock_cfp) -> None:
        from nemo_platform_plugin.files.types import UpdateFilesetRequest
        from nmp.customization_common.schemas.file_io import FileSetRef

        mock_fc = MagicMock()
        mock_fc.with_options.return_value = mock_fc
        mock_fc.create_fileset.side_effect = lambda **_: _raise_runner_conflict()
        mock_cfp.return_value = mock_fc
        sdk = _make_sdk()
        runner = _make_runner(sdk, service_source="rl")
        dest = FileSetRef(workspace="default", name="exists")
        metadata = {"model": {"tool_calling": {"tool_call_parser": "hermes"}}}

        runner.create_fileset(dest, metadata=metadata)

        mock_fc.update_fileset.assert_called_once()
        update_call = mock_fc.update_fileset.call_args
        assert update_call.kwargs["workspace"] == "default"
        assert update_call.kwargs["name"] == "exists"
        body = update_call.kwargs["body"]
        assert isinstance(body, UpdateFilesetRequest)
        assert body.metadata is not None
        assert body.metadata.model is not None
        assert body.metadata.model.tool_calling.tool_call_parser == "hermes"

    @patch("nmp.customization_common.tasks.file_io.run.client_from_platform")
    def test_conflict_no_metadata_skips_update(self, mock_cfp) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef

        mock_fc = MagicMock()
        mock_fc.with_options.return_value = mock_fc
        mock_fc.create_fileset.side_effect = lambda **_: _raise_runner_conflict()
        mock_cfp.return_value = mock_fc
        sdk = _make_sdk()
        runner = _make_runner(sdk)
        dest = FileSetRef(workspace="default", name="exists")

        runner.create_fileset(dest, metadata=None)

        mock_fc.update_fileset.assert_not_called()


class TestUploadFileset:
    def test_directory_uploads_with_trailing_slash(self, tmp_path: Path) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef

        sdk = _make_sdk()
        runner = _make_runner(sdk)
        src = _make_dir(tmp_path)
        dest = FileSetRef(workspace="default", name="qwen-test")

        runner.upload_fileset(dest, src.resolve())

        sdk.files.upload_file.assert_called_once()
        call = sdk.files.upload_file.call_args
        assert call.kwargs["local_path"] == f"{src.resolve()}/"
        assert call.kwargs["remote_path"] == ""
        assert call.kwargs["fileset"] == "qwen-test"
        assert call.kwargs["workspace"] == "default"

    def test_upload_failure_propagates_as_file_upload_error(self, tmp_path: Path) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef, FileUploadError

        sdk = _make_sdk()
        sdk.files.upload_file.side_effect = RuntimeError("upload broke")
        runner = _make_runner(sdk)
        src = _make_dir(tmp_path)
        dest = FileSetRef(workspace="default", name="x")

        with pytest.raises(FileUploadError, match="upload broke"):
            runner.upload_fileset(dest, src.resolve())


class TestDownloadFileset:
    def test_lists_then_downloads(self, tmp_path: Path) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef

        sdk = _make_sdk()
        sdk.files.list_files.return_value = types.SimpleNamespace(
            data=[
                types.SimpleNamespace(path="model.safetensors", size=100),
                types.SimpleNamespace(path="config.json", size=20),
            ]
        )
        runner = _make_runner(sdk)
        dest = tmp_path / "downloads"
        fileset = FileSetRef(workspace="default", name="qwen")

        runner.download_fileset(fileset, dest)

        sdk.files.list_files.assert_called_once()
        sdk.files.download_file.assert_called_once()
        call = sdk.files.download_file.call_args
        assert call.kwargs["fileset"] == "qwen"
        assert call.kwargs["workspace"] == "default"
        assert call.kwargs["local_path"] == str(dest.resolve())
        assert dest.exists()

    def test_empty_fileset_returns_zero_stats_without_downloading(self, tmp_path: Path) -> None:
        from nmp.customization_common.schemas.file_io import FileSetRef

        sdk = _make_sdk()
        sdk.files.list_files.return_value = types.SimpleNamespace(data=[])
        runner = _make_runner(sdk)
        dest = tmp_path / "downloads"
        fileset = FileSetRef(workspace="default", name="empty")

        stats = runner.download_fileset(fileset, dest)

        assert stats.files_downloaded == 0
        assert stats.total_bytes == 0
        sdk.files.download_file.assert_not_called()


@pytest.fixture
def no_retry_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip tenacity's exponential backoff so retry tests don't sleep for seconds.

    ``tenacity.nap.sleep`` resolves ``time.sleep`` per call, so patching it here
    takes effect even though the retry policy was bound at decoration time.
    """
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _seconds: None)


class TestCreateFilesetRetry:
    """Create goes through the typed client, so it must catch the typed client's errors."""

    @patch("nmp.customization_common.tasks.file_io.run.client_from_platform")
    def test_retries_transport_error_wrapped_by_the_client(self, mock_cfp, no_retry_backoff) -> None:
        from nemo_platform_plugin.client.errors import NemoTransportError
        from nmp.customization_common.schemas.file_io import FileSetRef

        mock_fc = MagicMock()
        mock_fc.with_options.return_value = mock_fc
        mock_fc.create_fileset.side_effect = [NemoTransportError(httpx.ConnectError("refused")), MagicMock()]
        mock_cfp.return_value = mock_fc
        runner = _make_runner(_make_sdk())

        runner.create_fileset(FileSetRef(workspace="default", name="models"))

        assert mock_fc.create_fileset.call_count == 2

    @patch("nmp.customization_common.tasks.file_io.run.client_from_platform")
    def test_retries_rate_limit_wrapped_by_the_client(self, mock_cfp, no_retry_backoff) -> None:
        from nemo_platform_plugin.client.errors import RateLimitError
        from nmp.customization_common.schemas.file_io import FileSetRef

        response = httpx.Response(429, request=httpx.Request("POST", "http://test/filesets"), json={"detail": "slow"})
        mock_fc = MagicMock()
        mock_fc.with_options.return_value = mock_fc
        mock_fc.create_fileset.side_effect = [RateLimitError(response), MagicMock()]
        mock_cfp.return_value = mock_fc
        runner = _make_runner(_make_sdk())

        runner.create_fileset(FileSetRef(workspace="default", name="models"))

        assert mock_fc.create_fileset.call_count == 2


class TestUploadRetry:
    """The task layer owns upload retries.

    The typed client cannot retry a streaming upload — the body is a one-shot
    iterator, and replaying it under the original Content-Length makes h11 abort
    the request. So the client raises through, and this layer, which rebuilds the
    request from the source file on every attempt, is where the retry belongs.
    """

    def test_retries_transport_error_wrapped_by_the_client(self, tmp_path: Path, no_retry_backoff) -> None:
        from nemo_platform_plugin.client.errors import NemoTransportError
        from nmp.customization_common.schemas.file_io import FileSetRef

        src = _make_dir(tmp_path)
        sdk = _make_sdk()
        sdk.files.upload_file.side_effect = [NemoTransportError(httpx.ReadTimeout("timed out")), None]
        runner = _make_runner(sdk)

        runner.upload_fileset(FileSetRef(workspace="default", name="models"), src.resolve())

        assert sdk.files.upload_file.call_count == 2

    def test_retries_server_error_wrapped_by_the_client(self, tmp_path: Path, no_retry_backoff) -> None:
        from nemo_platform_plugin.client.errors import InternalServerError
        from nmp.customization_common.schemas.file_io import FileSetRef

        src = _make_dir(tmp_path)
        sdk = _make_sdk()
        response = httpx.Response(503, request=httpx.Request("PUT", "http://test/upload"), json={"detail": "down"})
        sdk.files.upload_file.side_effect = [InternalServerError(response), None]
        runner = _make_runner(sdk)

        runner.upload_fileset(FileSetRef(workspace="default", name="models"), src.resolve())

        assert sdk.files.upload_file.call_count == 2

    def test_retries_rate_limit_wrapped_by_the_client(self, tmp_path: Path, no_retry_backoff) -> None:
        """429 is in the client's retryable statuses, but it cannot act on it here."""
        from nemo_platform_plugin.client.errors import RateLimitError
        from nmp.customization_common.schemas.file_io import FileSetRef

        src = _make_dir(tmp_path)
        sdk = _make_sdk()
        response = httpx.Response(429, request=httpx.Request("PUT", "http://test/upload"), json={"detail": "slow down"})
        sdk.files.upload_file.side_effect = [RateLimitError(response), None]
        runner = _make_runner(sdk)

        runner.upload_fileset(FileSetRef(workspace="default", name="models"), src.resolve())

        assert sdk.files.upload_file.call_count == 2

    def test_gives_up_as_a_file_upload_error(self, tmp_path: Path, no_retry_backoff) -> None:
        from nemo_platform_plugin.client.errors import NemoTransportError
        from nmp.customization_common.schemas.file_io import FileSetRef, FileUploadError

        src = _make_dir(tmp_path)
        sdk = _make_sdk()
        sdk.files.upload_file.side_effect = NemoTransportError(httpx.ReadTimeout("timed out"))
        runner = _make_runner(sdk)

        with pytest.raises(FileUploadError):
            runner.upload_fileset(FileSetRef(workspace="default", name="models"), src.resolve())

        assert sdk.files.upload_file.call_count == 3
