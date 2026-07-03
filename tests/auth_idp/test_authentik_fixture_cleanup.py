# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from tests.auth_idp import conftest
from tests.auth_idp.providers import ProviderConfig


def test_authentik_stack_uses_pooled_gateway_metadata():
    provider = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=Path("docker-compose.yml"),
        gateway_base_url="http://127.0.0.1:18080",
        issuer_url="http://authentik-server:9000/application/o/nemo/",
        discovery_url="http://127.0.0.1:18080/application/o/nemo/.well-known/openid-configuration",
        token_endpoint="http://127.0.0.1:18080/application/o/token/",
        nemo_config=Path("config/nemo-auth.yaml"),
        workload_principal_id="svc-nemo-ci",
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
        machine_grant={"grant_type": "password", "username": "svc-nemo-ci", "password": "svc-nemo-ci-token-secret-dev"},
        healthchecks=[],
        startup_timeouts={},
    )
    fixture_fn = conftest.authentik_stack.__wrapped__
    stack = fixture_fn(None, provider, "http://127.0.0.1:28080")

    assert stack.gateway_base_url == "http://127.0.0.1:28080"
    assert stack.discovery_url == "http://127.0.0.1:28080/application/o/nemo/.well-known/openid-configuration"
    assert stack.token_endpoint == "http://127.0.0.1:28080/application/o/token/"
    assert stack.nemo_config == provider.nemo_config
