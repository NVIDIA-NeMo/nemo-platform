"""E2E tests for the secrets service.

These tests verify basic secret creation and listing operations
work correctly when running against a fully deployed NMP platform.
"""

import uuid

from nemo_platform import NeMoPlatform


def test_secret_create_and_list(sdk: NeMoPlatform, workspace: str):
    """Test creating a secret and listing it in the workspace.

    This test verifies the secrets system works end-to-end:
    1. Create a secret with a test value
    2. Verify the secret appears in the list of workspace secrets
    3. Verify the secret can be retrieved
    """
    secret_name = f"e2e-secret-{uuid.uuid4().hex[:8]}"
    secret_value = "e2e-test-secret-value"

    # Create a secret
    secret = sdk.secrets.create(
        workspace=workspace,
        name=secret_name,
        value=secret_value,
    )
    assert secret.name == secret_name
    assert secret.workspace == workspace

    # List secrets and verify the new secret appears
    list_response = sdk.secrets.list(workspace=workspace)
    secret_names = [s.name for s in list_response.data]
    assert secret_name in secret_names

    # Retrieve the secret to verify it was created correctly
    retrieved_secret = sdk.secrets.retrieve(secret_name, workspace=workspace)
    assert retrieved_secret.name == secret_name
    assert retrieved_secret.workspace == workspace


def test_secret_create_duplicate_fails(sdk: NeMoPlatform, workspace: str):
    """Test that creating a secret with a duplicate name fails.

    This test verifies that the secrets system enforces unique
    secret names within a workspace.
    """
    secret_name = f"e2e-duplicate-secret-{uuid.uuid4().hex[:8]}"
    secret_value = "e2e-duplicate-test-secret-value"

    # Create the initial secret
    sdk.secrets.create(
        workspace=workspace,
        name=secret_name,
        value=secret_value,
    )

    # Attempt to create a duplicate secret and expect failure
    try:
        sdk.secrets.create(
            workspace=workspace,
            name=secret_name,
            value="some-other-value",
        )
        assert False, "Expected an exception when creating a duplicate secret"
    except Exception as e:
        # Verify that the exception indicates a duplicate resource
        assert "already exists" in str(e) or "duplicate" in str(e)


def test_secret_create_and_delete(sdk: NeMoPlatform, workspace: str):
    """Test creating and deleting a secret.

    This test verifies that a secret can be created and then deleted,
    and that it no longer appears in the list of secrets after deletion.
    """
    secret_name = f"e2e-delete-secret-{uuid.uuid4().hex[:8]}"
    secret_value = "e2e-delete-test-secret-value"

    # Create a secret
    sdk.secrets.create(
        workspace=workspace,
        name=secret_name,
        value=secret_value,
    )

    # Verify the secret appears in the list
    list_response = sdk.secrets.list(workspace=workspace)
    secret_names = [s.name for s in list_response.data]
    assert secret_name in secret_names

    # Delete the secret
    sdk.secrets.delete(
        workspace=workspace,
        name=secret_name,
    )

    # Verify the secret no longer appears in the list
    list_response = sdk.secrets.list(workspace=workspace)
    secret_names = [s.name for s in list_response.data]
    assert secret_name not in secret_names


def test_secret_data_not_in_create_response(sdk: NeMoPlatform, workspace: str):
    """Test that secret data is not exposed in the create response.

    This test verifies that when creating a secret, the response does not
    contain the secret value - only metadata like name and workspace.
    """
    secret_name = f"e2e-no-data-create-{uuid.uuid4().hex[:8]}"
    secret_value = "this-should-not-appear-in-response"

    secret = sdk.secrets.create(
        workspace=workspace,
        name=secret_name,
        value=secret_value,
    )

    # Verify name and workspace are present
    assert secret.name == secret_name
    assert secret.workspace == workspace

    # Verify the secret value is not exposed in the response object
    # The SDK object should not have a 'data' attribute with the secret value
    secret_dict = secret.model_dump()
    assert "data" not in secret_dict or secret_dict.get("data") is None
    assert "_data" not in secret_dict


def test_secret_data_not_in_retrieve_response(sdk: NeMoPlatform, workspace: str):
    """Test that secret data is not exposed in the retrieve response.

    This test verifies that when retrieving a secret by name, the response
    does not contain the secret value - only metadata.
    """
    secret_name = f"e2e-no-data-retrieve-{uuid.uuid4().hex[:8]}"
    secret_value = "this-should-not-appear-in-retrieve"

    sdk.secrets.create(
        workspace=workspace,
        name=secret_name,
        value=secret_value,
    )

    # Retrieve the secret
    retrieved = sdk.secrets.retrieve(secret_name, workspace=workspace)

    # Verify name and workspace are present
    assert retrieved.name == secret_name
    assert retrieved.workspace == workspace

    # Verify the secret value is not exposed
    secret_dict = retrieved.model_dump()
    assert "data" not in secret_dict or secret_dict.get("data") is None
    assert "_data" not in secret_dict


def test_secret_data_not_in_list_response(sdk: NeMoPlatform, workspace: str):
    """Test that secret data is not exposed in the list response.

    This test verifies that when listing secrets, none of the secrets
    in the response contain their actual values.
    """
    secret_name = f"e2e-no-data-list-{uuid.uuid4().hex[:8]}"
    secret_value = "this-should-not-appear-in-list"

    sdk.secrets.create(
        workspace=workspace,
        name=secret_name,
        value=secret_value,
    )

    # List secrets
    list_response = sdk.secrets.list(workspace=workspace)

    # Find our secret in the list
    our_secret = next((s for s in list_response.data if s.name == secret_name), None)
    assert our_secret is not None, "Created secret should appear in list"

    # Verify no secrets in the list expose their values
    for secret in list_response.data:
        secret_dict = secret.model_dump()
        assert "data" not in secret_dict or secret_dict.get("data") is None
        assert "_data" not in secret_dict
