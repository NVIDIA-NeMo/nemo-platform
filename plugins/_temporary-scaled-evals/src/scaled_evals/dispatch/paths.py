# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Neutral filesystem mapping helpers shared by runtime backends."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


def setting_evaluation_dir(settings: Any, setting_name: str) -> Callable[[str], Path]:
    """Resolve ``<setting>/<evaluation-id>`` using the setting's current value."""

    def resolve(evaluation_id: str) -> Path:
        return Path(str(getattr(settings, setting_name))).expanduser() / evaluation_id

    return resolve


def resolve_host_path(path: str | Path, *, host_root: str | None) -> Path:
    """Resolve a host bind path, anchoring relative values to ``host_root``."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if host_root:
        return (Path(host_root).expanduser().resolve() / candidate).resolve()
    return candidate.resolve()


def container_harness_host_path(container_path: Path, *, host_root: str | None) -> Path:
    """Map ``/harness/...`` to ``<host_root>/examples/...`` when available."""
    if host_root and container_path.parts[:2] == ("/", "harness"):
        return (Path(host_root).expanduser().resolve() / Path("examples", *container_path.parts[2:])).resolve()
    return container_path.expanduser().resolve()


def resolve_host_env_file(
    container_env_file: Path,
    *,
    explicit_host_env_file: str | None,
    host_root: str | None,
) -> Path:
    """Resolve an explicit host env file or generically map its container path."""
    if explicit_host_env_file:
        return resolve_host_path(explicit_host_env_file, host_root=host_root)
    return container_harness_host_path(container_env_file, host_root=host_root)
