# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Auth-proxy sidecar compilation.

A DeploymentConfig with ``auth_proxy_sidecar=True`` gets a loopback auth-proxy
sidecar injected: the nmp-api image running ``nemo services run --sidecars
auth-proxy``, which stamps ``X-NMP-Principal-Id: service:<identity>`` on the
workload's platform calls. The workload targets the proxy on localhost.

Injection is a no-op when platform auth is disabled — the workload's calls are
already trusted on the internal network, so no identity header is needed.
"""

from __future__ import annotations

import logging

from nemo_deployments_plugin.config import DeploymentsConfig
from nemo_deployments_plugin.entities import (
    Container,
    DeploymentConfig,
    EnvVar,
    ExecAction,
    Probe,
    RestartPolicy,
)
from nemo_platform_plugin.auth import platform_auth_enabled
from nemo_platform_plugin.config import get_nemo_config
from nemo_platform_plugin.jobs.image import get_qualified_image

logger = logging.getLogger(__name__)

AUTH_PROXY_CONTAINER_NAME = "auth-proxy"
_NATIVE_SIDECAR_RESTART_POLICY: RestartPolicy = "Always"
_AUTH_PROXY_PRINCIPAL_ENVVAR = "NMP_AUTH_PROXY_PRINCIPAL"
_AUTH_PROXY_HOST_ENVVAR = "NMP_AUTH_PROXY_HOST"
_AUTH_PROXY_PORT_ENVVAR = "NMP_AUTH_PROXY_PORT"
_DEFAULT_IDENTITY = "agents"


def auth_proxy_port() -> int:
    """Return the loopback port the auth-proxy sidecar listens on."""
    return get_nemo_config(DeploymentsConfig).auth_proxy_port


def _upstream_base_url() -> str:
    from nemo_platform_plugin.config import get_platform_config

    return get_platform_config().base_url.rstrip("/")


def build_auth_proxy_container(config: DeploymentConfig) -> Container | None:
    """Return the auth-proxy sidecar Container for *config*, or None.

    Returns None when the config does not request the sidecar, or when platform
    auth is disabled (the sidecar would be pointless — internal calls are already
    trusted).
    """
    if not config.auth_proxy_sidecar:
        return None
    if not platform_auth_enabled():
        logger.debug("auth_proxy_sidecar requested but platform auth is disabled; skipping sidecar injection")
        return None

    deployments_config = get_nemo_config(DeploymentsConfig)
    identity = config.auth_proxy_sidecar_identity or _DEFAULT_IDENTITY
    port = deployments_config.auth_proxy_port
    image = deployments_config.auth_proxy_image or get_qualified_image(deployments_config.auth_proxy_image_name)

    return Container(
        name=AUTH_PROXY_CONTAINER_NAME,
        image=image,
        command=["nemo", "services", "run", "--sidecars", "auth-proxy"],
        env=[
            EnvVar(name="NMP_BASE_URL", value=_upstream_base_url()),
            EnvVar(name=_AUTH_PROXY_PRINCIPAL_ENVVAR, value=identity),
            EnvVar(name=_AUTH_PROXY_HOST_ENVVAR, value="127.0.0.1"),
            EnvVar(name=_AUTH_PROXY_PORT_ENVVAR, value=str(port)),
        ],
    ).model_copy(
        update={
            "restart_policy": _NATIVE_SIDECAR_RESTART_POLICY,
            # The proxy binds loopback only, so a pod-IP httpGet probe would be
            # refused; exec-probe curls localhost inside the container netns.
            "readiness_probe": Probe(
                exec=ExecAction(command=["sh", "-c", f"curl -sf http://127.0.0.1:{port}/healthz"]),
                initialDelaySeconds=1,
                periodSeconds=5,
                failureThreshold=12,
            ),
        }
    )
