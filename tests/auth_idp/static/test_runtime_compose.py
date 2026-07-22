# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
from pathlib import Path

import httpx

from tests.auth_idp.providers import ProviderConfig
from tests.auth_idp.runtime_compose import (
    ACCESS_TOKEN_TYPE,
    JWT_TOKEN_TYPE,
    TOKEN_EXCHANGE_GRANT_TYPE,
    TOKEN_EXCHANGE_TIMEOUT_SECONDS,
    ComposeAuthIdpRuntime,
)
from tests.auth_idp.runtime_contract import AuthIdpCase


def _jwt(claims: dict[str, object]) -> str:
    def encode(value: dict[str, object]) -> str:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode(claims)}."


def test_compose_workload_exchange_posts_token_exchange_grant(monkeypatch) -> None:
    provider = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=None,
        gateway_base_url="https://127.0.0.1:18080",
        issuer_url="http://authentik-server:9000/application/o/nemo/",
        discovery_url="https://127.0.0.1:18080/application/o/nemo/.well-known/openid-configuration",
        nemo_config=Path("config.yaml"),
        interactive_user_username="nemo-user",
        interactive_user_password="nemo-user-password-dev",
        interactive_user_expected_email="nemo-user@example.com",
        workload_principal_id="svc-nemo",
        workload_expected_groups=["nemo-workloads"],
        workload_audience="nemo-platform",
        workload_principal_claim="sub",
        workload_groups_claim="groups",
        workload_groups_format="comma_string",
        workload_token_env_vars=["NMP_WORKLOAD_IDENTITY_TOKEN_FILE"],
        workload_forwarded_headers={},
        token_endpoint="https://127.0.0.1:18080/application/o/token/",
        e2e_setup_password_grant={
            "grant_type": "password",
            "client_id": "nemo-platform",
            "username": "nemo-setup",
            "password": "nemo-setup-token-secret-dev",
            "scope": "openid email groups",
        },
        interactive_user_password_grant=None,
        workload_provider_password_grant={
            "grant_type": "password",
            "client_id": "nemo-platform-workload",
            "username": "svc-nemo",
            "password": "secret",
            "scope": "openid email groups",
        },
        healthchecks=[],
        startup_timeouts={},
    )
    case = AuthIdpCase(
        id="authentik-compose",
        provider=provider,
        backend="compose",
        capabilities=frozenset({"workload_token_exchange"}),
    )
    runtime = ComposeAuthIdpRuntime(case, "https://127.0.0.1:18080")
    subject_token = _jwt({"sub": "svc-nemo"})
    exchanged_token = _jwt({"sub": "svc-nemo", "groups": "nemo-workloads"})
    captured: dict[str, object] = {}

    def fake_post(url: str, *, data: dict[str, str], timeout: float, verify: str | bool) -> httpx.Response:
        captured.update({"url": url, "data": data, "timeout": timeout, "verify": verify})
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"access_token": exchanged_token, "token_type": "Bearer"}, request=request)

    monkeypatch.setenv("NMP_CLIENT_SSL_CERT_FILE", "/tmp/nemo-ca.pem")
    monkeypatch.setattr("tests.auth_idp.runtime_compose.httpx.post", fake_post)

    token = runtime.exchange_workload_token(subject_token)

    assert token.access_token == exchanged_token
    assert token.claims == {"sub": "svc-nemo", "groups": "nemo-workloads"}
    assert captured == {
        "url": "https://127.0.0.1:18080/apis/auth/token",
        "data": {
            "grant_type": TOKEN_EXCHANGE_GRANT_TYPE,
            "client_id": "nemo-platform-workload",
            "subject_token": subject_token,
            "subject_token_type": JWT_TOKEN_TYPE,
            "requested_token_type": ACCESS_TOKEN_TYPE,
            "audience": "nemo-platform",
            "scope": "openid email groups",
        },
        "timeout": TOKEN_EXCHANGE_TIMEOUT_SECONDS,
        "verify": "/tmp/nemo-ca.pem",
    }
