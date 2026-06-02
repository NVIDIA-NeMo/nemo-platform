# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for workspace CRUD operations with authorization enabled.

These tests verify:
- Authorization behavior (401 without auth, proper access with auth)
- Role-based access control (Admin, Viewer permissions)
- Workspace visibility (users only see workspaces they have access to)
- Role binding creation on workspace creation

Uses the create_test_client pattern for fast in-memory testing.
"""

import uuid
from contextlib import contextmanager
from typing import Generator

import pytest
from nemo_platform import ConflictError, NeMoPlatform, PermissionDeniedError
from nmp.core.entities.service import EntitiesService
from nmp.testing import TEST_USER_EMAIL, create_test_client, short_unique_name


@contextmanager
def as_user(sdk: NeMoPlatform, email: str) -> Generator[None, None, None]:
    """Context manager to temporarily set the SDK's auth headers for a specific user."""
    old_headers = dict(sdk._client.headers)
    sdk._client.headers["X-NMP-Principal-Id"] = email
    try:
        yield
    finally:
        sdk._client.headers.clear()
        sdk._client.headers.update(old_headers)


@contextmanager
def as_user_with_id_and_email(sdk: NeMoPlatform, principal_id: str, email: str) -> Generator[None, None, None]:
    """Like production OIDC: subject/object id in Principal-Id, email in Principal-Email."""
    old_headers = dict(sdk._client.headers)
    sdk._client.headers["X-NMP-Principal-Id"] = principal_id
    sdk._client.headers["X-NMP-Principal-Email"] = email
    try:
        yield
    finally:
        sdk._client.headers.clear()
        sdk._client.headers.update(old_headers)


@contextmanager
def as_user_id_only(sdk: NeMoPlatform, principal_id: str) -> Generator[None, None, None]:
    """Principal-Id set without X-NMP-Principal-Email (e.g. token without email claim)."""
    old_headers = dict(sdk._client.headers)
    sdk._client.headers["X-NMP-Principal-Id"] = principal_id
    sdk._client.headers.pop("X-NMP-Principal-Email", None)
    try:
        yield
    finally:
        sdk._client.headers.clear()
        sdk._client.headers.update(old_headers)


@contextmanager
def as_user_with_id_and_groups(sdk: NeMoPlatform, principal_id: str, groups: list[str]) -> Generator[None, None, None]:
    """Subject id with group memberships (comma-separated X-NMP-Principal-Groups)."""
    old_headers = dict(sdk._client.headers)
    sdk._client.headers["X-NMP-Principal-Id"] = principal_id
    sdk._client.headers["X-NMP-Principal-Groups"] = ",".join(groups)
    sdk._client.headers.pop("X-NMP-Principal-Email", None)
    try:
        yield
    finally:
        sdk._client.headers.clear()
        sdk._client.headers.update(old_headers)


@contextmanager
def as_service(sdk: NeMoPlatform, service_name: str) -> Generator[None, None, None]:
    """Context manager to temporarily set the SDK's auth headers for a service principal."""
    old_headers = dict(sdk._client.headers)
    sdk._client.headers["X-NMP-Principal-Id"] = f"service:{service_name}"
    try:
        yield
    finally:
        sdk._client.headers.clear()
        sdk._client.headers.update(old_headers)


@pytest.fixture(scope="module")
def sdk() -> Generator[NeMoPlatform, None, None]:
    """SDK client with EntitiesService (auth enabled)."""
    with create_test_client(
        EntitiesService,
        auth_enabled=True,
        workspaces=[],  # Don't auto-create workspaces - we're testing workspace CRUD
        projects=[],  # Skip project creation
    ) as sdk:
        yield sdk


