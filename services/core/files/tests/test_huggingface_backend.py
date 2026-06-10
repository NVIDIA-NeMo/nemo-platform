# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Huggingface storage backend."""

from unittest.mock import Mock, patch

import aiohttp
import httpx
import pytest
from nmp.common.api.common import SecretRef
from nmp.core.files.app.backends.base import ByteRange
from nmp.core.files.app.backends.factory import storage_impl_factory
from nmp.core.files.app.backends.huggingface import (
    HuggingfaceAccessError,
    HuggingfaceBackendError,
    HuggingfaceConfigError,
    HuggingfaceStorageConfig,
    HuggingfaceStorageImpl,
    HuggingfaceUnavailableError,
    raise_for_hf_status,
)


def _hf_http_error_without_response(message: str):
    """Create a Hugging Face HTTP error for the no-response branch."""
    from huggingface_hub.utils import HfHubHTTPError

    error = HfHubHTTPError.__new__(HfHubHTTPError)
    Exception.__init__(error, message)
    error.response = None
    return error


@pytest.fixture
def mock_httpx_response():
    """Create a mock httpx.Response for Huggingface exceptions."""
    mock_response = Mock(spec=httpx.Response)
    mock_response.headers = {}
    return mock_response


@pytest.fixture
def hf_config() -> HuggingfaceStorageConfig:
    """Create a test Huggingface storage config."""
    return HuggingfaceStorageConfig(
        repo_id="test-org/test-repo",
        repo_type="model",
        revision="main",
    )


@pytest.fixture
def hf_config_with_token() -> HuggingfaceStorageConfig:
    """Create a test Huggingface storage config with token."""
    return HuggingfaceStorageConfig(
        repo_id="test-org/test-repo",
        repo_type="dataset",
        revision="v1.0",
        token_secret=SecretRef(root="test-secret"),
    )


@pytest.fixture
def hf_config_resolved() -> HuggingfaceStorageConfig:
    """Create a config as it would appear AFTER resolve_config() is called.

    After resolution, the revision is always a commit SHA (immutable),
    and original_revision stores what the user originally requested.
    """
    return HuggingfaceStorageConfig(
        repo_id="test-org/test-repo",
        repo_type="model",
        revision="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",  # 40-char commit SHA
        original_revision="main",  # What user originally requested
    )


@pytest.fixture
def hf_secrets() -> dict[str, str]:
    """Mock resolved secrets for HuggingFace."""
    return {"token": "test-token"}


@pytest.fixture
def hf_secrets_empty() -> dict[str, str]:
    """Empty secrets dict for tests without token."""
    return {}


@pytest.fixture
def mock_hf_api():
    """Mock Huggingface Hub API."""
    with patch("nmp.core.files.app.backends.huggingface.HfApi") as mock_api_cls:
        mock_api = Mock()
        mock_api_cls.return_value = mock_api
        yield mock_api


def test_get_download_url(hf_config, hf_secrets_empty):
    """Test download URL generation."""
    with patch("nmp.core.files.app.backends.huggingface.hf_hub_url") as mock_url:
        mock_url.return_value = "https://huggingface.co/test-org/test-repo/resolve/main/file.txt"

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
        url = impl._get_download_url("file.txt")

        mock_url.assert_called_once_with(
            repo_id="test-org/test-repo",
            filename="file.txt",
            repo_type="model",
            revision="main",
            endpoint="https://huggingface.co",
        )
        assert url == "https://huggingface.co/test-org/test-repo/resolve/main/file.txt"


