# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.auth_idp.conftest import _token_request_body
from tests.auth_idp.providers import load_provider_configs

pytestmark = [pytest.mark.auth_idp]


def test_authentik_provider_config_loads_token_acquisition_fields():
    provider = next(config for config in load_provider_configs() if config.name == "authentik")

    assert provider.token_endpoint == "http://127.0.0.1:18080/application/o/token/"
    assert provider.human_grant["grant_type"] == "password"
    assert provider.machine_grant["grant_type"] == "password"
    assert provider.workload_audience == "nemo-platform"
    assert provider.workload_principal_claim == "sub"
    assert provider.workload_groups_claim == "groups"
    assert provider.workload_groups_format == "comma_string"
    assert provider.workload_token_env_vars == ["NEMO_WORKLOAD_TOKEN", "NEMO_WORKLOAD_TOKEN_FILE"]
    assert provider.startup_timeouts == {
        "healthchecks_seconds": 600,
        "gateway_seconds": 30,
        "token_endpoint_seconds": 180,
    }


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
            "username": "svc-nemo-ci",
            "password": "svc-nemo-ci-token-secret-dev",
            "scope": "openid email groups",
        }
    ) == {
        "grant_type": "password",
        "client_id": "nemo-platform",
        "client_secret": "secret",
        "username": "svc-nemo-ci",
        "password": "svc-nemo-ci-token-secret-dev",
        "scope": "openid email groups",
    }
