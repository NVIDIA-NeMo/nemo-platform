# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Iterator
from dataclasses import replace
from urllib.parse import urlparse

import httpx
import pytest
import yaml

from tests.auth_idp.providers import ProviderConfig, load_provider_matrix
from tests.auth_idp.runtime import get_authentik_docker_test_runtime

pytest_plugins = ("e2e.conftest",)


def _token_request_body(grant: dict[str, str]) -> dict[str, str]:
    grant_type = grant["grant_type"]
    body = {
        "grant_type": grant_type,
        "client_id": grant["client_id"],
        "client_secret": grant["client_secret"],
    }
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


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "idp_provider" in metafunc.fixturenames:
        providers = load_provider_matrix()
        metafunc.parametrize("idp_provider", providers, ids=[provider.name for provider in providers])


@pytest.fixture
def gateway_base_url(idp_provider: ProviderConfig) -> str:
    return idp_provider.gateway_base_url


@pytest.fixture
def provider_machine_groups(idp_provider: ProviderConfig) -> list[str]:
    return idp_provider.machine_expected_groups


@pytest.fixture
def provider_machine_principal(idp_provider: ProviderConfig) -> str:
    return idp_provider.machine_principal_id


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
    e2e_sidecars: dict[str, dict[str, str]],
) -> ProviderConfig:
    sidecar = e2e_sidecars["authentik"]
    return replace(
        authentik_provider,
        gateway_base_url=sidecar["gateway_base_url"],
        discovery_url=sidecar["discovery_url"],
        token_endpoint=sidecar["token_endpoint"],
    )


@pytest.fixture(scope="module")
def machine_token(authentik_stack: ProviderConfig) -> str:
    grant = authentik_stack.machine_grant
    assert grant is not None
    issuer = yaml.safe_load(authentik_stack.nemo_config.read_text())["auth"]["oidc"]["issuer"]
    issuer_host = urlparse(issuer).netloc
    response = httpx.post(
        authentik_stack.token_endpoint,
        data=_token_request_body(grant),
        headers={"Host": issuer_host},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def machine_sdk(sdk, machine_token: str):
    return sdk.with_options(set_default_headers={"Authorization": f"Bearer {machine_token}"})
