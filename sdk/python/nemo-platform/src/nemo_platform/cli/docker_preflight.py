# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Config-aware Docker preflight for local platform startup (NVBug 6537617).

Fails fast before spawn/wait when the resolved run would start the deployments
service/controller with a docker-backed ``default_executor`` while the daemon is
unreachable. Does not treat Docker as a global platform dependency — kubernetes and
reduced selections that never hit that fail-close path are left alone.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import typer
import yaml
from nemo_platform_plugin.capabilities import probe_docker
from nmp.platform_runner.config import PlatformAppConfig, default_config_path, resolve_run_configuration
from rich.console import Console

DOCKER_PREFLIGHT_MESSAGE = (
    "Docker is required for this default local setup (deployments default_executor "
    "uses the docker backend) but the Docker daemon is not available. "
    "Install and start Docker, or use a kubernetes / non-docker config "
    "(and omit the deployments service if you do not need it), then retry."
)


def _load_platform_yaml(config_path: str) -> dict[str, Any]:
    """Load platform YAML without running Pydantic validators (no soft-downgrade)."""
    path = Path(config_path)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _intended_runtime_is_kubernetes(raw: dict[str, Any]) -> bool:
    platform = raw.get("platform")
    if not isinstance(platform, dict):
        return False
    runtime = platform.get("runtime")
    return isinstance(runtime, str) and runtime.strip().lower() == "kubernetes"


def _default_executor_backend_is_docker(raw: dict[str, Any]) -> bool:
    """Resolve deployments.default_executor → executors[].backend without string-matching names."""
    deployments = raw.get("deployments")
    if not isinstance(deployments, dict):
        return False
    default_name = deployments.get("default_executor")
    if not isinstance(default_name, str) or not default_name:
        return False
    executors = deployments.get("executors")
    if not isinstance(executors, list):
        return False
    for spec in executors:
        if not isinstance(spec, dict):
            continue
        if spec.get("name") != default_name:
            continue
        backend = spec.get("backend")
        return isinstance(backend, str) and backend.strip().lower() == "docker"
    return False


def default_local_needs_docker(
    platform_config: PlatformAppConfig | None = None,
    *,
    config_path: str | None = None,
) -> bool:
    """Return whether this run would fail closed on a missing Docker daemon."""
    app_config = platform_config or PlatformAppConfig()
    if config_path is not None:
        app_config = replace(app_config, config_path=config_path)

    try:
        resolved = resolve_run_configuration(app_config)
    except ValueError:
        # Invalid selections fail elsewhere; do not block on Docker here.
        return False

    starts_deployments = "deployments" in resolved.services or "deployments" in resolved.controllers
    if not starts_deployments:
        return False

    raw = _load_platform_yaml(resolved.config_path or default_config_path())
    if _intended_runtime_is_kubernetes(raw):
        return False
    return _default_executor_backend_is_docker(raw)


def require_docker_for_default_local(
    platform_config: PlatformAppConfig | None = None,
    *,
    config_path: str | None = None,
    console: Console | None = None,
) -> None:
    """Exit with a clear message when default-local Docker is required but missing."""
    if not default_local_needs_docker(platform_config, config_path=config_path):
        return
    if probe_docker(use_cache=False).available:
        return
    out = console or Console(stderr=True)
    out.print(f"[red]✗[/red] {DOCKER_PREFLIGHT_MESSAGE}")
    raise typer.Exit(1)


__all__ = [
    "DOCKER_PREFLIGHT_MESSAGE",
    "default_local_needs_docker",
    "require_docker_for_default_local",
]
