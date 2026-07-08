# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test fixtures for the CLI.

Provides HTTP client fixtures for testing a subset of API endpoints.
Uses in-memory repositories for fast, isolated testing.

This way we can run the CLI commands against a real ASGI app without needing
a live server or external database.
"""

import os
import uuid
from pathlib import Path
from typing import Generator

import pytest
from click.testing import Result
from nemo_platform import NeMoPlatform
from nemo_platform_ext.cli.core.context import CLIContext
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient
from nmp.core.files.service import FilesService
from nmp.testing import create_test_client
from starlette.testclient import TestClient
from typer.testing import CliRunner

DEFAULT_WORKSPACE = "default"


@pytest.fixture(scope="module")
def http_client() -> Generator[TestClient, None, None]:
    """TestClient with FilesService (and EntitiesService, which are included by default)."""
    with create_test_client(FilesService, client_type=TestClient) as client:
        yield client


@pytest.fixture(scope="module")
def sdk(http_client: TestClient) -> NeMoPlatform:
    """SDK client backed by the test client."""
    return NeMoPlatform(base_url="http://testserver", http_client=http_client)


@pytest.fixture(scope="module")
def files_client(sdk: NeMoPlatform) -> FilesClient:
    """Provide a FilesClient derived from the SDK."""
    return client_from_platform(sdk, FilesClient)


@pytest.fixture
def random_workspace(sdk: NeMoPlatform) -> str:
    """
    Create a random workspace for tests.

    It creates random enough workspace name to avoid collisions between tests, as we reuse the
    service dependency to make tests faster, but that requires unique workspace names for isolation.
    """
    workspace_name = f"test-{uuid.uuid4().hex[:8]}"
    sdk.workspaces.create(name=workspace_name, description=f"Test Workspace {workspace_name}")
    return workspace_name


class NmpCliRunner(CliRunner):
    def __init__(self, client: NeMoPlatform):
        super().__init__()
        self.client = client

    def invoke(self, *args, **kwargs) -> Result:
        if "obj" not in kwargs or kwargs["obj"] is None:
            kwargs["obj"] = CLIContext(
                overrides={"base_url": "http://test.example.com", "output_format": "json"},
                verbosity=0,
                _client=self.client,
            )
        return super().invoke(*args, **kwargs)


@pytest.fixture
def runner(sdk: NeMoPlatform) -> NmpCliRunner:
    """Create a CLI test runner with injected NeMoPlatform client."""
    return NmpCliRunner(client=sdk)


@pytest.fixture(autouse=True)
def isolated_config(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate tests from local config files and env vars.

    To skip isolation for a specific test, use:
        @pytest.mark.use_real_config
        def test_that_needs_real_config():
            ...
    """
    if request.node.get_closest_marker("use_real_config"):
        return

    # Clear all NMP_ env vars
    for var in list(os.environ):
        if var.startswith("NMP_"):
            monkeypatch.delenv(var, raising=False)

    # Point to an empty config file
    config_file = tmp_path / "config.yaml"
    config_file.touch()
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config_file))


@pytest.fixture
def test_context():
    """Create a fresh CLIContext object for unit tests.

    Use this fixture when testing functions that accept CLIContext directly,
    without going through the CLI.
    """
    return CLIContext(
        overrides={"base_url": "http://test.example.com", "output_format": "json"},
        verbosity=0,
    )
