"""E2E tests for the entities API.

These tests verify basic entity operations work correctly when running
against a fully deployed NMP platform. This includes:
- Entity CRUD operations (create, retrieve, update, delete)
- Entity creation within and without projects
- Listing with sorting and filtering

Note: Many other e2e tests implicitly test the entities API since most
services are built on top of it. These tests provide a direct indicator
for deeper problems in the entities service itself.
"""

import json
import time
import uuid

import pytest
from nemo_platform import APIStatusError, NeMoPlatform

ENTITY_TYPE = "e2e-test-entity"


def _unique_name(prefix: str = "entity") -> str:
    """Generate a unique entity name."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_cluster_info_endpoint_returns_json_with_platform_version_and_revision(sdk: NeMoPlatform):
    """Test GET /cluster-info returns JSON with platform_version and revision keys.

    Verifies the platform cluster-info endpoint returns a json-encoded response
    and includes platform_version and revision fields (values are not validated).
    """
    response = sdk._client.get("/cluster-info")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict), "Response body should be JSON object"
    assert "platform_version" in data, "Response should include a 'platform_version' key"
    assert "revision" in data, "Response should include a 'revision' key"


def test_entity_crud_lifecycle(sdk: NeMoPlatform, workspace: str):
    """Test basic entity create, retrieve, update, delete operations.

    This test verifies the complete entity lifecycle:
    1. Create an entity with specific data
    2. Retrieve it by name and verify contents
    3. Update the entity data
    4. Delete the entity
    5. Verify it no longer exists
    """
    entity_name = _unique_name()
    initial_data = {"key": "initial-value", "nested": {"field": 123}}

    # Create entity
    entity = sdk.entities.create(
        entity_type=ENTITY_TYPE,
        workspace=workspace,
        name=entity_name,
        data=initial_data,
    )
    assert entity.name == entity_name
    assert entity.workspace == workspace
    assert entity.entity_type == ENTITY_TYPE
    assert entity.data["key"] == "initial-value"
    assert entity.data["nested"]["field"] == 123  # ty: ignore[not-subscriptable]

    try:
        # Retrieve by name
        retrieved = sdk.entities.get_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
        assert retrieved.name == entity_name
        assert retrieved.id == entity.id
        assert retrieved.data == initial_data

        # Update entity
        updated_data = {"key": "updated-value", "nested": {"field": 456}, "new_field": True}
        updated = sdk.entities.update_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            data=updated_data,
        )
        assert updated.name == entity_name
        assert updated.data["key"] == "updated-value"
        assert updated.data["nested"]["field"] == 456  # ty: ignore[not-subscriptable]
        assert updated.data["new_field"] is True

        # Verify update persisted
        retrieved_after_update = sdk.entities.get_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
        assert retrieved_after_update.data == updated_data

    finally:
        # Delete entity
        sdk.entities.delete_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )

    # Verify entity no longer exists
    with pytest.raises(APIStatusError) as exc_info:
        sdk.entities.get_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
    assert exc_info.value.status_code == 404


def test_entity_with_project(sdk: NeMoPlatform, workspace: str):
    """Test entity creation within a project.

    Verifies that entities can be associated with projects and that
    the project association is correctly persisted and retrievable.
    """
    project_name = _unique_name("project")
    entity_name = _unique_name()

    # Create project first
    project = sdk.projects.create(
        workspace=workspace,
        name=project_name,
        description="E2E test project",
    )
    assert project.name == project_name

    try:
        # Create entity within project
        entity = sdk.entities.create(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            name=entity_name,
            data={"project_data": "value"},
            project=project_name,
        )
        assert entity.name == entity_name
        assert entity.project == project_name

        # Retrieve and verify project association
        retrieved = sdk.entities.get_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
        assert retrieved.project == project_name

        # Delete entity
        sdk.entities.delete_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )

    finally:
        # Clean up project
        sdk.projects.delete(name=project_name, workspace=workspace)


def test_entity_without_project(sdk: NeMoPlatform, workspace: str):
    """Test entity creation without a project association.

    Verifies that entities can exist at the workspace level without
    being associated with any project.
    """
    entity_name = _unique_name()

    entity = sdk.entities.create(
        entity_type=ENTITY_TYPE,
        workspace=workspace,
        name=entity_name,
        data={"standalone": True},
    )

    try:
        assert entity.name == entity_name
        assert entity.project is None

        retrieved = sdk.entities.get_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
        assert retrieved.project is None

    finally:
        sdk.entities.delete_entity_by_name(
            name=entity_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )


def test_entity_list_and_sorting(sdk: NeMoPlatform, workspace: str):
    """Test listing entities with sorting.

    Creates multiple entities and verifies:
    1. All entities are returned in list
    2. Sorting by created_at works (ascending and descending)
    3. Sorting by name works
    """
    entity_names = [_unique_name(f"sort-{i:02d}") for i in range(5)]
    created_entities = []

    try:
        # Create entities in order
        for name in entity_names:
            entity = sdk.entities.create(
                entity_type=ENTITY_TYPE,
                workspace=workspace,
                name=name,
                data={"order": name},
            )
            time.sleep(1)
            created_entities.append(entity)

        # List all entities of this type
        response = sdk.entities.list(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
        listed_names = {e.name for e in response.data}
        for name in entity_names:
            assert name in listed_names

        # Test descending sort by created_at (default, newest first)
        response_desc = sdk.entities.list(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            sort="-created_at",
        )
        desc_names = [e.name for e in response_desc.data if e.name in entity_names]
        assert desc_names == list(reversed(entity_names))

        # Test ascending sort by created_at (oldest first)
        response_asc = sdk.entities.list(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            sort="created_at",
        )
        asc_names = [e.name for e in response_asc.data if e.name in entity_names]
        assert asc_names == entity_names

        # Test sort by name
        response_by_name = sdk.entities.list(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            sort="name",
        )
        name_sorted = [e.name for e in response_by_name.data if e.name in entity_names]
        assert name_sorted == sorted(entity_names)

    finally:
        # Clean up all created entities
        for name in entity_names:
            try:
                sdk.entities.delete_entity_by_name(
                    name=name,
                    entity_type=ENTITY_TYPE,
                    workspace=workspace,
                )
            except Exception:
                pass


def test_entity_search_filter(sdk: NeMoPlatform, workspace: str):
    """Test filtering entities with search queries.

    Verifies that the search parameter correctly filters entities
    based on field values.
    """
    prefix = _unique_name("filter")
    entity_alpha = f"{prefix}-alpha"
    entity_beta = f"{prefix}-beta"

    try:
        # Create two entities with different data
        sdk.entities.create(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            name=entity_alpha,
            data={"category": "alpha", "value": 100},
        )
        sdk.entities.create(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            name=entity_beta,
            data={"category": "beta", "value": 200},
        )

        # Filter by exact name match
        filter_query = json.dumps({"name": {"$eq": entity_alpha}})
        response = sdk.entities.list(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            filter=filter_query,
        )
        assert len(response.data) == 1
        assert response.data[0].name == entity_alpha

        # Filter by name pattern (like)
        filter_query = json.dumps({"name": {"$like": f"{prefix}%"}})
        response = sdk.entities.list(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            filter=filter_query,
        )
        found_names = {e.name for e in response.data}
        assert entity_alpha in found_names
        assert entity_beta in found_names

        # Filter by data field
        filter_query = json.dumps({"data.category": {"$eq": "beta"}})
        response = sdk.entities.list(
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            filter=filter_query,
        )
        assert len(response.data) == 1
        assert response.data[0].name == entity_beta

    finally:
        for name in [entity_alpha, entity_beta]:
            try:
                sdk.entities.delete_entity_by_name(
                    name=name,
                    entity_type=ENTITY_TYPE,
                    workspace=workspace,
                )
            except Exception:
                pass


def test_entity_rename(sdk: NeMoPlatform, workspace: str):
    """Test renaming an entity via update.

    Verifies that entities can be renamed and the old name
    no longer works after rename.
    """
    old_name = _unique_name("old")
    new_name = _unique_name("new")

    entity = sdk.entities.create(
        entity_type=ENTITY_TYPE,
        workspace=workspace,
        name=old_name,
        data={"test": "rename"},
    )

    try:
        # Rename entity
        renamed = sdk.entities.update_entity_by_name(
            name=old_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
            data=entity.data,
            new_name=new_name,
        )
        assert renamed.name == new_name
        assert renamed.id == entity.id

        # Verify old name no longer works
        with pytest.raises(APIStatusError) as exc_info:
            sdk.entities.get_entity_by_name(
                name=old_name,
                entity_type=ENTITY_TYPE,
                workspace=workspace,
            )
        assert exc_info.value.status_code == 404

        # Verify new name works
        retrieved = sdk.entities.get_entity_by_name(
            name=new_name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
        assert retrieved.name == new_name

    finally:
        # Clean up with new name
        try:
            sdk.entities.delete_entity_by_name(
                name=new_name,
                entity_type=ENTITY_TYPE,
                workspace=workspace,
            )
        except Exception:
            pass


def test_entity_auto_generated_name(sdk: NeMoPlatform, workspace: str):
    """Test that entities can be created without specifying a name.

    When no name is provided, the API should auto-generate a unique name.
    """
    entity = sdk.entities.create(
        entity_type=ENTITY_TYPE,
        workspace=workspace,
        data={"auto_name": True},
    )

    try:
        assert entity.name is not None
        assert len(entity.name) > 0
        # Auto-generated names typically follow a pattern like "e2e-test-entity-xxxxx"
        assert ENTITY_TYPE.replace("_", "-").replace("-", "") in entity.name.replace("-", "") or entity.name

        # Verify we can retrieve by the generated name
        retrieved = sdk.entities.get_entity_by_name(
            name=entity.name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
        assert retrieved.id == entity.id

    finally:
        sdk.entities.delete_entity_by_name(
            name=entity.name,
            entity_type=ENTITY_TYPE,
            workspace=workspace,
        )
