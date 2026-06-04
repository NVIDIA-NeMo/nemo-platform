# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the file_io task."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from nemo_platform import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from nemo_platform.filesets import ListFilesResponse
from nemo_platform.types.files.fileset_file import FilesetFile
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.customizer.app.jobs.context import NMPJobContext
from nmp.customizer.app.jobs.file_io.schemas import (
    FILESET_PROTOCOL,
    DownloadItem,
    DownloadStats,
    FileDownloadError,
    FileIOTaskConfig,
    FileSetRef,
    FileUploadError,
    PathTraversalError,
    TaskPhase,
    UploadItem,
)
from nmp.customizer.tasks.file_io.run import (
    MAX_RETRIES,
    FileIORunner,
    run,
)
from nmp.customizer.tasks.file_io.utils import (
    filesystem_sdk_error_handler,
    get_config,
    sdk_error_handler,
    validate_safe_path,
    validate_storage_path,
)
from pydantic import ValidationError
from pytest_mock import MockerFixture


@dataclass
class FileIORunnerMocks:
    """Container for FileIORunner mock objects."""

    sdk: MagicMock
    progress_reporter: MagicMock
    filesystem: MagicMock
    job_ctx: NMPJobContext


@pytest.fixture
def job_ctx(tmp_path: Path) -> NMPJobContext:
    """Fixture providing a NMPJobContext for testing.

    Creates a job context with a temporary storage path.

    Returns:
        NMPJobContext for testing.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    return NMPJobContext(
        workspace="test-workspace",
        job_id="test-job-123",
        attempt_id="attempt-0",
        step="test-step",
        task="test-task",
        jobs_url="http://jobs:8000",
        files_url="http://files:8000",
        storage_path=tmp_path,
        config_path=config_path,
    )


@pytest.fixture
def file_io_runner_mocks(mocker: MockerFixture, job_ctx: NMPJobContext) -> FileIORunnerMocks:
    """Fixture providing mocked dependencies for FileIORunner.

    Creates mock SDK, progress reporter, and files resource objects.
    Sets up sdk.with_options(...).files to return the mock files resource.

    Returns:
        FileIORunnerMocks containing all mock objects needed for FileIORunner tests.

    """
    mock_sdk = mocker.MagicMock()
    mock_progress_reporter = mocker.MagicMock()
    mock_filesystem = mocker.MagicMock()
    # sdk.with_options(...) returns a new SDK; .files has upload/download/list methods.
    # Set on both the default with_options return value and on mock_sdk itself,
    # because some tests override with_options.return_value = mock_sdk for create_fileset.
    mock_sdk.with_options.return_value.files = mock_filesystem
    mock_sdk.files = mock_filesystem
    return FileIORunnerMocks(
        sdk=mock_sdk,
        progress_reporter=mock_progress_reporter,
        filesystem=mock_filesystem,
        job_ctx=job_ctx,
    )


@dataclass
class DownloadCallbackMocks:
    """Container for download callback mock objects."""

    tqdm: MagicMock
    jobs: MagicMock
    composite: MagicMock


@pytest.fixture
def mock_download_callbacks(mocker: MockerFixture) -> DownloadCallbackMocks:
    """Fixture that patches download callback classes.

    Patches TqdmPerFileDownloadCallback, FileDownloadProgressCallback, and CompositeCallback
    to avoid actual progress reporting during tests.

    Returns:
        DownloadCallbackMocks containing the patched mock classes.

    """
    return DownloadCallbackMocks(
        tqdm=mocker.patch("nmp.customizer.shared.tasks.file_io.runner.TqdmPerFileDownloadCallback"),
        jobs=mocker.patch("nmp.customizer.shared.tasks.file_io.runner.FileDownloadProgressCallback"),
        composite=mocker.patch("nmp.customizer.shared.tasks.file_io.runner.CompositeCallback"),
    )


class TestFileSetRef:
    """Tests for FileSetRef schema."""

    @pytest.mark.parametrize(
        ("ref", "expected_name"),
        [
            ("default/my-model", "my-model"),
            (f"{FILESET_PROTOCOL}default/my-model", "my-model"),
            ("my-model", "my-model"),
        ],
        ids=["workspace_name", "fileset_protocol", "name_only"],
    )
    def test_extract_name(self, ref: str, expected_name: str):
        """Should extract resource name from supported ref formats."""
        assert FileSetRef.extract_name(ref) == expected_name

    def test_create_with_explicit_fields(self):
        """Should create FileSetRef with explicit workspace and name."""
        ref = FileSetRef(workspace="my-workspace", name="my-fileset")
        assert ref.workspace == "my-workspace"
        assert ref.name == "my-fileset"

    def test_str_returns_workspace_slash_name(self):
        """Should return 'workspace/name' string representation."""
        ref = FileSetRef(workspace="default", name="my-model")
        assert str(ref) == "default/my-model"

    def test_parse_from_string_via_model_validator(self):
        """Should auto-parse 'workspace/name' string during construction."""
        ref = FileSetRef.model_validate("default/my-model")
        assert ref.workspace == "default"
        assert ref.name == "my-model"

    def test_model_validate_with_fileset_protocol(self):
        """Should parse 'fileset://workspace/name' URI via model_validate()."""
        ref = FileSetRef.model_validate(f"{FILESET_PROTOCOL}default/my-model")
        assert ref.workspace == "default"
        assert ref.name == "my-model"

    def test_model_validate_name_only_reference(self):
        """Should allow name-only reference with workspace=None."""
        ref = FileSetRef.model_validate("my-model")
        assert ref.workspace is None
        assert ref.name == "my-model"

    def test_model_validate_empty_string_raises(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValidationError):
            FileSetRef.model_validate("")

    def test_str_returns_name_only_when_workspace_is_none(self):
        """Should return just the name when workspace is None."""
        ref = FileSetRef(workspace=None, name="my-model")
        assert str(ref) == "my-model"

    def test_equality(self):
        """Should compare equal when workspace and name match."""
        ref1 = FileSetRef(workspace="default", name="model")
        ref2 = FileSetRef(workspace="default", name="model")
        ref3 = FileSetRef(workspace="other", name="model")

        assert ref1 == ref2
        assert ref1 != ref3

    def test_model_dump(self):
        """Should serialize to dict with workspace and name."""
        ref = FileSetRef(workspace="default", name="my-model")
        dumped = ref.model_dump()
        assert dumped == {"workspace": "default", "name": "my-model"}


class TestDownloadItem:
    """Tests for DownloadItem schema."""

    def test_create_with_string_src(self):
        """Should parse string src into FileSetRef."""
        item = DownloadItem(src=FileSetRef(workspace="default", name="my-model"))
        assert isinstance(item.src, FileSetRef)
        assert item.src.workspace == "default"
        assert item.src.name == "my-model"

    def test_create_with_fileset_ref_src(self):
        """Should accept FileSetRef directly."""
        ref = FileSetRef(workspace="default", name="my-model")
        item = DownloadItem(src=ref)
        assert item.src == ref

    def test_default_dest_is_dot(self):
        """Should default dest to '.' (current directory)."""
        item = DownloadItem(src=FileSetRef(workspace="default", name="my-model"))
        assert item.dest == "."

    def test_custom_dest(self):
        """Should accept custom dest path."""
        item = DownloadItem(src=FileSetRef(workspace="default", name="my-model"), dest="models/base")
        assert item.dest == "models/base"

    def test_name_only_src_parsed_as_name_only_reference(self):
        """Should parse name-only string as FileSetRef with workspace=None."""
        item = DownloadItem.model_validate({"src": "my-model"})
        assert isinstance(item.src, FileSetRef)
        assert item.src.workspace is None
        assert item.src.name == "my-model"

    def test_model_dump(self):
        """Should serialize src as dict (FileSetRef fields)."""
        item = DownloadItem(src=FileSetRef(workspace="default", name="my-model"), dest="model")
        dumped = item.model_dump()
        assert dumped == {
            "src": {"workspace": "default", "name": "my-model"},
            "dest": "model",
        }


class TestUploadItem:
    """Tests for UploadItem schema."""

    def test_create_with_string_dest(self):
        """Should parse string dest into FileSetRef."""
        item = UploadItem(src="outputs", dest=FileSetRef(workspace="default", name="results"))
        assert item.src == "outputs"
        assert isinstance(item.dest, FileSetRef)
        assert item.dest.workspace == "default"
        assert item.dest.name == "results"

    def test_create_with_fileset_ref_dest(self):
        """Should accept FileSetRef directly for dest."""
        ref = FileSetRef(workspace="default", name="results")
        item = UploadItem(src="outputs", dest=ref)
        assert item.dest == ref

    def test_name_only_dest_parsed_as_name_only_reference(self):
        """Should parse name-only string as FileSetRef with workspace=None."""
        item = UploadItem.model_validate({"src": "outputs", "dest": "my-results"})
        assert isinstance(item.dest, FileSetRef)
        assert item.dest.workspace is None
        assert item.dest.name == "my-results"

    def test_model_dump(self):
        """Should serialize dest as dict (FileSetRef fields)."""
        item = UploadItem(src="outputs", dest=FileSetRef(workspace="default", name="results"))
        dumped = item.model_dump()
        assert dumped == {
            "src": "outputs",
            "dest": {"workspace": "default", "name": "results"},
            "metadata": None,
        }


class TestFileIOTaskConfig:
    """Tests for FileIOTaskConfig schema."""

    def test_empty_config(self):
        """Should create config with empty lists when no data provided."""
        config = FileIOTaskConfig()
        assert config.download == []
        assert config.upload == []

    def test_config_with_downloads(self):
        """Should create config with download items from dicts."""
        config = FileIOTaskConfig(
            download=[
                DownloadItem(src=FileSetRef(workspace="default", name="my-model"), dest="model"),
                DownloadItem(src=FileSetRef(workspace="default", name="my-dataset"), dest="dataset"),
            ],
        )
        assert len(config.download) == 2

        assert config.download[0].src.workspace == "default"
        assert config.download[0].src.name == "my-model"
        assert config.download[0].dest == "model"

        assert config.download[1].src.workspace == "default"
        assert config.download[1].src.name == "my-dataset"
        assert config.download[1].dest == "dataset"

    def test_config_with_uploads(self):
        """Should create config with upload items from dicts."""
        config = FileIOTaskConfig(
            upload=[UploadItem(src="model", dest=FileSetRef(workspace="default", name="output-model"))],
        )
        assert len(config.upload) == 1
        assert config.upload[0].src == "model"
        assert config.upload[0].dest == FileSetRef(workspace="default", name="output-model")

    def test_model_validate_from_dict(self):
        """Should validate and create config from dict."""
        data = {
            "download": [{"src": "default/test-model", "dest": "model"}],
            "upload": [],
        }
        config = FileIOTaskConfig.model_validate(data)
        assert len(config.download) == 1
        assert config.download[0].src.workspace == "default"
        assert config.download[0].src.name == "test-model"

    def test_model_dump_json_roundtrip(self):
        """Should serialize to JSON and parse back."""
        config = FileIOTaskConfig(
            download=[DownloadItem(src=FileSetRef(workspace="default", name="my-model"), dest="model")],
        )
        json_str = config.model_dump_json()
        data = json.loads(json_str)

        # Verify structure
        assert "download" in data
        assert len(data["download"]) == 1
        assert data["download"][0]["src"] == {"workspace": "default", "name": "my-model"}
        assert data["download"][0]["dest"] == "model"

        # Verify roundtrip
        config2 = FileIOTaskConfig.model_validate(data)
        assert config2.download[0].src == config.download[0].src


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_raises_when_file_not_exists(self):
        """Should raise FileNotFoundError when config file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            get_config(Path("/nonexistent/path.json"))

    def test_get_config_loads_and_validates_json_from_file(self, tmp_path: Path):
        """Should load JSON config and validate it into FileIOTaskConfig."""
        config_data = {
            "download": [
                {"src": "default/my-model", "dest": "model"},
                {"src": "default/my-dataset", "dest": "dataset"},
            ],
            "upload": [],
        }

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        result = get_config(config_path)

        assert result.model_dump() == {
            "download": [
                {"src": {"workspace": "default", "name": "my-model"}, "dest": "model"},
                {"src": {"workspace": "default", "name": "my-dataset"}, "dest": "dataset"},
            ],
            "upload": [],
        }