@pytest.mark.integration
class TestWorkspaceCRUDWithAuth:
    """Test workspace CRUD operations with authorization enabled."""

    def test_default_workspaces_created_on_startup(self, sdk: NeMoPlatform):
        """Test that 'default' and 'system' workspaces are created automatically on startup."""
        # These workspaces are created by EntitiesService.startup() and are public
        with as_user(sdk, TEST_USER_EMAIL):
            default_ws = sdk.workspaces.retrieve("default")
            assert default_ws.name == "default"
            assert default_ws.description == "General-purpose workspace (all users have write access)"

            system_ws = sdk.workspaces.retrieve("system")
            assert system_ws.name == "system"
            assert system_ws.description == "Platform-provided resources (read-only for users)"

            # Verify regular user can see public workspaces when listing
            result = sdk.workspaces.list()
            workspace_names = [ws.name for ws in result.data]
            assert "default" in workspace_names, "Regular user should see 'default' workspace in list"
            assert "system" in workspace_names, "Regular user should see 'system' workspace in list"

    def test_create_workspace_without_auth_fails(self, sdk: NeMoPlatform):
        """Test that creating a workspace without auth headers returns 401."""
        workspace_name = short_unique_name("noauth")

        # Use raw client to test without auth headers
        response = sdk._client.post(
            "/apis/entities/v2/workspaces",
            json={"name": workspace_name, "description": "Should fail"},
        )

        assert response.status_code == 401

    def test_create_workspace_with_auth(self, sdk: NeMoPlatform):
        """Test creating a workspace with proper auth headers."""
        workspace_name = short_unique_name("auth-ws")

        with as_user(sdk, TEST_USER_EMAIL):
            workspace = sdk.workspaces.create(
                name=workspace_name,
                description="Auth test workspace",
            )

        assert workspace.name == workspace_name
        assert workspace.description == "Auth test workspace"
        assert workspace.created_by == TEST_USER_EMAIL
        assert workspace.updated_by == TEST_USER_EMAIL

    def test_creator_gets_admin_role(self, sdk: NeMoPlatform):
        """Test that workspace creator automatically gets Admin role."""
        workspace_name = short_unique_name("admin-ws")
        creator_email = f"creator-{uuid.uuid4().hex[:8]}@example.com"

        with as_user(sdk, creator_email):
            # Create workspace
            sdk.workspaces.create(name=workspace_name)

            # Verify creator can access the workspace (has Admin role)
            workspace = sdk.workspaces.retrieve(workspace_name)
            assert workspace.name == workspace_name
            assert workspace.created_by == creator_email
            assert workspace.updated_by == creator_email

            # Verify creator is listed as a member with Admin role
            members = sdk.workspaces.members.list(workspace=workspace_name)
            creator_member = next((m for m in members.data if m.principal == creator_email), None)
            assert creator_member is not None, "Creator should be listed as a member"
            assert "Admin" in creator_member.roles, "Creator should have Admin role"

    def test_creator_admin_binding_prefers_email_when_id_differs(self, sdk: NeMoPlatform):
        """Admin role binding principal is email when sub/oid differs from email (IdP-style headers)."""
        workspace_name = short_unique_name("email-bind")
        principal_id = str(uuid.uuid4())
        creator_email = f"creator-{uuid.uuid4().hex[:8]}@example.com"

        with as_user_with_id_and_email(sdk, principal_id, creator_email):
            sdk.workspaces.create(name=workspace_name)
            workspace = sdk.workspaces.retrieve(workspace_name)
            assert workspace.created_by == principal_id

            members = sdk.workspaces.members.list(workspace=workspace_name)
        creator_member = next((m for m in members.data if "Admin" in m.roles), None)
        assert creator_member is not None
        assert creator_member.principal == creator_email
        assert creator_member.principal != principal_id
        assert creator_member.granted_by == principal_id

    def test_creator_admin_binding_uses_id_when_email_header_absent(self, sdk: NeMoPlatform):
        """Admin role binding falls back to principal id when X-NMP-Principal-Email is not set."""
        workspace_name = short_unique_name("id-bind")
        principal_id = str(uuid.uuid4())

        with as_user_id_only(sdk, principal_id):
            sdk.workspaces.create(name=workspace_name)
            members = sdk.workspaces.members.list(workspace=workspace_name)

        creator_member = next((m for m in members.data if "Admin" in m.roles), None)
        assert creator_member is not None
        assert creator_member.principal == principal_id

    def test_member_added_by_email_lists_workspace_when_subject_is_uuid(self, sdk: NeMoPlatform):
        """Email-keyed role bindings must count for list_workspaces when JWT id is oid/sub, not email."""
        workspace_name = short_unique_name("invite-email")
        owner_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
        member_id = str(uuid.uuid4())
        member_email = f"member-{uuid.uuid4().hex[:8]}@example.com"

        with as_user(sdk, owner_email):
            sdk.workspaces.create(name=workspace_name)
            sdk.workspaces.members.create(
                workspace=workspace_name,
                principal=member_email,
                roles=["Editor"],
                wait_role_propagation=True,
            )

        with as_user_with_id_and_email(sdk, member_id, member_email):
            result = sdk.workspaces.list()
            names = [ws.name for ws in result.data]

        assert workspace_name in names

    def test_member_added_by_group_lists_workspace_when_user_in_group(self, sdk: NeMoPlatform):
        """Group-keyed role bindings must count for list_workspaces when the user carries that group."""
        workspace_name = short_unique_name("invite-group")
        owner_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
        group_principal = f"team-{uuid.uuid4().hex[:12]}"
        member_user_id = str(uuid.uuid4())

        with as_user(sdk, owner_email):
            sdk.workspaces.create(name=workspace_name)
            sdk.workspaces.members.create(
                workspace=workspace_name,
                principal=group_principal,
                roles=["Editor"],
                wait_role_propagation=True,
            )

        with as_user_with_id_and_groups(sdk, member_user_id, [group_principal]):
            result = sdk.workspaces.list()
            names = [ws.name for ws in result.data]

        assert workspace_name in names

    def test_list_workspaces_only_shows_accessible(self, sdk: NeMoPlatform):
        """Test that listing workspaces only shows workspaces the user can access."""
        user1_email = f"user1-{uuid.uuid4().hex[:8]}@example.com"
        user2_email = f"user2-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("priv-ws")

        # User1 creates a workspace
        with as_user(sdk, user1_email):
            sdk.workspaces.create(name=workspace_name)

            # User1 should see the workspace
            result = sdk.workspaces.list()
            user1_workspaces = [ws.name for ws in result.data]
            assert workspace_name in user1_workspaces

        # User2 should NOT see the workspace (no role binding)
        with as_user(sdk, user2_email):
            result = sdk.workspaces.list()
            user2_workspaces = [ws.name for ws in result.data]
            assert workspace_name not in user2_workspaces

    def test_user_without_role_cannot_access_workspace(self, sdk: NeMoPlatform):
        """Test that a user without a role cannot access a workspace."""
        owner_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
        other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("no-access")

        # Owner creates workspace
        with as_user(sdk, owner_email):
            sdk.workspaces.create(name=workspace_name)

        # Other user tries to access - should fail
        with as_user(sdk, other_email):
            with pytest.raises(PermissionDeniedError):
                sdk.workspaces.retrieve(workspace_name)

    def test_admin_can_update_workspace(self, sdk: NeMoPlatform):
        """Test that an Admin can update their workspace."""
        admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("upd-auth")

        with as_user(sdk, admin_email):
            # Create workspace (admin gets Admin role automatically)
            created = sdk.workspaces.create(name=workspace_name, description="Original")
            assert created.created_by == admin_email

            # Update workspace
            updated = sdk.workspaces.update(workspace_name, description="Updated by admin")
            assert updated.description == "Updated by admin"
            assert updated.created_by == admin_email
            assert updated.updated_by == admin_email

    def test_updated_by_changes_when_different_user_updates(self, sdk: NeMoPlatform):
        """Test that updated_by reflects the user who made the update, not the creator."""
        creator_email = f"creator-{uuid.uuid4().hex[:8]}@example.com"
        updater_email = f"updater-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("upd-by")

        # Creator creates workspace
        with as_user(sdk, creator_email):
            created = sdk.workspaces.create(name=workspace_name, description="Original")
            assert created.created_by == creator_email
            assert created.updated_by == creator_email

            # Add updater as Admin so they can update
            sdk.workspaces.members.create(
                workspace=workspace_name,
                principal=updater_email,
                roles=["Admin"],
                wait_role_propagation=True,
            )

        # Different user updates the workspace
        with as_user(sdk, updater_email):
            updated = sdk.workspaces.update(workspace_name, description="Updated by different user")
            assert updated.description == "Updated by different user"
            # created_by should remain the original creator
            assert updated.created_by == creator_email
            # updated_by should be the user who made the update
            assert updated.updated_by == updater_email

    def test_viewer_cannot_update_workspace(self, sdk: NeMoPlatform):
        """Test that a Viewer cannot update a workspace."""
        owner_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
        viewer_email = f"viewer-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("view-only")

        # Owner creates workspace and adds viewer
        with as_user(sdk, owner_email):
            sdk.workspaces.create(name=workspace_name)
            sdk.workspaces.members.create(
                workspace=workspace_name,
                principal=viewer_email,
                roles=["Viewer"],
                wait_role_propagation=True,
            )

        # Viewer can read but cannot update
        with as_user(sdk, viewer_email):
            workspace = sdk.workspaces.retrieve(workspace_name)
            assert workspace.name == workspace_name

            with pytest.raises(PermissionDeniedError):
                sdk.workspaces.update(workspace_name, description="Updated by viewer")

    def test_delete_workspace_deletes_role_bindings(self, sdk: NeMoPlatform):
        """Test that workspace deletion automatically deletes role bindings.

        Role bindings are system-managed and should not block workspace deletion.
        """
        admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("del-ok")

        with as_user(sdk, admin_email):
            # Create workspace (creates Admin role binding automatically)
            sdk.workspaces.create(name=workspace_name)

            # Verify role binding exists
            members = sdk.workspaces.members.list(workspace=workspace_name)
            assert len(members.data) > 0

            # Delete workspace - should succeed, role bindings are deleted automatically
            sdk.workspaces.delete(workspace_name)

        # Verify workspace is deleted by checking it's not in the list
        # (after deletion, user no longer has access so we check via list)
        with as_user(sdk, admin_email):
            workspaces = sdk.workspaces.list()
            workspace_names = [ws.name for ws in workspaces.data]
            assert workspace_name not in workspace_names

    def test_cannot_remove_last_admin_via_member_delete(self, sdk: NeMoPlatform):
        """Test that removing the last Admin via member delete fails."""

        admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("last-admin")

        with as_user(sdk, admin_email):
            # Create workspace (admin is the only Admin)
            sdk.workspaces.create(name=workspace_name)

            # Try to remove self (the last admin) - should fail
            with pytest.raises(ConflictError) as exc_info:
                sdk.workspaces.members.delete(workspace=workspace_name, principal_id=admin_email)

            assert "last admin" in str(exc_info.value).lower()

    def test_cannot_remove_last_admin_via_role_update(self, sdk: NeMoPlatform):
        """Test that removing the Admin role via update when they're the last Admin fails."""

        admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("upd-admin")

        with as_user(sdk, admin_email):
            # Create workspace (admin is the only Admin)
            sdk.workspaces.create(name=workspace_name)

            # Try to change own role from Admin to Viewer - should fail
            with pytest.raises(ConflictError) as exc_info:
                sdk.workspaces.members.update(
                    workspace=workspace_name,
                    principal_id=admin_email,
                    roles=["Viewer"],
                )

            assert "last admin" in str(exc_info.value).lower()

    def test_can_remove_admin_when_another_admin_exists(self, sdk: NeMoPlatform):
        """Test that removing an Admin succeeds when another Admin exists."""
        admin1_email = f"admin1-{uuid.uuid4().hex[:8]}@example.com"
        admin2_email = f"admin2-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("two-admins")

        with as_user(sdk, admin1_email):
            # Create workspace (admin1 is the Admin)
            sdk.workspaces.create(name=workspace_name)

            # Add admin2 as another Admin
            sdk.workspaces.members.create(
                workspace=workspace_name,
                principal=admin2_email,
                roles=["Admin"],
                wait_role_propagation=True,
            )

            # Now admin1 can remove themselves since admin2 is also an Admin
            sdk.workspaces.members.delete(workspace=workspace_name, principal_id=admin1_email)

        # Verify admin1 is no longer a member (check as admin2 since admin1 lost access)
        with as_user(sdk, admin2_email):
            members = sdk.workspaces.members.list(workspace=workspace_name)
            member_principals = [m.principal for m in members.data]
            assert admin1_email not in member_principals
            assert admin2_email in member_principals

    def test_delete_workspace_with_entities_marks_for_deletion(self, sdk: NeMoPlatform):
        """Test that deleting a workspace with entities marks it for async deletion.

        With cascade delete, workspaces are marked for deletion and become inaccessible.
        An async cleanup controller handles entity deletion.

        Note: After deletion, the user may get 403 (role bindings deleted) or 404
        (workspace marked for deletion). Both indicate the workspace is inaccessible.
        """
        from nemo_platform import NotFoundError, PermissionDeniedError

        admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        workspace_name = short_unique_name("has-ent")

        with as_user(sdk, admin_email):
            sdk.workspaces.create(name=workspace_name)

        # Create entity as service principal (generic entities API requires service credentials)
        with as_service(sdk, "entities"):
            sdk.entities.create(
                workspace=workspace_name,
                entity_type="test-entity-type",
                name="test-entity",
                data={"key": "value"},
            )

        with as_user(sdk, admin_email):
            sdk.workspaces.delete(workspace_name)

            # Verify workspace is inaccessible (403 or 404)
            # 403: Role bindings deleted, user has no access
            # 404: Workspace marked for deletion
            with pytest.raises((NotFoundError, PermissionDeniedError)):
                sdk.workspaces.retrieve(workspace_name)
