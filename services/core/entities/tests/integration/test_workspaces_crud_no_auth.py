# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for workspace CRUD operations without authorization.

These tests verify:
- Workspace CRUD operations (create, retrieve, list, update, delete)
- Validation (duplicate names, non-existent workspaces, invalid input)

Uses the create_test_client pattern for fast in-memory testing.
"""

from typing import Generator

import pytest
from nemo_platform_plugin.client.client import NemoClient
from nmp.core.entities.service import EntitiesService
from nmp.testing import create_test_client, short_unique_name


@pytest.fixture(scope="module")
def sdk() -> Generator[NemoClient, None, None]:
    """SDK client with EntitiesService (auth disabled)."""
    with create_test_client(
        EntitiesService,
        workspaces=[],  # Don't auto-create workspaces - we're testing workspace CRUD
        projects=[],  # Skip project creation
    ) as sdk:
        yield sdk


@pytest.mark.integration
class TestWorkspaceCRUD:
    """Test workspace CRUD operations without authorization."""

    def test_default_workspaces_created_on_startup(self, sdk: NemoClient):
        """Test that 'default' and 'system' workspaces are created automatically on startup."""
        # These workspaces are created by EntitiesService.startup()
        default_ws = sdk.workspaces.get_workspace("default")
        assert default_ws.name == "default"
        assert default_ws.description == "General-purpose workspace (all users have write access)"

        system_ws = sdk.workspaces.get_workspace("system")
        assert system_ws.name == "system"
        assert system_ws.description == "Platform-provided resources (read-only for users)"

    def test_create_workspace(self, sdk: NemoClient):
        """Test creating a new workspace."""
        workspace_name = short_unique_name("test-ws")

        workspace = sdk.workspaces.create_workspace(
            name=workspace_name,
            description="Test workspace for integration tests",
        )

        assert workspace.name == workspace_name
        assert workspace.description == "Test workspace for integration tests"
        assert workspace.id is not None
        assert workspace.created_at is not None
        assert workspace.updated_at is not None
        # Without auth, created_by/updated_by are empty string
        assert workspace.created_by == ""
        assert workspace.updated_by == ""

    def test_create_duplicate_workspace_fails(self, sdk: NemoClient):
        """Test that creating a duplicate workspace returns 409."""
        workspace_name = short_unique_name("dup-ws")

        # Create first workspace
        sdk.workspaces.create_workspace(name=workspace_name)

        # Try to create duplicate
        from nemo_platform_plugin.client.errors import ConflictError

        with pytest.raises(ConflictError) as exc_info:
            sdk.workspaces.create_workspace(name=workspace_name)

        assert "already exists" in str(exc_info.value)

    def test_retrieve_workspace(self, sdk: NemoClient):
        """Test retrieving a workspace by name."""
        workspace_name = short_unique_name("get-ws")
        created = sdk.workspaces.create_workspace(
            name=workspace_name,
            description="Retrieve test",
        )

        retrieved = sdk.workspaces.get_workspace(workspace_name)

        assert retrieved.id == created.id
        assert retrieved.name == workspace_name
        assert retrieved.description == "Retrieve test"

    def test_retrieve_nonexistent_workspace_fails(self, sdk: NemoClient):
        """Test that retrieving a non-existent workspace returns 404."""
        from nemo_platform_plugin.client.errors import NotFoundError

        with pytest.raises(NotFoundError):
            sdk.workspaces.get_workspace("nonexistent-workspace")

    def test_list_workspaces(self, sdk: NemoClient):
        """Test listing workspaces."""
        workspace_name = short_unique_name("list-ws")
        created = sdk.workspaces.create_workspace(name=workspace_name)

        result = sdk.workspaces.list_workspaces()

        workspace_ids = [ws.id for ws in result.data]
        assert created.id in workspace_ids

    def test_list_workspaces_with_pagination(self, sdk: NemoClient):
        """Test pagination when listing workspaces."""
        # Create a few workspaces
        for i in range(3):
            name = short_unique_name(f"page-{i}")
            sdk.workspaces.create_workspace(name=name)

        # List with pagination
        result = sdk.workspaces.list_workspaces(page=1, page_size=2)

        assert result.pagination is not None
        assert result.pagination.page == 1
        assert result.pagination.page_size == 2

    def test_update_workspace(self, sdk: NemoClient):
        """Test updating a workspace description."""
        workspace_name = short_unique_name("upd-ws")
        sdk.workspaces.create_workspace(
            name=workspace_name,
            description="Original description",
        )

        updated = sdk.workspaces.update_workspace(
            workspace_name,
            description="Updated description",
        )

        assert updated.name == workspace_name
        assert updated.description == "Updated description"
        # Without auth, created_by/updated_by are empty string
        assert updated.created_by == ""
        assert updated.updated_by == ""

    def test_update_nonexistent_workspace_fails(self, sdk: NemoClient):
        """Test that updating a non-existent workspace returns 404."""
        from nemo_platform_plugin.client.errors import NotFoundError

        with pytest.raises(NotFoundError):
            sdk.workspaces.update_workspace(
                "nonexistent-workspace",
                description="Should fail",
            )

    def test_delete_workspace(self, sdk: NemoClient):
        """Test deleting a workspace."""
        workspace_name = short_unique_name("del-ws")
        sdk.workspaces.create_workspace(name=workspace_name)

        # Delete the workspace
        sdk.workspaces.delete_workspace(workspace_name)

        # Verify it's deleted
        from nemo_platform_plugin.client.errors import NotFoundError

        with pytest.raises(NotFoundError):
            sdk.workspaces.get_workspace(workspace_name)

    def test_delete_nonexistent_workspace_fails(self, sdk: NemoClient):
        """Test that deleting a non-existent workspace returns 404."""
        from nemo_platform_plugin.client.errors import NotFoundError

        with pytest.raises(NotFoundError):
            sdk.workspaces.delete_workspace("nonexistent-workspace")

    def test_workspace_crud_lifecycle(self, sdk: NemoClient):
        """Test full CRUD lifecycle for workspaces."""
        workspace_name = short_unique_name("crud-ws")

        # CREATE
        created = sdk.workspaces.create_workspace(
            name=workspace_name,
            description="CRUD lifecycle test",
        )
        assert created.name == workspace_name
        assert created.id is not None

        # READ
        retrieved = sdk.workspaces.get_workspace(workspace_name)
        assert retrieved.id == created.id

        # UPDATE
        updated = sdk.workspaces.update_workspace(
            workspace_name,
            description="Updated in lifecycle test",
        )
        assert updated.description == "Updated in lifecycle test"

        # DELETE
        sdk.workspaces.delete_workspace(workspace_name)

        # Verify deleted
        from nemo_platform_plugin.client.errors import NotFoundError

        with pytest.raises(NotFoundError):
            sdk.workspaces.get_workspace(workspace_name)


@pytest.mark.integration
class TestWorkspaceValidation:
    """Test workspace input validation."""

    def test_create_workspace_invalid_name(self, sdk: NemoClient):
        """Test that creating a workspace with invalid name returns 422."""
        # Names with spaces are invalid
        response = sdk._client.post(
            "/apis/entities/v2/workspaces",
            json={"name": "invalid name with spaces"},
        )
        assert response.status_code == 422

    def test_create_workspace_empty_name(self, sdk: NemoClient):
        """Test that creating a workspace with empty name returns 422."""
        response = sdk._client.post(
            "/apis/entities/v2/workspaces",
            json={"name": ""},
        )
        assert response.status_code == 422