class TestValidateStoragePath:
    """Tests for validate_storage_path function."""

    def test_validate_storage_path_returns_path_when_exists(self, tmp_path: Path):
        """Should return storage path when it exists and is a directory."""
        result = validate_storage_path(tmp_path)
        assert result == tmp_path

    def test_validate_storage_path_raises_error_when_path_does_not_exist(self):
        """Should raise FileUploadError when storage path does not exist."""
        with pytest.raises(FileUploadError, match="Storage path does not exist"):
            validate_storage_path(Path("/non/existent/path"))

    def test_validate_storage_path_raises_error_when_path_is_not_directory(self, tmp_path: Path):
        """Should raise FileUploadError when storage path is a file, not a directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        with pytest.raises(FileUploadError, match="Storage path does not exist"):
            validate_storage_path(file_path)


class TestValidateSafePath:
    """Tests for validate_safe_path function."""

    def test_validate_safe_path_accepts_simple_relative_path(self, tmp_path: Path):
        """Should accept a simple relative path within base directory."""
        result = validate_safe_path(tmp_path, "subdir/file.txt")
        assert result == tmp_path / "subdir" / "file.txt"

    def test_validate_safe_path_accepts_current_dir(self, tmp_path: Path):
        """Should accept current directory reference."""
        result = validate_safe_path(tmp_path, ".")
        assert result == tmp_path

    def test_validate_safe_path_accepts_nested_path(self, tmp_path: Path):
        """Should accept deeply nested paths."""
        result = validate_safe_path(tmp_path, "a/b/c/d/e/file.txt")
        assert result == tmp_path / "a" / "b" / "c" / "d" / "e" / "file.txt"

    def test_validate_safe_path_accepts_path_with_dot_segments(self, tmp_path: Path):
        """Should accept paths with . segments that resolve within base."""
        result = validate_safe_path(tmp_path, "subdir/./file.txt")
        assert result == tmp_path / "subdir" / "file.txt"

    def test_validate_safe_path_accepts_path_with_parent_that_stays_within(self, tmp_path: Path):
        """Should accept paths with .. that still resolve within base."""
        result = validate_safe_path(tmp_path, "subdir/../other/file.txt")
        assert result == tmp_path / "other" / "file.txt"

    def test_validate_safe_path_rejects_parent_traversal(self, tmp_path: Path):
        """Should reject path traversal that escapes base directory."""
        with pytest.raises(PathTraversalError) as exc_info:
            validate_safe_path(tmp_path, "../escape.txt")

        assert "resolves outside of the base directory" in str(exc_info.value)
        assert "path traversal attack" in str(exc_info.value)

    def test_validate_safe_path_rejects_deep_parent_traversal(self, tmp_path: Path):
        """Should reject deep path traversal attack."""
        with pytest.raises(PathTraversalError) as exc_info:
            validate_safe_path(tmp_path, "../../../../../../etc/passwd")

        assert "resolves outside of the base directory" in str(exc_info.value)

    def test_validate_safe_path_rejects_mixed_traversal(self, tmp_path: Path):
        """Should reject path that goes up then down but still escapes."""
        with pytest.raises(PathTraversalError) as exc_info:
            validate_safe_path(tmp_path, "subdir/../../escape.txt")

        assert "resolves outside of the base directory" in str(exc_info.value)

    def test_validate_safe_path_rejects_absolute_path_outside_base(self, tmp_path: Path):
        """Should reject absolute paths that don't resolve within base."""
        with pytest.raises(PathTraversalError) as exc_info:
            validate_safe_path(tmp_path, "/etc/passwd")

        assert "resolves outside of the base directory" in str(exc_info.value)

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "../..",
            "../../..",
            "../secret",
            "foo/../../bar/../../../etc/passwd",
        ],
    )
    def test_validate_safe_path_rejects_various_traversal_patterns(self, tmp_path: Path, malicious_path: str):
        """Should reject various path traversal attack patterns."""
        with pytest.raises(PathTraversalError):
            validate_safe_path(tmp_path, malicious_path)

    @pytest.mark.parametrize(
        "safe_path,expected_suffix",
        [
            ("data", "data"),
            ("data/models", "data/models"),
            (".", ""),
            ("./data", "data"),
            ("data/./models", "data/models"),
            ("a/b/../b/c", "a/b/c"),
        ],
    )
    def test_validate_safe_path_accepts_various_safe_patterns(
        self,
        tmp_path: Path,
        safe_path: str,
        expected_suffix: str,
    ):
        """Should accept various safe path patterns."""
        result = validate_safe_path(tmp_path, safe_path)
        if expected_suffix:
            assert result == tmp_path / expected_suffix
        else:
            assert result == tmp_path


