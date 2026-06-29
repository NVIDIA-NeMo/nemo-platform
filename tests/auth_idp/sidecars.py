# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
from pathlib import Path
from typing import Any, Protocol

import pytest

from tests.auth_idp.compose import (
    compose_down,
    compose_published_port,
    compose_up,
    wait_for_gateway_listener,
    wait_for_healthchecks,
)
from tests.auth_idp.runtime import (
    authentik_runtime_compose_env,
    authentik_runtime_compose_files,
    configure_authentik_gateway_upstream,
    finalize_authentik_runtime_bundle,
    render_authentik_runtime_bundle,
)


class SupportsAuthentikSidecar(Protocol):
    url: str
    docker_network_name: str | None
    docker_container_alias: str | None
    docker_container_port: int | None


def start_authentik_sidecar(
    sidecar_config: dict[str, str],
    services: SupportsAuthentikSidecar,
    config_hash: str,
    runtime_root: Path,
) -> Any:
    if not isinstance(sidecar_config, dict):
        raise pytest.UsageError("e2e_sidecars.authentik must be a mapping")
    if sidecar_config.get("provider") != "authentik":
        raise pytest.UsageError(f"unsupported e2e sidecar provider: {sidecar_config.get('provider')}")

    runtime = render_authentik_runtime_bundle(
        runtime_root=runtime_root / f"authentik-{config_hash}",
        gateway_host_port=None,
        issuer_host_port=None,
        compose_project_name=f"authentik-e2e-{config_hash}",
    )
    compose_files = authentik_runtime_compose_files(runtime.compose_file.parent)
    compose_env = authentik_runtime_compose_env(None, None)
    if (
        services.docker_network_name is not None
        and services.docker_container_alias is not None
        and services.docker_container_port is not None
    ):
        configure_authentik_gateway_upstream(
            runtime.compose_file.parent,
            upstream_host=services.docker_container_alias,
            upstream_port=services.docker_container_port,
            external_network_name=services.docker_network_name,
        )
    else:
        raise pytest.UsageError(
            "authentik e2e sidecar requires Docker-backed services metadata "
            "(docker_network_name, docker_container_alias, docker_container_port)"
        )
    try:
        compose_down(compose_files, project_name=runtime.compose_project_name, env=compose_env)
    except subprocess.CalledProcessError:
        pass
    compose_up(
        compose_files,
        project_name=runtime.compose_project_name,
        wait_timeout=max(
            int(runtime.startup_timeouts["healthchecks_seconds"]),
            int(runtime.startup_timeouts["token_endpoint_seconds"]),
        ),
        env=compose_env,
    )
    runtime = finalize_authentik_runtime_bundle(
        runtime.compose_file.parent,
        gateway_host_port=compose_published_port(
            compose_files, "gateway", 8080, project_name=runtime.compose_project_name, env=compose_env
        ),
        issuer_host_port=compose_published_port(
            compose_files,
            "authentik-server",
            9000,
            project_name=runtime.compose_project_name,
            env=compose_env,
        ),
        compose_project_name=runtime.compose_project_name or f"authentik-e2e-{config_hash}",
    )
    wait_for_healthchecks(runtime, timeout=float(runtime.startup_timeouts["healthchecks_seconds"]))
    wait_for_gateway_listener(runtime.gateway_base_url, timeout=float(runtime.startup_timeouts["gateway_seconds"]))

    from e2e.services_pool import RunningSidecar

    return RunningSidecar(
        name="authentik",
        metadata={
            "gateway_base_url": runtime.gateway_base_url,
            "discovery_url": runtime.discovery_url,
            "token_endpoint": runtime.token_endpoint,
        },
        close=lambda: compose_down(compose_files, project_name=runtime.compose_project_name, env=compose_env),
    )
