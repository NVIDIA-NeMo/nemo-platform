# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import httpx
import pytest
from nemo_platform_plugin.auth.access_keys.client import AccessKeyIssuerClient, AccessKeysClient
from nemo_platform_plugin.auth.access_keys.issuer import (
    AccessKeyFeatureDisabledError,
    AccessKeyOperationNotImplementedError,
)
from nemo_platform_plugin.auth.access_keys.types import AccessKeyCreateRequest, AccessKeyCreateResponse
from nemo_platform_plugin.client.errors import NemoHTTPError


class _AccessKeysClientStub:
    def __init__(self) -> None:
        self.create_access_key = MagicMock()
        self.list_access_keys = MagicMock()
        self.revoke_access_key = MagicMock()

    def as_client(self) -> AccessKeysClient:
        return cast(AccessKeysClient, self)


def test_access_key_issuer_client_delegates_create_to_client() -> None:
    created = AccessKeyCreateResponse(
        jti="ak_example",
        name=None,
        token="signed.jwt.token",
        token_type="Bearer",
        principal="alice@example.com",
        created_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
        expires_at=None,
    )
    client = _AccessKeysClientStub()
    client.create_access_key.return_value.data.return_value = created

    issuer = AccessKeyIssuerClient(client.as_client())
    result = issuer.create(AccessKeyCreateRequest())

    assert result == created
    client.create_access_key.assert_called_once_with(body=AccessKeyCreateRequest())


def test_access_key_issuer_client_revokes_by_jti() -> None:
    client = _AccessKeysClientStub()
    client.revoke_access_key.return_value.data.return_value = None

    issuer = AccessKeyIssuerClient(client.as_client())
    issuer.revoke("ak_example")

    client.revoke_access_key.assert_called_once_with(jti="ak_example")


def test_access_key_issuer_client_translates_http_501_to_domain_error() -> None:
    response = httpx.Response(
        501,
        json={"detail": "Scoped Access Key listing is not implemented."},
        request=httpx.Request("GET", "https://cluster.example.com/apis/auth/v2/access-keys"),
    )
    client = _AccessKeysClientStub()
    client.list_access_keys.side_effect = NemoHTTPError(response)

    issuer = AccessKeyIssuerClient(client.as_client())

    with pytest.raises(AccessKeyOperationNotImplementedError, match="not implemented"):
        issuer.list()


def test_access_key_issuer_client_translates_disabled_feature_to_domain_error() -> None:
    response = httpx.Response(
        404,
        json={"detail": "Scoped Access Keys are not enabled"},
        request=httpx.Request("POST", "https://cluster.example.com/apis/auth/v2/access-keys"),
    )
    client = _AccessKeysClientStub()
    client.create_access_key.side_effect = NemoHTTPError(response)

    issuer = AccessKeyIssuerClient(client.as_client())

    with pytest.raises(AccessKeyFeatureDisabledError, match="not enabled"):
        issuer.create(AccessKeyCreateRequest())
