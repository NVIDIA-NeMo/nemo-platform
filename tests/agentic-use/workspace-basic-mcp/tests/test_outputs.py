# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Use this file to define pytest tests that verify the outputs of the task.

This file will be copied to /tests/test_outputs.py and run by the /tests/test.sh file
from the working directory.
"""

import os

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.workspaces.client import WorkspacesClient


def test_workspace_created() -> None:
    """Test that the harbor-test-workspace was successfully created."""
    # Get NeMo Platform API base URL from environment
    nmp_base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")

    # Create SDK client and list workspaces
    client = NeMoPlatform(base_url=nmp_base_url)
    response = client_from_platform(client, WorkspacesClient).list_workspaces().data()

    # Extract workspace names from the SDK response
    workspace_names = [ws.name for ws in response.data]

    # Verify that harbor-test-workspace EXISTS
    assert "harbor-test-workspace" in workspace_names, (
        f"Workspace 'harbor-test-workspace' was not created! Found workspaces: {workspace_names}"
    )

    print("✓ Test passed: harbor-test-workspace was successfully created")
