# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Every backend-native failure must arrive as a type a Harbor caller can handle."""

import httpx
import pytest
import respx
from harbor.publisher.errors import (
    PublishAuthError,
    PublishBackendError,
    PublishError,
    PublishPermissionError,
)
from harbor_nemo.client import NemoClient, NotFound

from conftest import TASKS_URL


@respx.mock
async def test_401_becomes_an_auth_error(client: NemoClient):
    respx.get(TASKS_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(PublishAuthError, match="NMP_TOKEN"):
        await client.get_json(TASKS_URL)


@respx.mock
async def test_403_becomes_a_permission_error(client: NemoClient):
    respx.get(TASKS_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(PublishPermissionError, match="permission"):
        await client.get_json(TASKS_URL)


@respx.mock
async def test_404_becomes_not_found_not_a_publish_error(client: NemoClient):
    """`NotFound` is deliberately not a PublishError: only read paths turn it into the
    ValueError that `package_type` keys on, and a publish must not silently treat it as one."""
    respx.get(TASKS_URL).mock(return_value=httpx.Response(404, json={"detail": "nope"}))
    with pytest.raises(NotFound):
        await client.get_json(TASKS_URL)


@respx.mock
async def test_500_carries_the_platforms_own_message(client: NemoClient):
    respx.get(TASKS_URL).mock(return_value=httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(PublishBackendError, match="boom") as exc_info:
        await client.get_json(TASKS_URL)
    assert exc_info.value.message == "boom"


@respx.mock
async def test_a_transport_failure_is_never_reported_as_not_found(client: NemoClient):
    """The failure mode this whole module exists to prevent: a platform that is down being
    reported to the user as a package that does not exist."""
    respx.get(TASKS_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(PublishBackendError, match="Could not reach"):
        await client.get_json(TASKS_URL)


@respx.mock
async def test_a_non_json_error_body_still_produces_a_message(client: NemoClient):
    respx.get(TASKS_URL).mock(return_value=httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(PublishBackendError, match="bad gateway"):
        await client.get_json(TASKS_URL)


def test_permission_error_remains_catchable_as_the_builtin():
    """Harbor's retry predicate classifies the builtin PermissionError as non-retryable."""
    assert issubclass(PublishPermissionError, PermissionError)
    assert issubclass(PublishAuthError, PublishError)
