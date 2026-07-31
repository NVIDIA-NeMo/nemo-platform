# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest
from nmp.common.auth.dependencies import parse_service_principal_bearer_token
from nmp.core.models.controllers.backends.deployments_plugin.runtime_auth import files_service_bearer_token


def test_runtime_token_preserves_original_user_and_origin() -> None:
    deployment = SimpleNamespace(
        workspace="destination",
        auth_context=SimpleNamespace(
            principal_id="creator@example.com",
            principal_email="creator@example.com",
            principal_groups=["exporters"],
            principal_on_behalf_of=None,
            principal_on_behalf_of_email=None,
            principal_on_behalf_of_groups=None,
            origin_workspace="destination",
        ),
    )

    token = files_service_bearer_token(deployment, "source")

    headers = parse_service_principal_bearer_token(token, expected_source_workspace="source")
    assert headers is not None
    assert headers["x-nmp-principal-id"] == "service:models"
    assert headers["x-nmp-principal-on-behalf-of"] == "creator@example.com"
    assert "x-nmp-principal-on-behalf-of-groups" not in headers
    assert headers["x-nmp-origin-workspace"] == "destination"


def test_runtime_without_auth_context_fails_closed() -> None:
    deployment = SimpleNamespace(workspace="destination", auth_context=None)

    with pytest.raises(ValueError, match="require a deployment auth context"):
        files_service_bearer_token(deployment, "source")


def test_same_workspace_runtime_without_auth_context_fails_closed() -> None:
    deployment = SimpleNamespace(workspace="source", auth_context=None)

    with pytest.raises(ValueError, match="require a deployment auth context"):
        files_service_bearer_token(deployment, "source")
