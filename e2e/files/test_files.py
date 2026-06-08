"""E2E tests for the files service.

These tests verify basic file upload and download operations
work correctly when running against a fully deployed NMP platform.
"""

import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from nemo_platform import NeMoPlatform
from nemo_platform.types.files import Fileset


@pytest.fixture
def fileset(sdk: NeMoPlatform, workspace: str) -> Iterator[Fileset]:
    """Create a unique fileset for each test with automatic cleanup."""
    fileset_name = f"e2e-fileset-{uuid.uuid4().hex[:8]}"
    fileset = sdk.files.filesets.create(workspace=workspace, name=fileset_name)
    yield fileset
    try:
        sdk.files.filesets.delete(fileset_name, workspace=workspace)
    except Exception:
        pass  # Ignore cleanup errors


def test_file_upload_and_download(sdk: NeMoPlatform, workspace: str, fileset: Fileset):
    """Test uploading and downloading a file.

    This test verifies the files system works end-to-end:
    1. Upload a file with test content
    2. Download the file and verify content matches
    """
    test_content = b"Hello from e2e test! This is test file content."

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create local file to upload
        local_file = Path(tmpdir, "test.txt")
        local_file.write_bytes(test_content)

        # Upload file using high-level API
        sdk.files.upload(
            fileset=fileset.name,
            workspace=workspace,
            local_path=str(local_file),
            remote_path="test.txt",
        )

        # Verify file was uploaded
        files = sdk.files.list(fileset=fileset.name, workspace=workspace)
        assert len(files.data) == 1
        assert files.data[0].path == "test.txt"
        assert files.data[0].size == len(test_content)

        # Download file and verify content
        download_path = Path(tmpdir, "downloaded.txt")
        sdk.files.download(
            fileset=fileset.name,
            workspace=workspace,
            remote_path="test.txt",
            local_path=str(download_path),
        )
        assert download_path.read_bytes() == test_content


def test_file_list_cache_status_for_default_storage(sdk: NeMoPlatform, workspace: str, fileset: Fileset):
    """Test cache status reporting for files stored in the default backend."""
    test_content = b"cache status coverage"

    sdk.files.upload_content(
        fileset=fileset.name,
        workspace=workspace,
        remote_path="cache-status.txt",
        content=test_content,
    )

    files_without_cache_check = sdk.files.list(fileset=fileset.name, workspace=workspace)
    assert len(files_without_cache_check.data) == 1
    assert files_without_cache_check.data[0].cache_status == "not_cacheable"

    files_with_cache_check = sdk.files.list(
        fileset=fileset.name,
        workspace=workspace,
        include_cache_status=True,
    )
    assert len(files_with_cache_check.data) == 1
    assert files_with_cache_check.data[0].cache_status == "not_cacheable"


def test_file_upload_nested_path(sdk: NeMoPlatform, workspace: str, fileset: Fileset):
    """Test uploading a file with a nested path.

    Verifies that files can be uploaded to nested directories
    within a fileset.
    """
    test_content = b"Nested file content"
    test_path = "folder/subfolder/nested.txt"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create local file to upload
        local_file = Path(tmpdir, "nested.txt")
        local_file.write_bytes(test_content)

        # Upload file to nested path
        sdk.files.upload(
            fileset=fileset.name,
            workspace=workspace,
            local_path=str(local_file),
            remote_path=test_path,
        )

        # List files and verify the nested file appears
        files = sdk.files.list(fileset=fileset.name, workspace=workspace)
        file_paths = {f.path for f in files.data}
        assert test_path in file_paths

        # Download and verify
        download_path = Path(tmpdir, "downloaded.txt")
        sdk.files.download(
            fileset=fileset.name,
            workspace=workspace,
            remote_path=test_path,
            local_path=str(download_path),
        )
        assert download_path.read_bytes() == test_content


def test_file_delete(sdk: NeMoPlatform, workspace: str, fileset: Fileset):
    """Test deleting a file from a fileset.

    Verifies that files can be deleted and are no longer
    accessible after deletion.
    """
    test_content = b"File to be deleted"
    test_path = "delete-me.txt"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create local file to upload
        local_file = Path(tmpdir, "delete-me.txt")
        local_file.write_bytes(test_content)

        # Upload file
        sdk.files.upload(
            fileset=fileset.name,
            workspace=workspace,
            local_path=str(local_file),
            remote_path=test_path,
        )

        # Verify file exists by listing
        files = sdk.files.list(fileset=fileset.name, workspace=workspace)
        assert any(f.path == test_path for f in files.data)

        # Delete file
        sdk.files.delete(
            fileset=fileset.name,
            workspace=workspace,
            remote_path=test_path,
        )

        # Verify file is gone
        files = sdk.files.list(fileset=fileset.name, workspace=workspace)
        assert not any(f.path == test_path for f in files.data)


def test_directory_upload_and_download(sdk: NeMoPlatform, workspace: str, fileset: Fileset):
    """Test uploading and downloading a directory.

    Verifies that entire directories can be uploaded and downloaded
    with their structure preserved.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory structure to upload
        upload_dir = Path(tmpdir, "upload")
        upload_dir.mkdir()
        (upload_dir / "file1.txt").write_text("content1")
        (upload_dir / "file2.txt").write_text("content2")
        subdir = upload_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        # Upload entire directory
        sdk.files.upload(
            fileset=fileset.name,
            workspace=workspace,
            local_path=f"{upload_dir}/",
            remote_path="",
        )

        # Verify all files were uploaded
        files = sdk.files.list(fileset=fileset.name, workspace=workspace)
        paths = {f.path for f in files.data}
        assert paths == {"file1.txt", "file2.txt", "subdir/file3.txt"}

        # Download entire fileset
        download_dir = Path(tmpdir, "download")
        download_dir.mkdir()
        sdk.files.download(
            fileset=fileset.name,
            workspace=workspace,
            local_path=f"{download_dir}/",
        )

        # Verify downloaded content matches
        assert (download_dir / "file1.txt").read_text() == "content1"
        assert (download_dir / "file2.txt").read_text() == "content2"
        assert (download_dir / "subdir" / "file3.txt").read_text() == "content3"