class TestSdkErrorHandler:
    """Tests for sdk_error_handler context manager."""

    def test_sdk_error_handler_success_no_exception(self):
        """Should complete successfully when no exception is raised."""
        with sdk_error_handler(FileDownloadError, "test operation"):
            pass  # No exception raised

    def test_sdk_error_handler_handles_api_timeout_error(self, mocker: MockerFixture):
        """Should catch APITimeoutError and raise FileDownloadError with timeout message."""
        mock_httpx_request = mocker.MagicMock(spec=httpx.Request)

        with pytest.raises(FileDownloadError, match="due to request timeout error"):
            with sdk_error_handler(FileDownloadError, "test operation"):
                raise APITimeoutError(request=mock_httpx_request)

    def test_sdk_error_handler_handles_api_connection_error(self, mocker: MockerFixture):
        """Should catch APIConnectionError and raise FileDownloadError with connection error message."""
        mock_httpx_request = mocker.MagicMock(spec=httpx.Request)

        with pytest.raises(FileDownloadError, match="due to connection error"):
            with sdk_error_handler(FileDownloadError, "test operation"):
                raise APIConnectionError(message="Connection refused", request=mock_httpx_request)

    def test_sdk_error_handler_handles_api_status_error(self, mocker: MockerFixture):
        """Should catch APIStatusError and raise FileDownloadError with API error message."""
        mock_httpx_response = mocker.MagicMock(spec=httpx.Response)
        mock_httpx_response.status_code = 500

        with pytest.raises(FileDownloadError, match="due to API error.*Status code: 500"):
            with sdk_error_handler(FileDownloadError, "test operation"):
                raise APIStatusError("Server Error", response=mock_httpx_response, body=None)

    def test_sdk_error_handler_handles_authentication_error(self, mocker: MockerFixture):
        """Should catch AuthenticationError and raise FileDownloadError with auth error message."""
        mock_httpx_response = mocker.MagicMock(spec=httpx.Response)
        mock_httpx_response.status_code = 401

        with pytest.raises(FileDownloadError, match="due to authentication error"):
            with sdk_error_handler(FileDownloadError, "test operation"):
                raise AuthenticationError("Unauthorized", response=mock_httpx_response, body=None)

    def test_sdk_error_handler_handles_permission_denied_error(self, mocker: MockerFixture):
        """Should catch PermissionDeniedError and raise FileDownloadError with permission denied message."""
        mock_httpx_response = mocker.MagicMock(spec=httpx.Response)
        mock_httpx_response.status_code = 403

        with pytest.raises(FileDownloadError, match="due to permission denied error"):
            with sdk_error_handler(FileDownloadError, "test operation"):
                raise PermissionDeniedError("Forbidden", response=mock_httpx_response, body=None)

    def test_sdk_error_handler_handles_generic_exception(self):
        """Should catch generic exceptions and raise with unexpected error message."""
        with pytest.raises(FileDownloadError, match="due to unexpected error"):
            with sdk_error_handler(FileDownloadError, "test operation"):
                raise RuntimeError("Something unexpected")

    def test_sdk_error_handler_passthrough_exception(self, mocker: MockerFixture):
        """Should pass through exceptions in passthrough tuple."""
        mock_httpx_response = mocker.MagicMock(spec=httpx.Response)
        mock_httpx_response.status_code = 404

        with pytest.raises(NotFoundError):
            with sdk_error_handler(FileDownloadError, "test operation", passthrough=(NotFoundError,)):
                raise NotFoundError("Not Found", response=mock_httpx_response, body=None)

    def test_sdk_error_handler_with_file_upload_error_class(self, mocker: MockerFixture):
        """Should use FileUploadError when specified."""
        mock_httpx_request = mocker.MagicMock(spec=httpx.Request)

        with pytest.raises(FileUploadError, match="due to connection error"):
            with sdk_error_handler(FileUploadError, "upload operation"):
                raise APIConnectionError(message="Connection refused", request=mock_httpx_request)

    def test_sdk_error_handler_includes_operation_in_message(self, mocker: MockerFixture):
        """Should include operation description in error message."""
        mock_httpx_request = mocker.MagicMock(spec=httpx.Request)

        with pytest.raises(FileDownloadError, match="Failed to download file from fileset"):
            with sdk_error_handler(FileDownloadError, "download file from fileset"):
                raise APIConnectionError(message="Connection error", request=mock_httpx_request)


