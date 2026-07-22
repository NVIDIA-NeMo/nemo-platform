# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for IAM role binding CRUD operations."""

import uuid

from fastapi.testclient import TestClient

# Default workspace for tests
DEFAULT_WORKSPACE = "default"

SERVICE_PRINCIPAL = "service:integration-test"

# Platform mounts auth at /apis/auth
IAM_ROLE_BINDINGS_PATH = "/apis/auth/v2/iam/role-bindings"


class TestIAMRoleBindings:
    """Tests for IAM role binding CRUD operations."""

    def test_list_role_bindings(self, http_client: TestClient):
        """Test listing role bindings."""
        headers = {"X-NMP-Principal-Id": SERVICE_PRINCIPAL}
        response = http_client.get(IAM_ROLE_BINDINGS_PATH, headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert isinstance(data["data"], list)

    def test_role_binding_crud_lifecycle(self, http_client: TestClient):
        """Test full CRUD lifecycle for role bindings."""
        headers = {"X-NMP-Principal-Id": SERVICE_PRINCIPAL}
        test_principal = f"test-user-{uuid.uuid4().hex[:8]}@example.com"
        test_workspace = DEFAULT_WORKSPACE
        test_role = "Viewer"

        # CREATE
        binding_data = {
            "principal": test_principal,
            "workspace": test_workspace,
            "role": test_role,
        }
        response = http_client.post(
            "/apis/auth/v2/iam/role-bindings?wait_role_propagation=false",
            json=binding_data,
            headers=headers,
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        created = response.json()
        assert created["principal"] == test_principal
        assert created["workspace"] == test_workspace
        assert created["role"] == test_role
        assert "id" in created
        assert "name" in created
        binding_id = created["id"]
        binding_name = created["name"]

        # READ (single) - use name in path
        response = http_client.get(f"/apis/auth/v2/iam/role-bindings/{binding_name}", headers=headers)
        assert response.status_code == 200, f"Get failed: {response.text}"
        fetched = response.json()
        assert fetched["id"] == binding_id
        assert fetched["principal"] == test_principal

        # LIST (verify it appears)
        response = http_client.get("/apis/auth/v2/iam/role-bindings", headers=headers)
        assert response.status_code == 200, f"List failed: {response.text}"
        bindings = response.json()
        assert any(b["id"] == binding_id for b in bindings["data"])

        # DELETE (revoke) - use name in path
        response = http_client.delete(
            f"/apis/auth/v2/iam/role-bindings/{binding_name}?wait_role_propagation=false",
            headers=headers,
        )
        assert response.status_code == 200, f"Delete failed: {response.text}"
        deleted = response.json()
        assert deleted["id"] == binding_id

        # Verify revoked (should still exist but be revoked)
        response = http_client.get(f"/apis/auth/v2/iam/role-bindings/{binding_name}", headers=headers)
        assert response.status_code == 200
        revoked = response.json()
        assert revoked["revoked_at"] is not None

    def test_create_duplicate_role_binding_fails(self, http_client: TestClient):
        """Test that creating a duplicate active role binding returns 409."""
        headers = {"X-NMP-Principal-Id": SERVICE_PRINCIPAL}
        test_principal = f"dup-user-{uuid.uuid4().hex[:8]}@example.com"
        test_workspace = DEFAULT_WORKSPACE
        test_role = "Editor"

        binding_data = {
            "principal": test_principal,
            "workspace": test_workspace,
            "role": test_role,
        }

        # Create first binding
        response = http_client.post(
            "/apis/auth/v2/iam/role-bindings?wait_role_propagation=false",
            json=binding_data,
            headers=headers,
        )
        assert response.status_code == 200
        binding_name = response.json()["name"]

        # Try to create duplicate
        response = http_client.post(
            "/apis/auth/v2/iam/role-bindings?wait_role_propagation=false",
            json=binding_data,
            headers=headers,
        )
        assert response.status_code == 409

        # Cleanup - use name from response
        http_client.delete(
            f"/apis/auth/v2/iam/role-bindings/{binding_name}?wait_role_propagation=false",
            headers=headers,
        )

    def test_get_nonexistent_role_binding_returns_404(self, http_client: TestClient):
        """Test that getting a non-existent role binding returns 404."""
        headers = {"X-NMP-Principal-Id": SERVICE_PRINCIPAL}
        # Use a fake name that looks like a hash-based binding name
        fake_name = f"rb-{uuid.uuid4().hex[:24]}"
        response = http_client.get(f"/apis/auth/v2/iam/role-bindings/{fake_name}", headers=headers)
        assert response.status_code == 404

    def test_revoke_already_revoked_binding_returns_409(self, http_client: TestClient):
        """Test that revoking an already revoked binding returns 409."""
        headers = {"X-NMP-Principal-Id": SERVICE_PRINCIPAL}
        test_principal = f"revoke-user-{uuid.uuid4().hex[:8]}@example.com"
        test_workspace = DEFAULT_WORKSPACE
        test_role = "Viewer"

        # Create and immediately revoke a binding
        binding_data = {
            "principal": test_principal,
            "workspace": test_workspace,
            "role": test_role,
        }
        response = http_client.post(
            "/apis/auth/v2/iam/role-bindings?wait_role_propagation=false",
            json=binding_data,
            headers=headers,
        )
        assert response.status_code == 200
        binding_name = response.json()["name"]

        # Revoke it - use name from response
        response = http_client.delete(
            f"/apis/auth/v2/iam/role-bindings/{binding_name}?wait_role_propagation=false",
            headers=headers,
        )
        assert response.status_code == 200

        # Try to revoke again
        response = http_client.delete(
            f"/apis/auth/v2/iam/role-bindings/{binding_name}?wait_role_propagation=false",
            headers=headers,
        )
        assert response.status_code == 409

    def test_list_role_bindings_with_pagination(self, http_client: TestClient):
        """Test listing role bindings with pagination."""
        headers = {"X-NMP-Principal-Id": SERVICE_PRINCIPAL}
        response = http_client.get("/apis/auth/v2/iam/role-bindings?page=1&page_size=5", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 5
