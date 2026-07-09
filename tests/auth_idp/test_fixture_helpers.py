# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for auth-idp pytest fixtures and fixture-only helper functions."""

from pathlib import Path

import pytest

from tests.auth_idp import conftest
from tests.auth_idp.conftest import _token_request_body
from tests.auth_idp.providers import ProviderConfig
from tests.auth_idp.xdist import append_xdist_group_suffix

pytestmark = [pytest.mark.auth_idp]


def test_authentik_stack_fixture_uses_pooled_gateway_metadata():
    provider = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=Path("docker-compose.yml"),
        gateway_base_url="http://127.0.0.1:18080",
        issuer_url="http://authentik-server:9000/application/o/nemo/",
        discovery_url="http://127.0.0.1:18080/application/o/nemo/.well-known/openid-configuration",
        token_endpoint="http://127.0.0.1:18080/application/o/token/",
        nemo_config=Path("config/platform-compose-authentik.yaml"),
        workload_principal_id="svc-nemo",
        workload_expected_groups=["nemo-editors"],
        workload_audience="nemo-platform",
        workload_principal_claim="sub",
        workload_groups_claim="groups",
        workload_groups_format="comma_string",
        workload_token_env_vars=["NEMO_WORKLOAD_TOKEN", "NEMO_WORKLOAD_TOKEN_FILE"],
        workload_forwarded_headers={
            "principal_id": "X-NMP-Principal-Id",
            "principal_groups": "X-NMP-Principal-Groups",
        },
        human_grant={"grant_type": "password"},
        machine_grant={"grant_type": "password", "username": "svc-nemo", "password": "svc-nemo-token-secret-dev"},
        healthchecks=[],
        startup_timeouts={},
    )
    fixture_fn = conftest.authentik_stack.__wrapped__
    stack = fixture_fn(None, provider, "http://127.0.0.1:28080")

    assert stack.gateway_base_url == "http://127.0.0.1:28080"
    assert stack.discovery_url == "http://127.0.0.1:28080/application/o/nemo/.well-known/openid-configuration"
    assert stack.token_endpoint == "http://127.0.0.1:28080/application/o/token/"
    assert stack.nemo_config == provider.nemo_config


def test_token_request_body_for_password_grant_includes_username_and_password():
    assert _token_request_body(
        {
            "grant_type": "password",
            "client_id": "nemo-platform",
            "client_secret": "secret",
            "username": "akadmin",
            "password": "akadmin-dev",
            "scope": "openid profile email groups",
        }
    ) == {
        "grant_type": "password",
        "client_id": "nemo-platform",
        "client_secret": "secret",
        "username": "akadmin",
        "password": "akadmin-dev",
        "scope": "openid profile email groups",
    }


def test_token_request_body_for_workload_password_grant_includes_username_and_password():
    assert _token_request_body(
        {
            "grant_type": "password",
            "client_id": "nemo-platform",
            "client_secret": "secret",
            "username": "svc-nemo",
            "password": "svc-nemo-token-secret-dev",
            "scope": "openid email groups",
        }
    ) == {
        "grant_type": "password",
        "client_id": "nemo-platform",
        "client_secret": "secret",
        "username": "svc-nemo",
        "password": "svc-nemo-token-secret-dev",
        "scope": "openid email groups",
    }


def test_append_xdist_group_suffix_only_appends_once_and_sorts_groups():
    nodeid = "tests/auth_idp/test_authentik_real_oidc.py::test_authentik_machine_token_is_real"
    assert append_xdist_group_suffix(nodeid, {"idp-live"}) == f"{nodeid}@idp-live"
    assert append_xdist_group_suffix(nodeid, {"b", "a"}) == f"{nodeid}@a_b"
    assert append_xdist_group_suffix(f"{nodeid}@idp-live", {"idp-live"}) == f"{nodeid}@idp-live"