async def test_list_files_no_filter(hf_config, mock_hf_api, hf_secrets_empty):
    """Test listing all files without path filter."""
    # Create mock RepoFile objects (files have size)
    mock_file1 = Mock()
    mock_file1.path = "file1.txt"
    mock_file1.size = 100

    mock_file2 = Mock()
    mock_file2.path = "dir/file2.txt"
    mock_file2.size = 200

    # Create mock RepoFolder object (folders don't have size)
    mock_folder = Mock(spec=["path"])  # No size attribute
    mock_folder.path = "dir"

    mock_hf_api.list_repo_tree.return_value = [mock_folder, mock_file1, mock_file2]

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
    files = await impl.list_files()

    # Should only return files, not folders
    assert len(files) == 2
    assert files[0].path == "file1.txt"
    assert files[0].size == 100
    assert files[1].path == "dir/file2.txt"
    assert files[1].size == 200

    mock_hf_api.list_repo_tree.assert_called_once_with(
        repo_id="test-org/test-repo",
        repo_type="model",
        revision="main",
        path_in_repo=None,
        recursive=True,
    )


async def test_list_files_with_path_filter(hf_config, mock_hf_api, hf_secrets_empty):
    """Test listing files with path filter."""
    mock_file1 = Mock()
    mock_file1.path = "subdir/file1.txt"
    mock_file1.size = 100

    mock_file2 = Mock()
    mock_file2.path = "subdir/file2.txt"
    mock_file2.size = 200

    mock_hf_api.list_repo_tree.return_value = [mock_file1, mock_file2]

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
    files = await impl.list_files("subdir")

    assert len(files) == 2

    # Verify path_in_repo was passed to the API
    mock_hf_api.list_repo_tree.assert_called_once_with(
        repo_id="test-org/test-repo",
        repo_type="model",
        revision="main",
        path_in_repo="subdir",
        recursive=True,
    )


