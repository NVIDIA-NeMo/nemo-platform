# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for integration tests in the tasks module.

Provides common fixtures for:
- Test workspace constants
- HTTP test clients with various service combinations
- SDK clients (sync and async)
- Temporary directories for test artifacts
- Job lifecycle management (JobContext)
- Utility functions for working with filesets and results
"""

import tempfile
from pathlib import Path
from typing import Generator
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform, NotFoundError
from nmp.core.files.service import FilesService
from nmp.core.jobs.service import JobsService
from nmp.testing.client import create_test_client

# =============================================================================
# Constants
# =============================================================================

TEST_WORKSPACE = "test-workspace"


# =============================================================================
# Job Context - Handles Creation & Cleanup Tracking
# =============================================================================


class JobContext:
    """Tracks created jobs and provides cleanup utilities.

    Ensures test jobs are properly cleaned up even if tests fail mid-way.
    """

    def __init__(self, sdk: NeMoPlatform, workspace: str = TEST_WORKSPACE):
        self._sdk = sdk
        self._workspace = workspace
        self._created_jobs: set[str] = set()
        self._cleaned_jobs: set[str] = set()

    def create(self, job_name: str):
        """Create a test job and register it for cleanup tracking."""
        job = self._sdk.jobs.create(
            workspace=self._workspace,
            name=job_name,
            source="evaluator",
            spec={},
            platform_spec={
                "steps": [
                    {
                        "name": "evaluate",
                        "executor": {
                            "provider": "cpu",
                            "profile": "default",
                            "container": {
                                "image": "test:latest",
                                "entrypoint": ["entrypoint"],
                                "command": ["command"],
                            },
                        },
                    }
                ]
            },
        )
        self._created_jobs.add(job_name)
        return job

    def cleanup(self, job_name: str) -> None:
        """Delete job and assert cascade deletion works correctly."""
        fileset_name = f"job-fileset-{job_name}"

        # Delete the job - should cascade to delete the fileset
        self._sdk.jobs.delete(workspace=self._workspace, name=job_name)

        # Verify job is gone
        with pytest.raises(NotFoundError):
            self._sdk.jobs.retrieve(workspace=self._workspace, name=job_name)

        # Verify fileset was cascade deleted
        with pytest.raises(NotFoundError):
            self._sdk.files.filesets.retrieve(workspace=self._workspace, name=fileset_name)

        self._cleaned_jobs.add(job_name)

    def mark_cleaned(self, job_name: str) -> None:
        """Mark a job as manually cleaned (for tests doing their own cleanup assertions)."""
        self._cleaned_jobs.add(job_name)

    def safety_cleanup(self) -> None:
        """Clean up any jobs that weren't explicitly cleaned (test failed mid-way)."""
        for job_name in self._created_jobs - self._cleaned_jobs:
            fileset_name = f"job-fileset-{job_name}"
            try:
                self._sdk.jobs.delete(workspace=self._workspace, name=job_name)
            except Exception:
                pass
            try:
                self._sdk.files.filesets.delete(workspace=self._workspace, name=fileset_name)
            except Exception:
                pass


# =============================================================================
# Fileset Helper Functions
# =============================================================================


def get_fileset_path_from_artifact_url(artifact_url: str, fileset_name: str) -> str:
    """Extract the file path within a fileset from an artifact URL.

    Handles various URL formats robustly using urlparse.
    Example: "fileset://workspace/fileset-name/path/to/file.json" -> "path/to/file.json"
    """
    parsed = urlparse(artifact_url)

    # Handle fileset:// URLs
    if parsed.scheme == "fileset":
        # Path is like /fileset-name/path/to/file
        path_parts = parsed.path.lstrip("/").split("/", 1)
        if len(path_parts) > 1:
            return path_parts[1]
        return ""

    # Handle http(s):// URLs that contain the fileset path
    # e.g., http://host/v2/workspaces/ws/filesets/name/-/files/path/to/file
    if "filesets" in parsed.path and "/-/" in parsed.path:
        # Split on /-/ which separates fileset name from file path
        parts = parsed.path.split("/-/")
        if len(parts) > 1:
            # Remove leading "files/" if present
            file_path = parts[1]
            if file_path.startswith("files/"):
                file_path = file_path[6:]
            return file_path

    # Fallback: try to find fileset name in path and extract remainder
    if fileset_name in artifact_url:
        parts = artifact_url.split(f"{fileset_name}/", 1)
        if len(parts) > 1:
            return parts[1]

    raise ValueError(f"Could not extract file path from artifact URL: {artifact_url}")


