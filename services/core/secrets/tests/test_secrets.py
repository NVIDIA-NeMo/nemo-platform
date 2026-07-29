# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest


async def test_create_secret(test_client):
    secret_name = "test-secret"
    secret_value = "supersecret"

    response = test_client.post(
        "/apis/secrets/v2/workspaces/default/secrets",
        json={
            "name": secret_name,
            "value": secret_value,
        },
    )
    assert response.status_code == 201
    secret = response.json()
    assert secret["name"] == secret_name
    assert "data" not in secret  # Secret value should not be in the list response
    assert "value" not in secret  # Secret value should not be in the list response
    assert "_data" not in secret


async def test_create_and_list_secrets(test_client):
    secret_name_1 = "test-secret-1"
    secret_name_2 = "test-secret-2"
    test_client.post(
        "/apis/secrets/v2/workspaces/default/secrets",
        json={
            "name": secret_name_1,
            "value": "value1",
        },
    )
    test_client.post(
        "/apis/secrets/v2/workspaces/default/secrets",
        json={
            "name": secret_name_2,
            "value": "value2",
        },
    )

    response = test_client.get("/apis/secrets/v2/workspaces/default/secrets", params={"page": 1, "page_size": 10})
    assert response.status_code == 200
    secrets = response.json()
    secret_names = [secret["name"] for secret in secrets["data"]]
    assert secret_name_1 in secret_names
    assert secret_name_2 in secret_names
    for secret in secrets["data"]:
        assert "data" not in secret  # Secret value should not be in the list response
        assert "value" not in secret
        assert "_data" not in secret


async def test_create_secret_with_empty_value(test_client):
    secret_name = "test-secret-empty"
    response = test_client.post(
        "/apis/secrets/v2/workspaces/default/secrets",
        json={
            "name": secret_name,
            "value": "",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "invalid_name",
    ["bad name", "bad/name", "no!way", "MySecret", "1secret", "my--secret", "secret-", "a" * 64],
)
async def test_create_secret_with_invalid_name_is_rejected(test_client, invalid_name):
    """Names the entity store would reject must fail at the API boundary, not downstream."""
    response = test_client.post(
        "/apis/secrets/v2/workspaces/default/secrets",
        json={"name": invalid_name, "value": "x"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("valid_name", ["hf-token", "a@b", "model.v1", "svc_key", "ab"])
async def test_create_secret_accepts_entity_store_names(test_client, valid_name):
    response = test_client.post(
        "/apis/secrets/v2/workspaces/default/secrets",
        json={"name": valid_name, "value": "x"},
    )
    assert response.status_code == 201


async def test_create_and_delete_secret(test_client):
    secret_name = "test-secret-delete"
    secret_value = "deletesecret"
    create_response = test_client.post(
        "/apis/secrets/v2/workspaces/default/secrets",
        json={
            "name": secret_name,
            "value": secret_value,
        },
    )
    assert create_response.status_code == 201
    delete_response = test_client.delete(f"/apis/secrets/v2/workspaces/default/secrets/{secret_name}")
    assert delete_response.status_code == 204

    access_response = test_client.get(f"/apis/secrets/v2/workspaces/default/secrets/{secret_name}/access")
    assert access_response.status_code == 404
