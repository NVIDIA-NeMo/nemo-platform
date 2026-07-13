# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import time
import uuid
from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest
from nemo_platform import NeMoPlatform

from tests.auth_idp.providers import ProviderConfig
from tests.auth_idp.runtime import get_authentik_docker_test_runtime

pytest_plugins = ("e2e.conftest",)


def _token_request_body(grant: dict[str, str]) -> dict[str, str]:
    grant_type = grant["grant_type"]
    body = {
        "grant_type": grant_type,
        "client_id": grant["client_id"],
    }
    if "client_secret" in grant:
        body["client_secret"] = grant["client_secret"]
    if grant_type == "password":
        body["username"] = grant["username"]
        body["password"] = grant["password"]
        if "scope" in grant:
            body["scope"] = grant["scope"]
        return body
    if grant_type == "client_credentials":
        if "scope" in grant:
            body["scope"] = grant["scope"]
        return body
    raise ValueError(f"unsupported grant_type for auth_idp token exchange: {grant_type}")


def _exchange_token_with_retries(token_endpoint: str, grant: dict[str, str], timeout: float = 60.0) -> str:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.post(
                token_endpoint,
                data=_token_request_body(grant),
                timeout=30.0,
            )
            if response.status_code >= 500:
                last_error = httpx.HTTPStatusError(
                    f"token endpoint not ready: {response.status_code}",
                    request=response.request,
                    response=response,
                )
                time.sleep(2)
                continue
            response.raise_for_status()
            return response.json()["access_token"]
        except httpx.RequestError as exc:
            last_error = exc
            time.sleep(2)
    if last_error is not None:
        raise last_error
    raise TimeoutError(f"token endpoint did not become ready: {token_endpoint}")


@pytest.fixture(scope="session")
def idp_e2e_enabled(pytestconfig: pytest.Config) -> bool:
    return bool(pytestconfig.getoption("--run-e2e"))


@pytest.fixture(scope="session")
def require_idp_e2e(idp_e2e_enabled: bool) -> Iterator[None]:
    if not idp_e2e_enabled:
        pytest.skip("set --run-e2e to execute provider stack validation")
    yield


@pytest.fixture(scope="module")
def authentik_provider(authentik_docker_runtime: ProviderConfig) -> ProviderConfig:
    provider = authentik_docker_runtime
    assert provider.token_endpoint is not None
    assert provider.machine_grant is not None
    return provider


@pytest.fixture(scope="session")
def authentik_docker_runtime() -> ProviderConfig:
    provider = get_authentik_docker_test_runtime()
    assert provider.token_endpoint is not None
    assert provider.machine_grant is not None
    return provider


@pytest.fixture(scope="module")
def authentik_stack(
    require_idp_e2e: None,
    authentik_provider: ProviderConfig,
    _services: str,
) -> ProviderConfig:
    return replace(
        authentik_provider,
        gateway_base_url=_services,
        discovery_url=f"{_services}/application/o/nemo/.well-known/openid-configuration",
        token_endpoint=f"{_services}/application/o/token/",
    )


@pytest.fixture(scope="module")
def machine_token(authentik_stack: ProviderConfig) -> str:
    grant = authentik_stack.machine_grant
    assert grant is not None
    assert authentik_stack.token_endpoint is not None
    return _exchange_token_with_retries(authentik_stack.token_endpoint, grant)


@pytest.fixture(scope="module")
def human_token(authentik_stack: ProviderConfig) -> str:
    grant = authentik_stack.human_grant
    assert grant is not None
    assert authentik_stack.token_endpoint is not None
    return _exchange_token_with_retries(authentik_stack.token_endpoint, grant)


@pytest.fixture(scope="module")
def authentik_human_sdk(authentik_stack: ProviderConfig, human_token: str) -> NeMoPlatform:
    return NeMoPlatform(
        base_url=authentik_stack.gateway_base_url,
        default_headers={"Authorization": f"Bearer {human_token}"},
        max_retries=0,
    )


@pytest.fixture(scope="module")
def machine_sdk(authentik_stack: ProviderConfig, machine_token: str) -> NeMoPlatform:
    return NeMoPlatform(
        base_url=authentik_stack.gateway_base_url,
        default_headers={"Authorization": f"Bearer {machine_token}"},
        max_retries=0,
    )


@pytest.fixture
def authentik_workspace(authentik_human_sdk: NeMoPlatform) -> Iterator[str]:
    workspace_name = f"authentik-ws-{uuid.uuid4().hex[:8]}"
    authentik_human_sdk.workspaces.create(
        name=workspace_name,
        description="Workspace for Authentik live auth tests",
        wait_role_propagation=True,
    )
    try:
        yield workspace_name
    finally:
        authentik_human_sdk.workspaces.delete(workspace_name)