def download_result_content(
    sdk: NeMoPlatform,
    job_name: str,
    result_name: str,
    workspace: str = TEST_WORKSPACE,
) -> bytes:
    """Download the content of a job result from its fileset."""
    fileset_name = f"job-fileset-{job_name}"

    result = sdk.jobs.results.retrieve(
        name=result_name,
        job=job_name,
        workspace=workspace,
    )

    file_path = get_fileset_path_from_artifact_url(result.artifact_url, fileset_name)

    content = sdk.files.download_content(
        remote_path=file_path,
        fileset=fileset_name,
        workspace=workspace,
    )
    return content


def file_exists_in_fileset(
    sdk: NeMoPlatform,
    job_name: str,
    path: str,
    workspace: str = TEST_WORKSPACE,
) -> bool:
    """Check if a file exists in a job's fileset by attempting to download it."""
    fileset_name = f"job-fileset-{job_name}"
    try:
        sdk.files.download_content(
            remote_path=path,
            fileset=fileset_name,
            workspace=workspace,
        )
        return True
    except Exception:
        return False


def download_fileset_file(
    sdk: NeMoPlatform,
    job_name: str,
    path: str,
    workspace: str = TEST_WORKSPACE,
) -> bytes:
    """Download a file from a job's fileset."""
    fileset_name = f"job-fileset-{job_name}"
    return sdk.files.download_content(
        remote_path=path,
        fileset=fileset_name,
        workspace=workspace,
    )


# =============================================================================
# HTTP Client Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def files_http_client() -> Generator[TestClient, None, None]:
    """Create test client with Files service only."""
    with create_test_client(
        FilesService,
        client_type=TestClient,
        workspaces=[TEST_WORKSPACE],
    ) as client:
        yield client


@pytest.fixture(scope="module")
def jobs_files_http_client() -> Generator[TestClient, None, None]:
    """Create test client with Jobs and Files services."""
    with create_test_client(
        JobsService,
        FilesService,
        client_type=TestClient,
        workspaces=[TEST_WORKSPACE],
    ) as client:
        yield client


# =============================================================================
# SDK Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def sdk(jobs_files_http_client: TestClient) -> NeMoPlatform:
    """Sync SDK client backed by the Jobs+Files test client."""
    return NeMoPlatform(base_url="http://testserver", http_client=jobs_files_http_client)


@pytest.fixture(scope="module")
def async_sdk(files_http_client: TestClient) -> AsyncNeMoPlatform:
    """Async SDK client backed by the Files test client."""
    transport = ASGITransport(app=files_http_client.app)
    async_client = AsyncClient(transport=transport, base_url="http://testserver")
    return AsyncNeMoPlatform(base_url="http://testserver", http_client=async_client)


@pytest.fixture(scope="module")
def async_sdk_with_jobs(jobs_files_http_client: TestClient) -> AsyncNeMoPlatform:
    """Async SDK client backed by the Jobs+Files test client."""
    transport = ASGITransport(app=jobs_files_http_client.app)
    async_client = AsyncClient(transport=transport, base_url="http://testserver")
    return AsyncNeMoPlatform(base_url="http://testserver", http_client=async_client)


# =============================================================================
# Job Context Fixture
# =============================================================================


@pytest.fixture
def job_context(sdk: NeMoPlatform) -> Generator[JobContext, None, None]:
    """Provides job creation and cleanup with automatic safety cleanup on failure."""
    ctx = JobContext(sdk)
    yield ctx
    ctx.safety_cleanup()


# =============================================================================
# Temporary Directory Fixture
# =============================================================================


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
