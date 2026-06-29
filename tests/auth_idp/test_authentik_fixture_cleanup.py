# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from tests.auth_idp import conftest
from tests.auth_idp.providers import ProviderConfig


def test_authentik_stack_uses_pooled_sidecar_metadata():
    provider = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=Path("docker-compose.yml"),
        gateway_base_url="http://127.0.0.1:18080",
        issuer_url="http://127.0.0.1:19000/application/o/nemo/",
        discovery_url="http://127.0.0.1:19000/application/o/nemo/.well-known/openid-configuration",
        token_endpoint="http://127.0.0.1:19000/application/o/token/",
        nemo_config=Path("config/nemo-auth.yaml"),
        machine_principal_id="svc-nemo-ci",
        machine_expected_groups=["nemo-editors"],
        human_grant={"grant_type": "password"},
        machine_grant={"grant_type": "client_credentials"},
        healthchecks=[],
        startup_timeouts={},
    )
    sidecars = {
        "authentik": {
            "gateway_base_url": "http://127.0.0.1:28080",
            "discovery_url": "http://127.0.0.1:29000/application/o/nemo/.well-known/openid-configuration",
            "token_endpoint": "http://127.0.0.1:29000/application/o/token/",
        }
    }

    fixture_fn = conftest.authentik_stack.__wrapped__
    stack = fixture_fn(None, provider, sidecars)

    assert stack.gateway_base_url == sidecars["authentik"]["gateway_base_url"]
    assert stack.discovery_url == sidecars["authentik"]["discovery_url"]
    assert stack.token_endpoint == sidecars["authentik"]["token_endpoint"]
    assert stack.nemo_config == provider.nemo_config
