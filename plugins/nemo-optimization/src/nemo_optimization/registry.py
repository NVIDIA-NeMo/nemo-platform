# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tune backend discovery."""

from __future__ import annotations

import importlib.metadata
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nemo_optimization.backends.protocol import OptimizationBackend

OPTIMIZATION_BACKENDS_GROUP = "nemo.optimization.backends"


class OptimizationBackendDiscoveryError(RuntimeError):
    """Raised when Tune backend discovery fails."""


@cache
def discover_optimization_backends() -> dict[str, OptimizationBackend]:
    from nemo_optimization.backends.protocol import OptimizationBackend

    backends: dict[str, OptimizationBackend] = {}
    for entry in importlib.metadata.entry_points(group=OPTIMIZATION_BACKENDS_GROUP):
        try:
            backend_cls = entry.load()
        except Exception as exc:  # pragma: no cover - defensive
            raise OptimizationBackendDiscoveryError(f"Failed to load optimization backend {entry.name!r}") from exc
        if not isinstance(backend_cls, type):
            backend = backend_cls
        else:
            backend = backend_cls()
        if not isinstance(backend, OptimizationBackend):
            raise OptimizationBackendDiscoveryError(
                f"Optimization backend {entry.name!r} must implement OptimizationBackend"
            )
        backends[entry.name] = backend
    return backends