async def test_list_files_repo_not_found(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test list_files when repository not found."""
    from huggingface_hub.utils import RepositoryNotFoundError

    mock_httpx_response.status_code = 404
    mock_httpx_response.headers = {"X-Error-Code": "RepoNotFound"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.list_repo_tree.side_effect = RepositoryNotFoundError("Repo not found", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceConfigError) as exc_info:
        await impl.list_files()

    assert "Repository not found" in str(exc_info.value)


async def test_list_files_revision_not_found(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test list_files when revision not found."""
    from huggingface_hub.utils import RevisionNotFoundError

    mock_httpx_response.status_code = 404
    mock_httpx_response.headers = {"X-Error-Code": "RevisionNotFound"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.list_repo_tree.side_effect = RevisionNotFoundError("Revision not found", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceConfigError) as exc_info:
        await impl.list_files()

    assert "Revision not found" in str(exc_info.value)


async def test_list_files_file_path_fallback_to_get_file(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test list_files falls back to get_file when path is a file, not a directory.

    HuggingFace's list_repo_tree expects a directory path. When given a file path
    like 'subdir/file.jsonl', it returns 404. The backend should fall back to
    checking if it's a single file using get_file.
    """
    from huggingface_hub.utils import EntryNotFoundError

    # list_repo_tree fails because path is a file, not a directory
    mock_hf_api.list_repo_tree.side_effect = EntryNotFoundError("Entry not found")

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    # Mock get_file to succeed (the path is a valid file)
    with patch.object(impl, "get_file") as mock_get_file:
        from nmp.core.files.app.backends.base import FileInfo

        mock_get_file.return_value = FileInfo(path="subdir/file.jsonl", size=1234)

        files = await impl.list_files("subdir/file.jsonl")

        assert len(files) == 1
        assert files[0].path == "subdir/file.jsonl"
        assert files[0].size == 1234
        mock_get_file.assert_called_once_with("subdir/file.jsonl")


async def test_list_files_path_not_found_returns_empty(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test list_files returns empty list when path doesn't exist as file or directory."""
    from huggingface_hub.utils import EntryNotFoundError
    from nmp.core.files.exceptions import NotFoundError

    # list_repo_tree fails (not a directory)
    mock_hf_api.list_repo_tree.side_effect = EntryNotFoundError("Entry not found")

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    # Mock get_file to also fail (not a file either)
    with patch.object(impl, "get_file") as mock_get_file:
        mock_get_file.side_effect = NotFoundError("File not found")

        files = await impl.list_files("nonexistent/path.jsonl")

        assert files == []
        mock_get_file.assert_called_once_with("nonexistent/path.jsonl")


async def test_list_files_entry_not_found_no_path_returns_empty(
    hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty
):
    """Test list_files returns empty when EntryNotFoundError with no path."""
    from huggingface_hub.utils import EntryNotFoundError

    mock_hf_api.list_repo_tree.side_effect = EntryNotFoundError("Entry not found")

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    # When path is None, we don't try get_file fallback
    files = await impl.list_files(None)

    assert files == []


async def test_download_success(hf_config, hf_secrets_empty):
    """Test successful file download."""
    with (
        patch("nmp.core.files.app.backends.huggingface.hf_hub_url") as mock_url,
        patch("nmp.core.files.app.backends.huggingface.download_url_streaming") as mock_stream,
    ):
        mock_url.return_value = "https://huggingface.co/test-org/test-repo/resolve/main/test.txt"

        async def mock_chunks():
            yield b"chunk1"
            yield b"chunk2"

        mock_stream.return_value = mock_chunks()

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
        download_iter = await impl.download("test.txt", None)

        chunks = []
        async for chunk in download_iter:
            chunks.append(chunk)

        assert chunks == [b"chunk1", b"chunk2"]
        mock_stream.assert_called_once()


async def test_download_with_token(hf_config_with_token, hf_secrets):
    """Test download includes authorization header when token provided."""
    with (
        patch("nmp.core.files.app.backends.huggingface.hf_hub_url") as mock_url,
        patch("nmp.core.files.app.backends.huggingface.download_url_streaming") as mock_stream,
    ):
        mock_url.return_value = "https://huggingface.co/test-org/test-repo/resolve/v1.0/test.txt"

        async def mock_chunks():
            yield b"data"

        mock_stream.return_value = mock_chunks()

        impl = HuggingfaceStorageImpl(hf_config_with_token, hf_secrets)
        download_iter = await impl.download("test.txt", None)

        # Consume iterator
        async for _ in download_iter:
            pass

        # Verify headers include authorization
        call_kwargs = mock_stream.call_args.kwargs
        assert call_kwargs["headers"] == {"Authorization": "Bearer test-token"}


async def test_download_with_byte_range(hf_config, hf_secrets_empty):
    """Test file download with byte range."""
    byte_range = ByteRange(start=0, end=100)

    with (
        patch("nmp.core.files.app.backends.huggingface.hf_hub_url") as mock_url,
        patch("nmp.core.files.app.backends.huggingface.download_url_streaming") as mock_stream,
    ):
        mock_url.return_value = "https://huggingface.co/test-org/test-repo/resolve/main/test.txt"

        async def mock_chunks():
            yield b"partial"

        mock_stream.return_value = mock_chunks()

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
        download_iter = await impl.download("test.txt", byte_range)

        chunks = []
        async for chunk in download_iter:
            chunks.append(chunk)

        # Verify byte range was passed
        call_kwargs = mock_stream.call_args.kwargs
        assert call_kwargs["byte_range"] == byte_range
        assert chunks == [b"partial"]


async def test_download_file_not_found(hf_config, hf_secrets_empty):
    """Test download when file is not found (404)."""
    with (
        patch("nmp.core.files.app.backends.huggingface.hf_hub_url") as mock_url,
        patch("nmp.core.files.app.backends.huggingface.download_url_streaming") as mock_stream,
    ):
        mock_url.return_value = "https://huggingface.co/test-org/test-repo/resolve/main/missing.txt"

        async def mock_chunks():
            raise aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=404,
                message="Not Found",
            )
            yield  # pragma: no cover

        mock_stream.return_value = mock_chunks()

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
        download_iter = await impl.download("missing.txt", None)

        with pytest.raises(HuggingfaceConfigError) as exc_info:
            async for _ in download_iter:
                pass

        assert "Not found" in str(exc_info.value)


async def test_download_unauthorized(hf_config, hf_secrets_empty):
    """Test download when unauthorized (401)."""
    with (
        patch("nmp.core.files.app.backends.huggingface.hf_hub_url") as mock_url,
        patch("nmp.core.files.app.backends.huggingface.download_url_streaming") as mock_stream,
    ):
        mock_url.return_value = "https://huggingface.co/test-org/test-repo/resolve/main/private.txt"

        async def mock_chunks():
            raise aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=401,
                message="Unauthorized",
            )
            yield  # pragma: no cover

        mock_stream.return_value = mock_chunks()

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
        download_iter = await impl.download("private.txt", None)

        with pytest.raises(HuggingfaceAccessError) as exc_info:
            async for _ in download_iter:
                pass

        assert "Unauthorized" in str(exc_info.value)


async def test_download_network_error(hf_config, hf_secrets_empty):
    """Test download with network error."""
    with (
        patch("nmp.core.files.app.backends.huggingface.hf_hub_url") as mock_url,
        patch("nmp.core.files.app.backends.huggingface.download_url_streaming") as mock_stream,
    ):
        mock_url.return_value = "https://huggingface.co/test-org/test-repo/resolve/main/test.txt"

        async def mock_chunks():
            raise aiohttp.ClientError("Connection failed")
            yield  # pragma: no cover

        mock_stream.return_value = mock_chunks()

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
        download_iter = await impl.download("test.txt", None)

        with pytest.raises(HuggingfaceBackendError) as exc_info:
            async for _ in download_iter:
                pass

        assert "Network error" in str(exc_info.value)


async def test_validate_storage_success(hf_config, mock_hf_api, hf_secrets_empty):
    """Test successful storage validation."""
    # Mock repo_info with siblings
    mock_sibling = Mock()
    mock_sibling.rfilename = "config.json"
    mock_repo_info = Mock()
    mock_repo_info.siblings = [mock_sibling]
    mock_hf_api.repo_info.return_value = mock_repo_info

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    # Mock file metadata check
    with patch("nmp.core.files.app.backends.huggingface.get_hf_file_metadata") as mock_metadata:
        mock_metadata.return_value = Mock(size=1234)
        await impl.validate_storage()

    # Should complete without exception


async def test_validate_storage_repo_not_found(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test storage validation when repository not found."""
    from huggingface_hub.utils import RepositoryNotFoundError

    mock_httpx_response.status_code = 404
    mock_httpx_response.headers = {"X-Error-Code": "RepoNotFound"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.repo_info.side_effect = RepositoryNotFoundError("Repo not found", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceConfigError) as exc_info:
        await impl.validate_storage()

    assert "Repository not found" in str(exc_info.value)


async def test_validate_storage_revision_not_found(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test storage validation when revision not found."""
    from huggingface_hub.utils import RevisionNotFoundError

    mock_httpx_response.status_code = 404
    mock_httpx_response.headers = {"X-Error-Code": "RevisionNotFound"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.repo_info.side_effect = RevisionNotFoundError("Revision not found", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceConfigError) as exc_info:
        await impl.validate_storage()

    assert "Revision not found" in str(exc_info.value)


async def test_validate_storage_generic_error(hf_config, mock_hf_api, hf_secrets_empty):
    """Test storage validation with generic error."""
    mock_hf_api.repo_info.side_effect = Exception("Connection failed")

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceBackendError) as exc_info:
        await impl.validate_storage()

    assert "Failed to access" in str(exc_info.value)


def test_factory_creates_huggingface_impl(hf_config: HuggingfaceStorageConfig, hf_secrets_empty):
    """Test that factory correctly creates Huggingface storage impl."""

    impl = storage_impl_factory(hf_config, hf_secrets_empty)

    assert isinstance(impl, HuggingfaceStorageImpl)
    assert impl.config == hf_config


async def test_get_cache_path_key_with_path(hf_config, hf_secrets_empty):
    """Test get_cache_path_key returns full path when path is provided."""
    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    cache_key = await impl.get_cache_path_key("models/model.bin")

    assert cache_key == "cache/hf/test-org/test-repo/main/models/model.bin"


async def test_get_cache_path_key_without_path(hf_config, hf_secrets_empty):
    """Test get_cache_path_key returns cache root prefix when path is None."""
    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    cache_key = await impl.get_cache_path_key()

    assert cache_key == "cache/hf/test-org/test-repo/main"


async def test_get_cache_path_key_with_different_revision(hf_config_with_token, hf_secrets):
    """Test get_cache_path_key includes revision in path."""
    impl = HuggingfaceStorageImpl(hf_config_with_token, hf_secrets)

    cache_key = await impl.get_cache_path_key("file.txt")

    assert cache_key == "cache/hf/test-org/test-repo/v1.0/file.txt"

    # Without path
    cache_prefix = await impl.get_cache_path_key()

    assert cache_prefix == "cache/hf/test-org/test-repo/v1.0"


def test_hf_config_does_not_own_storage_data(hf_config):
    """HuggingFace is read-only external storage; the platform does not own the source data."""
    assert hf_config.owns_storage_data is False


async def test_list_files_gated_repo_error(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test list_files when gated repo access is denied."""
    from huggingface_hub.utils import GatedRepoError

    mock_httpx_response.status_code = 403
    mock_httpx_response.headers = {"X-Error-Code": "GatedRepo"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.list_repo_tree.side_effect = GatedRepoError("Gated repo", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceAccessError) as exc_info:
        await impl.list_files()

    assert "Access denied to gated repository" in str(exc_info.value)


async def test_get_file_gated_repo_error(hf_config, mock_httpx_response, hf_secrets_empty):
    """Test get_file when gated repo access is denied."""
    from huggingface_hub.utils import GatedRepoError

    mock_httpx_response.status_code = 403
    mock_httpx_response.headers = {"X-Error-Code": "GatedRepo"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo/test.txt"

    with patch("nmp.core.files.app.backends.huggingface.get_hf_file_metadata") as mock_metadata:
        mock_metadata.side_effect = GatedRepoError("Gated repo", response=mock_httpx_response)

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

        with pytest.raises(HuggingfaceAccessError) as exc_info:
            await impl.get_file("test.txt")

    assert "Access denied to gated repository" in str(exc_info.value)


async def test_get_file_rate_limit_error(hf_config, hf_secrets_empty):
    """Test get_file when rate limited by HuggingFace."""
    from huggingface_hub.utils import HfHubHTTPError

    # Create a mock response with 429 status code
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.headers = {}
    mock_response.url = "https://huggingface.co/test-org/test-repo/test.txt"

    mock_error = HfHubHTTPError("Rate limited", response=mock_response)

    with patch("nmp.core.files.app.backends.huggingface.get_hf_file_metadata") as mock_metadata:
        mock_metadata.side_effect = mock_error

        impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

        with pytest.raises(HuggingfaceUnavailableError) as exc_info:
            await impl.get_file("test.txt")

    assert "Rate limited" in str(exc_info.value)


async def test_validate_storage_gated_repo_error(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test storage validation when gated repo access is denied."""
    from huggingface_hub.utils import GatedRepoError

    mock_httpx_response.status_code = 403
    mock_httpx_response.headers = {"X-Error-Code": "GatedRepo"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.repo_info.side_effect = GatedRepoError("Gated repo", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceAccessError) as exc_info:
        await impl.validate_storage()

    assert "Access denied to gated repository" in str(exc_info.value)


async def test_validate_storage_checks_file_metadata_for_gated_repos(hf_config, mock_hf_api, hf_secrets_empty):
    """Test that validate_storage checks file metadata to catch gated repos.

    Some gated repos allow repo_info but block file downloads.
    validate_storage should check both.
    """
    from huggingface_hub.utils import GatedRepoError

    # repo_info succeeds
    mock_sibling = Mock()
    mock_sibling.rfilename = "config.json"
    mock_repo_info = Mock()
    mock_repo_info.siblings = [mock_sibling]
    mock_hf_api.repo_info.return_value = mock_repo_info

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    # But file metadata check fails with gated error
    with patch("nmp.core.files.app.backends.huggingface.get_hf_file_metadata") as mock_metadata:
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {"X-Error-Code": "GatedRepo"}
        mock_response.url = "https://huggingface.co/test-org/test-repo/resolve/main/config.json"
        mock_metadata.side_effect = GatedRepoError("Gated repo", response=mock_response)

        with pytest.raises(HuggingfaceAccessError) as exc_info:
            await impl.validate_storage()

        assert "Access denied to gated repository" in str(exc_info.value)


@pytest.mark.parametrize(
    ("status_code", "headers", "expected_exc", "expected_msg"),
    [
        # X-Error-Code header mappings
        (403, {"X-Error-Code": "GatedRepo"}, HuggingfaceAccessError, "gated"),
        (404, {"X-Error-Code": "RepoNotFound"}, HuggingfaceConfigError, "Repository"),
        (404, {"X-Error-Code": "RevisionNotFound"}, HuggingfaceConfigError, "Revision"),
        (404, {"X-Error-Code": "EntryNotFound"}, HuggingfaceConfigError, "Entry"),
        # Status code fallbacks
        (401, None, HuggingfaceAccessError, "Unauthorized"),
        (403, None, HuggingfaceAccessError, "Forbidden"),
        (404, None, HuggingfaceConfigError, "Not found"),
        (429, None, HuggingfaceUnavailableError, "Rate limited"),
        (500, None, HuggingfaceUnavailableError, "Service error"),
        (502, None, HuggingfaceUnavailableError, "Service error"),
        (418, None, HuggingfaceBackendError, "HTTP 418"),
        # Error code takes precedence over status
        (404, {"X-Error-Code": "GatedRepo"}, HuggingfaceAccessError, "gated"),
    ],
)
def test_raise_for_hf_status(status_code, headers, expected_exc, expected_msg):
    """Test raise_for_hf_status maps status codes and headers to exceptions."""
    with pytest.raises(expected_exc) as exc_info:
        raise_for_hf_status(status_code, headers)
    assert expected_msg in str(exc_info.value)


def test_raise_for_hf_status_success_codes():
    """Test that success status codes don't raise."""
    for code in [200, 201, 204, 304]:
        raise_for_hf_status(code)  # Should not raise


async def test_resolve_config_success(hf_config, mock_hf_api, hf_secrets_empty):
    """Test resolve_config resolves mutable revision to commit SHA."""
    # Mock repo_info to return an object with .sha
    mock_repo_info = Mock()
    mock_repo_info.sha = "abc123def456789"
    mock_hf_api.repo_info.return_value = mock_repo_info

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)
    resolved_config = await impl.resolve_config()

    # Original revision should be stored
    assert resolved_config.original_revision == "main"
    # Revision should be updated to commit SHA
    assert resolved_config.revision == "abc123def456789"
    # Other fields should be unchanged
    assert resolved_config.repo_id == hf_config.repo_id
    assert resolved_config.repo_type == hf_config.repo_type

    mock_hf_api.repo_info.assert_called_once_with(
        repo_id="test-org/test-repo",
        repo_type="model",
        revision="main",
    )


async def test_resolve_config_already_sha(mock_hf_api, hf_secrets_empty):
    """Test resolve_config works when revision is already a commit SHA."""
    config = HuggingfaceStorageConfig(
        repo_id="test-org/test-repo",
        repo_type="model",
        revision="abc123def456789",  # Already a SHA
    )

    mock_repo_info = Mock()
    mock_repo_info.sha = "abc123def456789"  # Same SHA returned
    mock_hf_api.repo_info.return_value = mock_repo_info

    impl = HuggingfaceStorageImpl(config, hf_secrets_empty)
    resolved_config = await impl.resolve_config()

    assert resolved_config.original_revision == "abc123def456789"
    assert resolved_config.revision == "abc123def456789"


async def test_resolve_config_tag_to_sha(mock_hf_api, hf_secrets_empty):
    """Test resolve_config resolves tag to commit SHA."""
    config = HuggingfaceStorageConfig(
        repo_id="test-org/test-repo",
        repo_type="dataset",
        revision="v1.0",  # A tag
    )

    mock_repo_info = Mock()
    mock_repo_info.sha = "def789abc123456"
    mock_hf_api.repo_info.return_value = mock_repo_info

    impl = HuggingfaceStorageImpl(config, hf_secrets_empty)
    resolved_config = await impl.resolve_config()

    assert resolved_config.original_revision == "v1.0"
    assert resolved_config.revision == "def789abc123456"


async def test_resolve_config_repo_not_found(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test resolve_config raises HuggingfaceConfigError when repo not found."""
    from huggingface_hub.utils import HfHubHTTPError

    mock_httpx_response.status_code = 404
    mock_httpx_response.headers = {"X-Error-Code": "RepoNotFound"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.repo_info.side_effect = HfHubHTTPError("Repo not found", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceConfigError) as exc_info:
        await impl.resolve_config()

    assert "Repository not found" in str(exc_info.value)


async def test_resolve_config_revision_not_found(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test resolve_config raises HuggingfaceConfigError when revision not found."""
    from huggingface_hub.utils import HfHubHTTPError

    mock_httpx_response.status_code = 404
    mock_httpx_response.headers = {"X-Error-Code": "RevisionNotFound"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.repo_info.side_effect = HfHubHTTPError("Revision not found", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceConfigError) as exc_info:
        await impl.resolve_config()

    assert "Revision not found" in str(exc_info.value)


async def test_resolve_config_gated_repo(hf_config, mock_hf_api, mock_httpx_response, hf_secrets_empty):
    """Test resolve_config raises HuggingfaceAccessError for gated repos."""
    from huggingface_hub.utils import HfHubHTTPError

    mock_httpx_response.status_code = 403
    mock_httpx_response.headers = {"X-Error-Code": "GatedRepo"}
    mock_httpx_response.url = "https://huggingface.co/test-org/test-repo"
    mock_hf_api.repo_info.side_effect = HfHubHTTPError("Gated repo", response=mock_httpx_response)

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceAccessError) as exc_info:
        await impl.resolve_config()

    assert "gated" in str(exc_info.value).lower()


async def test_resolve_config_generic_error(hf_config, mock_hf_api, hf_secrets_empty):
    """Test resolve_config raises HuggingfaceBackendError for unexpected errors."""
    # HfHubHTTPError without response
    mock_hf_api.repo_info.side_effect = _hf_http_error_without_response("Connection failed")

    impl = HuggingfaceStorageImpl(hf_config, hf_secrets_empty)

    with pytest.raises(HuggingfaceBackendError) as exc_info:
        await impl.resolve_config()

    assert "HuggingFace API error" in str(exc_info.value)


async def test_get_cache_path_key_uses_revision(hf_config_resolved, hf_secrets_empty):
    """Test get_cache_path_key uses revision (commit SHA) for cache path.

    After resolve_config(), revision is always a commit SHA, ensuring
    the cache path is immutable and safe from cache staleness.
    """
    impl = HuggingfaceStorageImpl(hf_config_resolved, hf_secrets_empty)

    cache_key = await impl.get_cache_path_key("models/model.bin")

    assert cache_key == "cache/hf/test-org/test-repo/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2/models/model.bin"
