# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trusted episode broker + sandboxed Gym host orchestrator.

Ray wrappers live under :mod:`sandboxed_gym.ray` (optional extra). The HTTP
surface, sanitizer, backends, and orchestrator are importable without Ray.

**Exports resolve lazily.** Importing any submodule runs this file, so eagerly re-exporting the
orchestrator and HTTP app made ``import sandboxed_gym.wire`` -- 270 lines of Pydantic with no
server dependencies -- pull in FastAPI, Starlette, anyio and orjson. A client that speaks the
broker's wire contract without running a broker should pay for Pydantic and nothing else. Names
are therefore mapped to their defining module here and imported on first attribute access, which
:pep:`562` resolves for both ``sandboxed_gym.X`` and ``from sandboxed_gym import X``.

Keep :data:`_LAZY_EXPORTS` and the ``TYPE_CHECKING`` block below in step with each other; the test
suite asserts they agree with ``__all__``, since a name missing from either resolves at runtime and
fails type checking, or the reverse.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    # Static-only: gives type checkers and IDEs the real symbols, which a module-level
    # ``__getattr__`` alone cannot provide -- every export would otherwise widen to ``Any``.
    # These bind no names at runtime, which is the point.
    from sandboxed_gym.backends.base import (
        EpisodeSandboxBackend,
        SanitizedEpisodeSpec,
        UnsupportedEpisodeOperationError,
    )
    from sandboxed_gym.broker import EpisodeBrokerServer
    from sandboxed_gym.config import (
        BrokerEndpoint,
        EpisodeBrokerConfig,
    )
    from sandboxed_gym.egress import (
        DEFAULT_PUBLIC_DNS_SUFFIXES,
        EgressAllowlist,
        EgressPolicy,
        EgressRule,
        build_egress_policy,
        denied_cidrs,
        local_resolver_addresses,
    )
    from sandboxed_gym.errors import BrokerRequestError
    from sandboxed_gym.host.models import (
        GymHostEgressRule,
        GymHostHandle,
        GymHostSpec,
        GymHostVolumeMount,
        NemoGymSandboxedConfig,
        SandboxConfig,
    )
    from sandboxed_gym.http_app import (
        begin_shutdown,
        build_broker_app,
        close_all_episodes,
    )
    from sandboxed_gym.orchestrator import (
        SandboxedGymOrchestrator,
        SandboxedGymSession,
        apply_sandbox_runtime_defaults,
    )
    from sandboxed_gym.sanitize import (
        sanitize_create_request,
        sanitize_exec_request,
    )
    from sandboxed_gym.serve_config import (
        SandboxedGymServeConfig,
        SandboxedGymSessionDescriptor,
    )

#: Exported name -> module that defines it. The single source of truth for lazy resolution.
_LAZY_EXPORTS: Final[dict[str, str]] = {
    "EpisodeSandboxBackend": "sandboxed_gym.backends.base",
    "SanitizedEpisodeSpec": "sandboxed_gym.backends.base",
    "UnsupportedEpisodeOperationError": "sandboxed_gym.backends.base",
    "EpisodeBrokerServer": "sandboxed_gym.broker",
    "BrokerEndpoint": "sandboxed_gym.config",
    "EpisodeBrokerConfig": "sandboxed_gym.config",
    "DEFAULT_PUBLIC_DNS_SUFFIXES": "sandboxed_gym.egress",
    "EgressAllowlist": "sandboxed_gym.egress",
    "EgressPolicy": "sandboxed_gym.egress",
    "EgressRule": "sandboxed_gym.egress",
    "build_egress_policy": "sandboxed_gym.egress",
    "denied_cidrs": "sandboxed_gym.egress",
    "local_resolver_addresses": "sandboxed_gym.egress",
    "BrokerRequestError": "sandboxed_gym.errors",
    "GymHostEgressRule": "sandboxed_gym.host.models",
    "GymHostHandle": "sandboxed_gym.host.models",
    "GymHostSpec": "sandboxed_gym.host.models",
    "GymHostVolumeMount": "sandboxed_gym.host.models",
    "NemoGymSandboxedConfig": "sandboxed_gym.host.models",
    "SandboxConfig": "sandboxed_gym.host.models",
    "begin_shutdown": "sandboxed_gym.http_app",
    "build_broker_app": "sandboxed_gym.http_app",
    "close_all_episodes": "sandboxed_gym.http_app",
    "SandboxedGymOrchestrator": "sandboxed_gym.orchestrator",
    "SandboxedGymSession": "sandboxed_gym.orchestrator",
    "apply_sandbox_runtime_defaults": "sandboxed_gym.orchestrator",
    "sanitize_create_request": "sandboxed_gym.sanitize",
    "sanitize_exec_request": "sandboxed_gym.sanitize",
    "SandboxedGymServeConfig": "sandboxed_gym.serve_config",
    "SandboxedGymSessionDescriptor": "sandboxed_gym.serve_config",
}


def __getattr__(name: str) -> Any:
    """Import and return an export on first access (:pep:`562`).

    The resolved object is cached in module globals, so later lookups bypass this function
    entirely rather than re-entering ``import_module`` on every attribute access.
    """
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose the lazy exports to ``dir()`` and tab-completion, which do not trigger ``__getattr__``."""
    return sorted(__all__)


__all__ = [
    "BrokerEndpoint",
    "BrokerRequestError",
    "DEFAULT_PUBLIC_DNS_SUFFIXES",
    "EgressAllowlist",
    "EgressPolicy",
    "EgressRule",
    "EpisodeBrokerConfig",
    "EpisodeBrokerServer",
    "EpisodeSandboxBackend",
    "GymHostEgressRule",
    "GymHostHandle",
    "GymHostSpec",
    "GymHostVolumeMount",
    "NemoGymSandboxedConfig",
    "SandboxConfig",
    "SandboxedGymOrchestrator",
    "SandboxedGymServeConfig",
    "SandboxedGymSession",
    "SandboxedGymSessionDescriptor",
    "SanitizedEpisodeSpec",
    "UnsupportedEpisodeOperationError",
    "apply_sandbox_runtime_defaults",
    "begin_shutdown",
    "build_broker_app",
    "build_egress_policy",
    "close_all_episodes",
    "denied_cidrs",
    "local_resolver_addresses",
    "sanitize_create_request",
    "sanitize_exec_request",
]