class TestFilesystemSdkErrorHandler:
    """Tests for filesystem_sdk_error_handler context manager."""

    def test_success_no_exception(self):
        """Should complete successfully when no exception is raised."""
        with filesystem_sdk_error_handler(FileDownloadError, "test operation"):
            pass

    def test_handles_httpx_timeout_exception(self):
        """Should catch httpx.TimeoutException and raise with timeout message."""
        with pytest.raises(FileDownloadError, match="due to request timeout"):
            with filesystem_sdk_error_handler(FileDownloadError, "download file"):
                raise httpx.ReadTimeout("read timed out")

    def test_handles_httpx_connect_error(self):
        """Should catch httpx.ConnectError and raise with connection error message."""
        with pytest.raises(FileDownloadError, match="due to connection error"):
            with filesystem_sdk_error_handler(FileDownloadError, "download file"):
                raise httpx.ConnectError("connection refused")

    def test_handles_file_not_found_error(self):
        """Should catch FileNotFoundError and raise with file not found message."""
        with pytest.raises(FileDownloadError, match="due to file not found error"):
            with filesystem_sdk_error_handler(FileDownloadError, "download file"):
                raise FileNotFoundError("no such file")

    def test_handles_permission_error(self):
        """Should catch PermissionError and raise with permission denied message."""
        with pytest.raises(FileUploadError, match="due to permission denied error"):
            with filesystem_sdk_error_handler(FileUploadError, "upload file"):
                raise PermissionError("access denied")

    def test_handles_generic_exception(self):
        """Should catch generic exceptions and raise with unexpected error message."""
        with pytest.raises(FileDownloadError, match="due to unexpected error"):
            with filesystem_sdk_error_handler(FileDownloadError, "test operation"):
                raise RuntimeError("Something unexpected")

    def test_passthrough_exception(self):
        """Should pass through exceptions in passthrough tuple."""
        with pytest.raises(KeyboardInterrupt):
            with filesystem_sdk_error_handler(FileDownloadError, "test operation", passthrough=(KeyboardInterrupt,)):
                raise KeyboardInterrupt

    def test_timeout_includes_operation_in_message(self):
        """Should include operation description in timeout error message."""
        with pytest.raises(FileDownloadError, match="Failed to download model weights"):
            with filesystem_sdk_error_handler(FileDownloadError, "download model weights"):
                raise httpx.ReadTimeout("read timed out")

    def test_connect_error_with_upload_error_class(self):
        """Should use FileUploadError when specified."""
        with pytest.raises(FileUploadError, match="due to connection error"):
            with filesystem_sdk_error_handler(FileUploadError, "upload file"):
                raise httpx.ConnectError("connection refused")


class TestDownloadFileset:
    """Tests for FileIORunner.download_fileset method."""

    def test_download_fileset_success(self, mocker: MockerFixture, file_io_runner_mocks: FileIORunnerMocks):
        """Should download files from fileset and return stats."""
        mocks = file_io_runner_mocks

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[
                FilesetFile(
                    file_ref="ref1", file_url="/v2/files/ref1", path="config.json", size=100, cache_status=None
                ),
                FilesetFile(file_ref="ref2", file_url="/v2/files/ref2", path="model.bin", size=1000, cache_status=None),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir) / "output"

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="default", name="my-model")
            stats = runner.download_fileset(fileset, dest_dir)

            # Verify download was called with correct args
            mocks.filesystem.download.assert_called_once()
            call_args = mocks.filesystem.download.call_args
            assert call_args.kwargs["fileset"] == "my-model"
            assert call_args.kwargs["workspace"] == "default"
            assert call_args.kwargs["local_path"] == str(dest_dir)

            # Verify destination directory was created
            assert dest_dir.exists()

            # Stats should be returned (actual values updated by callbacks)
            assert isinstance(stats, DownloadStats)

    def test_download_fileset_empty_fileset_returns_empty_stats(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should return empty stats when fileset contains no files."""
        mocks = file_io_runner_mocks

        # Mock empty list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(data=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir) / "output"

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="default", name="empty-fileset")
            stats = runner.download_fileset(fileset, dest_dir)

            # Should not call filesystem.download for empty fileset
            mocks.filesystem.download.assert_not_called()

            # Should return empty stats
            assert stats.files_downloaded == 0
            assert stats.total_bytes == 0

    def test_download_fileset_creates_dest_directory(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should create destination directory if it doesn't exist."""
        mocks = file_io_runner_mocks

        # Mock list_files response with one file - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file.txt", size=100, cache_status=None)]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a nested path that doesn't exist
            dest_dir = Path(tmpdir) / "nested" / "deep" / "output"
            assert not dest_dir.exists()

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="ws", name="fileset")
            runner.download_fileset(fileset, dest_dir)

            # Destination directory should now exist
            assert dest_dir.exists()
            assert dest_dir.is_dir()

    def test_download_fileset_raises_on_filesystem_error(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should raise FileDownloadError when filesystem download fails."""
        mocks = file_io_runner_mocks
        mocks.filesystem.download.side_effect = Exception("Network error")

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file.txt", size=100, cache_status=None)]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir) / "output"

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="default", name="my-model")

            with pytest.raises(FileDownloadError, match="unexpected error"):
                runner.download_fileset(fileset, dest_dir)

    def test_download_fileset_raises_when_fileset_not_found(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should raise FileDownloadError when fileset is not found."""
        mocks = file_io_runner_mocks

        # Mock list_files to raise NotFoundError
        mock_response = mocker.MagicMock()
        mock_response.status_code = 404
        mocks.sdk.with_options.return_value.files.list.side_effect = NotFoundError(
            message="Not Found",
            response=mock_response,
            body=None,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir) / "output"

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="default", name="nonexistent")

            with pytest.raises(FileDownloadError, match="not found"):
                runner.download_fileset(fileset, dest_dir)

    def test_download_fileset_creates_composite_callback(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should create composite callback with tqdm and jobs progress callbacks."""
        mocks = file_io_runner_mocks

        # Mock callback classes to verify they're instantiated correctly
        mock_tqdm_callback = mocker.MagicMock()
        mock_tqdm_class = mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.TqdmPerFileDownloadCallback",
            return_value=mock_tqdm_callback,
        )

        mock_jobs_callback = mocker.MagicMock()
        mock_jobs_class = mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.FileDownloadProgressCallback",
            return_value=mock_jobs_callback,
        )

        mock_composite_callback = mocker.MagicMock()
        mock_composite_class = mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.CompositeCallback",
            return_value=mock_composite_callback,
        )

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[
                FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file1.txt", size=100, cache_status=None),
                FilesetFile(file_ref="ref2", file_url="/v2/files/ref2", path="file2.txt", size=200, cache_status=None),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir) / "output"

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="default", name="my-model")
            runner.download_fileset(fileset, dest_dir)

            # Verify TqdmPerFileDownloadCallback was created with correct args
            mock_tqdm_class.assert_called_once()
            tqdm_kwargs = mock_tqdm_class.call_args.kwargs
            assert tqdm_kwargs["dest_path"] == dest_dir
            assert tqdm_kwargs["fileset_path"] == "default/my-model"
            assert tqdm_kwargs["file_sizes"] == {"file1.txt": 100, "file2.txt": 200}

            # Verify FileDownloadProgressCallback was created with correct args
            mock_jobs_class.assert_called_once()
            jobs_kwargs = mock_jobs_class.call_args.kwargs
            assert jobs_kwargs["progress_reporter"] == mocks.progress_reporter
            assert jobs_kwargs["fileset_name"] == "default/my-model"
            assert jobs_kwargs["total_files"] == 2
            assert jobs_kwargs["total_size"] == 300

            # Verify CompositeCallback was created with both callbacks
            mock_composite_class.assert_called_once_with(mock_tqdm_callback, mock_jobs_callback)

            # Verify filesystem.get was called with composite callback
            call_kwargs = mocks.filesystem.download.call_args.kwargs
            assert call_kwargs["callback"] == mock_composite_callback

    def test_download_fileset_handles_leading_slash_in_file_paths(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should strip leading slashes from file paths when building file_sizes map."""
        mocks = file_io_runner_mocks

        # Mock list_files response with leading slashes in paths - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[
                FilesetFile(
                    file_ref="ref1", file_url="/v2/files/ref1", path="/dir/file1.txt", size=100, cache_status=None
                ),
                FilesetFile(file_ref="ref2", file_url="/v2/files/ref2", path="/file2.txt", size=200, cache_status=None),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir) / "output"

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="ws", name="model")
            runner.download_fileset(fileset, dest_dir)

            # Verify file_sizes has leading slashes stripped
            tqdm_kwargs = mock_download_callbacks.tqdm.call_args.kwargs
            assert tqdm_kwargs["file_sizes"] == {"dir/file1.txt": 100, "file2.txt": 200}


