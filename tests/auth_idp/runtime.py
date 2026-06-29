# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import uuid
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import yaml

from tests.auth_idp.providers import ProviderConfig, load_provider_config

_AUTHENTIK_ROOT = Path("contrib/auth/authentik")
_RUNTIME_ROOT = Path(".tmp/e2e/auth-idp-runtimes")
_AUTHENTIK_COMPOSE_NEMO_CONFIG = _AUTHENTIK_ROOT / "config" / "platform-compose-authentik.yaml"
_AUTHENTIK_BASE_COMPOSE = _AUTHENTIK_ROOT / "docker-compose.yml"
_AUTHENTIK_OVERRIDE_COMPOSE = "docker-compose.override.yml"


def _set_external_default_network(compose_path: Path, external_network_name: str | None) -> None:
    if external_network_name is None:
        return

    compose = yaml.safe_load(compose_path.read_text())
    compose["networks"] = {
        "default": {
            "name": external_network_name,
            "external": True,
        }
    }
    compose_path.write_text(yaml.safe_dump(compose, sort_keys=False))


def authentik_runtime_compose_files(runtime_root: Path) -> tuple[Path, Path]:
    return (_AUTHENTIK_BASE_COMPOSE, runtime_root / _AUTHENTIK_OVERRIDE_COMPOSE)


def configure_authentik_gateway_upstream(
    runtime_root: Path,
    *,
    upstream_host: str,
    upstream_port: int,
    external_network_name: str | None = None,
) -> None:
    envoy_path = runtime_root / "gateway" / "envoy.yaml"
    envoy = yaml.safe_load(envoy_path.read_text())
    socket_address = envoy["static_resources"]["clusters"][0]["load_assignment"]["endpoints"][0]["lb_endpoints"][0][
        "endpoint"
    ]["address"]["socket_address"]
    socket_address["address"] = upstream_host
    socket_address["port_value"] = upstream_port
    router_filter = envoy["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0]["typed_config"][
        "http_filters"
    ][0]
    router_filter["typed_config"] = {"@type": "type.googleapis.com/envoy.extensions.filters.http.router.v3.Router"}
    envoy_path.write_text(yaml.safe_dump(envoy, sort_keys=False))
    _set_external_default_network(runtime_root / _AUTHENTIK_OVERRIDE_COMPOSE, external_network_name)


def authentik_runtime_compose_env(gateway_host_port: int | None, issuer_host_port: int | None) -> dict[str, str]:
    return {
        "AUTHENTIK_GATEWAY_PORT": str(gateway_host_port or 0),
        "AUTHENTIK_ISSUER_PORT": str(issuer_host_port or 0),
    }


def _write_runtime_provider_files(
    runtime_root: Path,
    *,
    gateway_host_port: int,
    issuer_host_port: int,
    nemo_auth_issuer_url: str | None = None,
) -> None:
    manifest = yaml.safe_load((_AUTHENTIK_ROOT / "manifest.yaml").read_text())
    manifest["gateway_base_url"] = f"http://127.0.0.1:{gateway_host_port}"
    manifest["issuer_url"] = f"http://127.0.0.1:{issuer_host_port}/application/o/nemo/"
    manifest["discovery_url"] = (
        f"http://127.0.0.1:{issuer_host_port}/application/o/nemo/.well-known/openid-configuration"
    )
    manifest["token_acquisition"]["token_endpoint"] = f"http://127.0.0.1:{issuer_host_port}/application/o/token/"
    manifest["healthchecks"][0]["url"] = manifest["discovery_url"]
    (runtime_root / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))

    nemo_auth = yaml.safe_load((_AUTHENTIK_ROOT / "config" / "nemo-auth.yaml").read_text())
    nemo_auth["auth"]["oidc"]["issuer"] = nemo_auth_issuer_url or manifest["issuer_url"]
    (runtime_root / "config" / "nemo-auth.yaml").write_text(yaml.safe_dump(nemo_auth, sort_keys=False))


def finalize_authentik_runtime_bundle(
    runtime_root: Path,
    *,
    gateway_host_port: int,
    issuer_host_port: int,
    compose_project_name: str,
    nemo_auth_issuer_url: str | None = None,
) -> ProviderConfig:
    _write_runtime_provider_files(
        runtime_root,
        gateway_host_port=gateway_host_port,
        issuer_host_port=issuer_host_port,
        nemo_auth_issuer_url=nemo_auth_issuer_url,
    )
    runtime_provider = load_provider_config(runtime_root / "manifest.yaml")
    return replace(
        runtime_provider,
        compose_file=runtime_root / _AUTHENTIK_OVERRIDE_COMPOSE,
        compose_project_name=compose_project_name,
    )


def render_authentik_runtime_bundle(
    runtime_root: Path,
    gateway_host_port: int | None,
    issuer_host_port: int | None,
    compose_project_name: str,
    nemo_auth_issuer_url: str | None = None,
) -> ProviderConfig:
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "gateway").mkdir(exist_ok=True)
    (runtime_root / "config").mkdir(exist_ok=True)

    (runtime_root / "gateway" / "envoy.yaml").write_text((_AUTHENTIK_ROOT / "gateway" / "envoy.yaml").read_text())
    override_compose = {
        "services": {
            "gateway": {
                "volumes": [f"{(runtime_root / 'gateway' / 'envoy.yaml').resolve()}:/etc/envoy/envoy.yaml:ro"],
            },
        }
    }
    (runtime_root / _AUTHENTIK_OVERRIDE_COMPOSE).write_text(yaml.safe_dump(override_compose, sort_keys=False))
    return finalize_authentik_runtime_bundle(
        runtime_root,
        gateway_host_port=gateway_host_port or 0,
        issuer_host_port=issuer_host_port or 0,
        compose_project_name=compose_project_name,
        nemo_auth_issuer_url=nemo_auth_issuer_url,
    )


@lru_cache(maxsize=1)
def get_authentik_test_runtime() -> ProviderConfig:
    runtime_root = _RUNTIME_ROOT / f"authentik-e2e-{uuid.uuid4().hex[:8]}"
    return render_authentik_runtime_bundle(
        runtime_root=runtime_root,
        gateway_host_port=None,
        issuer_host_port=None,
        compose_project_name=f"authentik-e2e-{uuid.uuid4().hex[:8]}",
    )


@lru_cache(maxsize=1)
def get_authentik_docker_test_runtime() -> ProviderConfig:
    provider = load_provider_config(_AUTHENTIK_ROOT / "manifest.yaml")
    return replace(
        provider,
        nemo_config=_AUTHENTIK_COMPOSE_NEMO_CONFIG,
        compose_project_name=f"authentik-e2e-{uuid.uuid4().hex[:8]}",
        compose_file=_AUTHENTIK_BASE_COMPOSE,
    )