class TestRunDownload:
    """Tests for FileIORunner.run_download method."""

    def test_run_download_skips_when_no_downloads(self, file_io_runner_mocks: FileIORunnerMocks):
        """Should skip download when no downloads are configured."""
        mocks = file_io_runner_mocks

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        runner.run_download([])

        # Should not call filesystem download or list_files
        mocks.filesystem.download.assert_not_called()
        mocks.sdk.with_options.return_value.files.list.assert_not_called()
        mocks.progress_reporter.update_progress.assert_not_called()

    def test_run_download_downloads_from_single_fileset(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should download files from a single fileset."""
        mocks = file_io_runner_mocks

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[
                FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="model.bin", size=1000, cache_status=None)
            ]
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        downloads = [
            DownloadItem(src=FileSetRef(workspace="default", name="my-model"), dest="model"),
        ]
        runner.run_download(downloads)

        # Should have listed files in the fileset
        mocks.sdk.with_options.return_value.files.list.assert_called_once()

        # Should have called get on filesystem
        mocks.filesystem.download.assert_called_once()

        # Verify destination path is correct
        expected_dest = mocks.job_ctx.storage_path / "model"
        call_args = mocks.filesystem.download.call_args
        assert call_args.kwargs["local_path"] == str(expected_dest)

    def test_run_download_downloads_from_multiple_filesets(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should download from multiple filesets."""
        mocks = file_io_runner_mocks

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file.txt", size=100, cache_status=None)]
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        downloads = [
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset1"), dest="model"),
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset2"), dest="dataset"),
        ]
        runner.run_download(downloads)

        # Should have listed files for each fileset
        assert mocks.sdk.with_options.return_value.files.list.call_count == 2

        # Should have called download for each fileset
        assert mocks.filesystem.download.call_count == 2

    def test_run_download_reports_initial_progress(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should report initial progress with correct status details."""
        mocks = file_io_runner_mocks

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file.txt", size=100, cache_status=None)]
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        downloads = [
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset"), dest="model"),
        ]
        runner.run_download(downloads)

        # Verify progress was reported at least twice (initial + per-fileset)
        assert mocks.progress_reporter.update_progress.call_count >= 2

        # Check initial progress call
        initial_call = mocks.progress_reporter.update_progress.call_args_list[0]
        assert initial_call[1]["status"] == PlatformJobStatus.ACTIVE
        assert initial_call[1]["status_details"]["phase"] == TaskPhase.DOWNLOADING
        assert initial_call[1]["status_details"]["total_filesets"] == 1
        assert initial_call[1]["status_details"]["completed_filesets"] == 0

    def test_run_download_reports_progress_per_fileset(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should report progress for each fileset during download."""
        mocks = file_io_runner_mocks

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file.txt", size=100, cache_status=None)]
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        downloads = [
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset1"), dest="model"),
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset2"), dest="dataset"),
        ]
        runner.run_download(downloads)

        # Find progress calls with current_fileset
        progress_calls = [
            call
            for call in mocks.progress_reporter.update_progress.call_args_list
            if "current_fileset" in call[1].get("status_details", {})
        ]

        # Should have progress call for each fileset
        assert len(progress_calls) == 2

        # First fileset progress
        first_call_details = progress_calls[0][1]["status_details"]
        assert first_call_details["current_fileset"] == "ws/fileset1"
        assert first_call_details["completed_filesets"] == 0
        assert first_call_details["total_filesets"] == 2

        # Second fileset progress
        second_call_details = progress_calls[1][1]["status_details"]
        assert second_call_details["current_fileset"] == "ws/fileset2"
        assert second_call_details["completed_filesets"] == 1
        assert second_call_details["total_filesets"] == 2

    def test_run_download_accumulates_stats(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should accumulate stats from all downloads."""
        mocks = file_io_runner_mocks

        # Mock list_files to return different sizes for each fileset - list() returns ListFilesResponse
        call_count = [0]

        def list_files_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ListFilesResponse(
                    data=[
                        FilesetFile(
                            file_ref="ref1", file_url="/v2/files/ref1", path="file1.txt", size=100, cache_status=None
                        ),
                        FilesetFile(
                            file_ref="ref2", file_url="/v2/files/ref2", path="file2.txt", size=200, cache_status=None
                        ),
                    ]
                )
            else:
                return ListFilesResponse(
                    data=[
                        FilesetFile(
                            file_ref="ref3", file_url="/v2/files/ref3", path="file3.txt", size=300, cache_status=None
                        ),
                    ]
                )

        mocks.sdk.with_options.return_value.files.list.side_effect = list_files_side_effect

        # Capture logger calls to verify stats logging
        mock_logger = mocker.patch("nmp.customizer.shared.tasks.file_io.runner.logger")

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        downloads = [
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset1"), dest="model"),
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset2"), dest="dataset"),
        ]
        runner.run_download(downloads)

        # Verify final log message indicates all downloads completed
        info_calls = [call for call in mock_logger.info.call_args_list]
        final_log_found = any("All downloads complete" in str(call) for call in info_calls)
        assert final_log_found

    def test_run_download_propagates_download_error(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should propagate FileDownloadError when download fails."""
        mocks = file_io_runner_mocks
        mocks.filesystem.download.side_effect = Exception("Download failed")

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file.txt", size=100, cache_status=None)]
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        downloads = [
            DownloadItem(src=FileSetRef(workspace="ws", name="fileset"), dest="model"),
        ]

        with pytest.raises(FileDownloadError, match="unexpected error"):
            runner.run_download(downloads)

    def test_run_download_uses_correct_dest_path(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
        mock_download_callbacks: DownloadCallbackMocks,
    ):
        """Should compute correct destination path from storage path and item dest."""
        mocks = file_io_runner_mocks

        # Mock list_files response - list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[FilesetFile(file_ref="ref1", file_url="/v2/files/ref1", path="file.txt", size=100, cache_status=None)]
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        downloads = [
            DownloadItem(src=FileSetRef(workspace="ws", name="model"), dest="nested/path/model"),
        ]
        runner.run_download(downloads)

        # Verify destination path is storage_path / item.dest
        expected_dest = mocks.job_ctx.storage_path / "nested" / "path" / "model"
        call_args = mocks.filesystem.download.call_args
        assert call_args.kwargs["local_path"] == str(expected_dest)


class TestListFilesetFiles:
    """Tests for FileIORunner.list_fileset_files method."""

    def test_list_fileset_files_success(self, mocker: MockerFixture, file_io_runner_mocks: FileIORunnerMocks):
        """Should return list of files from FileSet."""
        mocks = file_io_runner_mocks
        # list() returns a ListFilesResponse
        mocks.sdk.with_options.return_value.files.list.return_value = ListFilesResponse(
            data=[
                FilesetFile(
                    file_ref="ref1", file_url="/v2/files/ref1", path="config.json", size=100, cache_status=None
                ),
                FilesetFile(file_ref="ref2", file_url="/v2/files/ref2", path="model.bin", size=1000, cache_status=None),
            ]
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        fileset = FileSetRef(workspace="default", name="my-model")
        files = runner.list_fileset_files(fileset)

        assert len(files) == 2
        assert files[0].path == "config.json"
        assert files[1].path == "model.bin"

    def test_list_fileset_files_not_found(self, mocker: MockerFixture, file_io_runner_mocks: FileIORunnerMocks):
        """Should raise FileDownloadError when FileSet not found."""
        mocks = file_io_runner_mocks
        mock_response = mocker.MagicMock()
        mock_response.status_code = 404
        mocks.sdk.with_options.return_value.files.list.side_effect = NotFoundError(
            message="Not Found",
            response=mock_response,
            body=None,
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        fileset = FileSetRef(workspace="default", name="nonexistent")

        with pytest.raises(FileDownloadError, match="not found"):
            runner.list_fileset_files(fileset)

    def test_list_fileset_files_raises_on_api_connection_error(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should raise FileDownloadError on APIConnectionError."""
        mocks = file_io_runner_mocks
        mock_httpx_request = mocker.MagicMock(spec=httpx.Request)
        mocks.sdk.with_options.return_value.files.list.side_effect = APIConnectionError(
            message="Connection failed",
            request=mock_httpx_request,
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        fileset = FileSetRef(workspace="default", name="my-model")

        with pytest.raises(FileDownloadError, match="Failed to list files .* due to connection error"):
            runner.list_fileset_files(fileset)


class TestCreateFileset:
    """Tests for FileIORunner.create_fileset method."""

    def test_create_fileset_success(self, file_io_runner_mocks: FileIORunnerMocks):
        """Should create a fileset successfully."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        fileset = FileSetRef(workspace="default", name="new-fileset")
        runner.create_fileset(fileset)

        mocks.sdk.files.filesets.create.assert_called_once()
        call_kwargs = mocks.sdk.files.filesets.create.call_args.kwargs
        assert call_kwargs["workspace"] == "default"
        assert call_kwargs["name"] == "new-fileset"

    def test_create_fileset_already_exists(self, mocker: MockerFixture, file_io_runner_mocks: FileIORunnerMocks):
        """Should silently skip when fileset already exists (ConflictError)."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk
        mock_httpx_response = mocker.MagicMock(spec=httpx.Response)
        mock_httpx_response.status_code = 409
        mocks.sdk.files.filesets.create.side_effect = ConflictError("Conflict", response=mock_httpx_response, body=None)

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        fileset = FileSetRef(workspace="default", name="existing-fileset")

        # Should not raise - just silently continues
        runner.create_fileset(fileset)

    def test_create_fileset_raises_on_api_timeout_error(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should raise FileUploadError on APITimeoutError after retries."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk
        mock_httpx_request = mocker.MagicMock(spec=httpx.Request)
        mocks.sdk.files.filesets.create.side_effect = APITimeoutError(request=mock_httpx_request)

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        fileset = FileSetRef(workspace="default", name="new-fileset")

        # create_fileset has retry decorator and sdk_error_handler converts APITimeoutError to FileUploadError
        with pytest.raises(FileUploadError, match="Failed to create fileset .* due to request timeout error"):
            runner.create_fileset(fileset)
        # Ensure we actually attempted the operation multiple times
        assert mocks.sdk.files.filesets.create.call_count == MAX_RETRIES


class TestUploadFileset:
    """Tests for FileIORunner.upload_fileset method."""

    def test_upload_fileset_calls_filesystem_put(self, file_io_runner_mocks: FileIORunnerMocks):
        """Should call filesystem_sdk.put with correct arguments for directory.

        For directories, we add a trailing slash to the source path to copy
        the directory CONTENTS (not the directory itself). This follows the
        rsync/scp convention where "dir/" copies contents while "dir" copies
        the directory.
        """
        mocks = file_io_runner_mocks

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir)
            (src_dir / "file.txt").write_text("content")

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="default", name="my-output")
            runner.upload_fileset(fileset, src_dir)

            mocks.filesystem.upload.assert_called_once()
            call_args = mocks.filesystem.upload.call_args
            # Trailing slash on source means "copy contents, not the directory itself"
            assert call_args.kwargs["local_path"] == f"{src_dir}/"
            assert call_args.kwargs["remote_path"] == ""  # Upload to fileset root
            assert call_args.kwargs["fileset"] == "my-output"
            assert call_args.kwargs["workspace"] == "default"

    def test_upload_fileset_single_file(self, file_io_runner_mocks: FileIORunnerMocks):
        """Should call filesystem_sdk.put with correct path for single file."""
        mocks = file_io_runner_mocks

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "single.txt"
            src_file.write_text("content")

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="ws", name="file-set")
            runner.upload_fileset(fileset, src_file)

            mocks.filesystem.upload.assert_called_once()
            call_args = mocks.filesystem.upload.call_args
            assert call_args.kwargs["local_path"] == str(src_file)
            assert call_args.kwargs["remote_path"] == "single.txt"  # Just the filename
            assert call_args.kwargs["fileset"] == "file-set"
            assert call_args.kwargs["workspace"] == "ws"

    def test_upload_fileset_raises_on_filesystem_error(self, file_io_runner_mocks: FileIORunnerMocks):
        """Should raise FileUploadError when filesystem put fails."""
        mocks = file_io_runner_mocks
        mocks.filesystem.upload.side_effect = Exception("Upload failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir)
            (src_dir / "file.txt").write_text("content")

            runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
            fileset = FileSetRef(workspace="default", name="test")

            with pytest.raises(FileUploadError, match="upload"):
                runner.upload_fileset(fileset, src_dir)


class TestRunUpload:
    """Tests for FileIORunner.run_upload method."""

    def test_run_upload_skips_when_no_uploads(self, file_io_runner_mocks: FileIORunnerMocks):
        """Should skip upload when no uploads are configured."""
        mocks = file_io_runner_mocks

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        runner.run_upload([])

        # Should not call filesystem put or create_fileset
        mocks.filesystem.upload.assert_not_called()
        mocks.sdk.files.filesets.create.assert_not_called()
        mocks.progress_reporter.update_progress.assert_not_called()

    def test_run_upload_creates_fileset_and_uploads(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should create fileset and upload files."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk

        # Create source directory inside job_ctx.storage_path
        src_dir = mocks.job_ctx.storage_path / "outputs"
        src_dir.mkdir()
        (src_dir / "result.txt").write_text("result")

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="outputs", dest=FileSetRef(workspace="ws", name="output-fileset")),
        ]
        runner.run_upload(uploads)

        # Should have called create on filesets
        mocks.sdk.files.filesets.create.assert_called_once()
        # Should have called put on filesystem
        mocks.filesystem.upload.assert_called_once()

    def test_run_upload_multiple_filesets(self, mocker: MockerFixture, file_io_runner_mocks: FileIORunnerMocks):
        """Should upload to multiple filesets."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk

        # Create two source directories inside job_ctx.storage_path
        src_dir1 = mocks.job_ctx.storage_path / "outputs1"
        src_dir1.mkdir()
        (src_dir1 / "file1.txt").write_text("content1")

        src_dir2 = mocks.job_ctx.storage_path / "outputs2"
        src_dir2.mkdir()
        (src_dir2 / "file2.txt").write_text("content2")

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="outputs1", dest=FileSetRef(workspace="ws", name="fileset1")),
            UploadItem(src="outputs2", dest=FileSetRef(workspace="ws", name="fileset2")),
        ]
        runner.run_upload(uploads)

        assert mocks.sdk.files.filesets.create.call_count == 2
        assert mocks.filesystem.upload.call_count == 2

    def test_run_upload_reports_progress(self, mocker: MockerFixture, file_io_runner_mocks: FileIORunnerMocks):
        """Should report progress during upload operation."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk

        # Create source directory inside job_ctx.storage_path
        src_dir = mocks.job_ctx.storage_path / "outputs"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("content")

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="outputs", dest=FileSetRef(workspace="ws", name="fileset")),
        ]
        runner.run_upload(uploads)

        # Verify progress was reported
        assert mocks.progress_reporter.update_progress.call_count >= 2  # Initial + per-fileset

        # Check initial progress call
        initial_call = mocks.progress_reporter.update_progress.call_args_list[0]
        assert initial_call[1]["status"] == PlatformJobStatus.ACTIVE
        assert initial_call[1]["status_details"]["phase"] == TaskPhase.UPLOADING
        assert initial_call[1]["status_details"]["total_filesets"] == 1

    def test_run_upload_propagates_upload_error(self, mocker: MockerFixture, file_io_runner_mocks: FileIORunnerMocks):
        """Should propagate FileUploadError when upload fails."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk
        mocks.filesystem.upload.side_effect = Exception("Upload failed")

        # Create source directory inside job_ctx.storage_path
        src_dir = mocks.job_ctx.storage_path / "outputs"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("content")

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="outputs", dest=FileSetRef(workspace="ws", name="fileset")),
        ]

        with pytest.raises(FileUploadError, match="upload"):
            runner.run_upload(uploads)

    def test_run_upload_raises_error_when_source_path_does_not_exist(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should raise FileUploadError when source path does not exist."""
        mocks = file_io_runner_mocks
        # we intentionally do NOT create the "outputs" directory

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="outputs", dest=FileSetRef(workspace="ws", name="fileset")),
        ]

        with pytest.raises(FileUploadError, match="Source path does not exist"):
            runner.run_upload(uploads)

        # Should not attempt to create fileset or upload when source doesn't exist
        mocks.sdk.files.filesets.create.assert_not_called()
        mocks.filesystem.upload.assert_not_called()

    def test_run_upload_raises_error_when_source_is_broken_symlink(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should raise FileUploadError when source path is a broken symlink."""
        mocks = file_io_runner_mocks

        # Create a broken symlink (symlink pointing to non-existent target) inside job_ctx.storage_path
        broken_symlink = mocks.job_ctx.storage_path / "outputs"
        non_existent_target = mocks.job_ctx.storage_path / "non_existent_target"
        broken_symlink.symlink_to(non_existent_target)

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="outputs", dest=FileSetRef(workspace="ws", name="fileset")),
        ]

        with pytest.raises(FileUploadError, match="Source path does not exist"):
            runner.run_upload(uploads)

        # Should not attempt to create fileset or upload
        mocks.sdk.files.filesets.create.assert_not_called()
        mocks.filesystem.upload.assert_not_called()

    def test_run_upload_raises_error_when_source_path_is_not_file_or_directory(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should raise FileUploadError when source path exists but is not a file or directory."""
        mocks = file_io_runner_mocks

        # Mock validate_safe_path to return a mock Path object that exists but is neither file nor directory
        mock_path = mocker.MagicMock()
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = False
        mock_path.is_file.return_value = False

        mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.validate_safe_path",
            return_value=mock_path,
        )

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="special_device", dest=FileSetRef(workspace="ws", name="fileset")),
        ]

        with pytest.raises(FileUploadError, match="Source path is not a file or directory"):
            runner.run_upload(uploads)

        # Should not attempt to create fileset or upload
        mocks.sdk.files.filesets.create.assert_not_called()
        mocks.filesystem.upload.assert_not_called()

    def test_run_upload_uses_default_fileset_when_dest_is_none(
        self,
        mocker: MockerFixture,
        file_io_runner_mocks: FileIORunnerMocks,
    ):
        """Should use default FileSet reference when dest is None."""
        mocks = file_io_runner_mocks
        mocks.sdk.with_options.return_value = mocks.sdk

        # Create source directory inside job_ctx.storage_path
        src_dir = mocks.job_ctx.storage_path / "outputs"
        src_dir.mkdir()
        (src_dir / "result.txt").write_text("result")

        runner = FileIORunner(sdk=mocks.sdk, progress_reporter=mocks.progress_reporter, job_ctx=mocks.job_ctx)
        uploads = [
            UploadItem(src="outputs", dest=FileSetRef(workspace=None, name="test-fileset")),
        ]
        runner.run_upload(uploads)

        # Should have called create on filesets with the default fileset (workspace/job_id from job_ctx)
        mocks.sdk.files.filesets.create.assert_called_once()
        create_call = mocks.sdk.files.filesets.create.call_args
        assert create_call[1]["workspace"] == mocks.job_ctx.workspace
        assert create_call[1]["name"] == "test-fileset"

        # Should have called put on filesystem
        mocks.filesystem.upload.assert_called_once()


class TestRun:
    """Tests for the run function."""

    def test_run_succeeds_with_no_downloads(self, mocker: MockerFixture, tmp_path: Path):
        """Should succeed when no downloads are configured."""
        # Create config file
        config = {"download": [], "upload": []}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        # Create job context
        test_job_ctx = NMPJobContext(
            workspace="test-workspace",
            job_id="test-job-123",
            attempt_id="attempt-0",
            step="model-and-dataset-download",
            task="task-456",
            jobs_url="http://jobs:8000",
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=config_path,
        )

        # Mock the SDK with required attributes for FilesetFileSystem
        mock_sdk = mocker.MagicMock()
        mock_sdk.base_url = "http://files:8000"
        mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.get_task_sdk",
            return_value=mock_sdk,
        )
        mock_create_reporter = mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.JobsServiceProgressReporter.create_progress_reporter",
        )
        mock_reporter = mocker.MagicMock()
        mock_create_reporter.return_value = mock_reporter

        exit_code = run(job_ctx=test_job_ctx)

        assert exit_code == 0

    def test_run_downloads_from_fileset(self, mocker: MockerFixture, tmp_path: Path):
        """Should download files from configured fileset."""
        # Create config file with downloads
        config = {"download": [{"src": "default/my-model", "dest": "model"}], "upload": []}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        # Create job context
        test_job_ctx = NMPJobContext(
            workspace="test-workspace",
            job_id="test-job-123",
            attempt_id="attempt-0",
            step="model-and-dataset-download",
            task="task-456",
            jobs_url="http://jobs:8000",
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=config_path,
        )

        # Mock SDK and FileIORunner to avoid actual HTTP calls
        mock_sdk = mocker.MagicMock()
        mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.get_task_sdk",
            return_value=mock_sdk,
        )
        mock_create_reporter = mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.JobsServiceProgressReporter.create_progress_reporter",
        )
        mock_reporter = mocker.MagicMock()
        mock_create_reporter.return_value = mock_reporter

        # Mock FileIORunner.run_download method
        mock_runner_class = mocker.patch("nmp.customizer.shared.tasks.file_io.runner.FileIORunner")
        mock_runner = mocker.MagicMock()
        mock_runner_class.return_value = mock_runner

        exit_code = run(job_ctx=test_job_ctx)

        assert exit_code == 0
        mock_runner.run_download.assert_called_once()

        # Verify the download was called with correct config
        call_args = mock_runner.run_download.call_args
        downloads = call_args[0][0]
        assert len(downloads) == 1
        assert downloads[0].src.workspace == "default"
        assert downloads[0].src.name == "my-model"

        # Verify progress was reported at end
        mock_reporter.update_progress.assert_called()

    def test_run_returns_error_on_download_failure(self, mocker: MockerFixture, tmp_path: Path):
        """Should return exit code 1 when download fails."""
        # Create config file with downloads
        config = {"download": [{"src": "default/my-model", "dest": "model"}], "upload": []}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        # Create job context
        test_job_ctx = NMPJobContext(
            workspace="test-workspace",
            job_id="test-job-123",
            attempt_id="attempt-0",
            step="model-and-dataset-download",
            task="task-456",
            jobs_url="http://jobs:8000",
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=config_path,
        )

        mock_sdk = mocker.MagicMock()
        mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.get_task_sdk",
            return_value=mock_sdk,
        )
        mock_create_reporter = mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.JobsServiceProgressReporter.create_progress_reporter",
        )
        mock_reporter = mocker.MagicMock()
        mock_create_reporter.return_value = mock_reporter

        # Mock FileIORunner to raise error on download
        mock_runner_class = mocker.patch("nmp.customizer.shared.tasks.file_io.runner.FileIORunner")
        mock_runner = mocker.MagicMock()
        mock_runner.run_download.side_effect = FileDownloadError("Download failed")
        mock_runner_class.return_value = mock_runner

        exit_code = run(job_ctx=test_job_ctx)

        assert exit_code == 1

        # Verify error was reported
        mock_reporter.update_progress.assert_called()
        # Find the error call
        error_calls = [
            call
            for call in mock_reporter.update_progress.call_args_list
            if call[1].get("status") == PlatformJobStatus.ERROR
        ]
        assert len(error_calls) > 0

    def test_run_returns_error_on_exception(self, mocker: MockerFixture, tmp_path: Path):
        """Should return exit code 1 when an unexpected exception occurs."""
        # Create job context with invalid config path to trigger an exception
        test_job_ctx = NMPJobContext(
            workspace="test-workspace",
            job_id="test-job-123",
            attempt_id="attempt-0",
            step="test-step",
            task="task-456",
            jobs_url="http://jobs:8000",
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=Path("/nonexistent/config.json"),
        )

        mock_sdk = mocker.MagicMock()
        mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.get_task_sdk",
            return_value=mock_sdk,
        )
        mock_create_reporter = mocker.patch(
            "nmp.customizer.shared.tasks.file_io.runner.JobsServiceProgressReporter.create_progress_reporter",
        )
        mock_reporter = mocker.MagicMock()
        mock_create_reporter.return_value = mock_reporter

        exit_code = run(job_ctx=test_job_ctx)
        assert exit_code == 1
