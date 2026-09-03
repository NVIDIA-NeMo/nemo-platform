# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Selection of the configured episode backend."""

from sandboxed_gym.backends.base import EpisodeSandboxBackend
from sandboxed_gym.backends.memory import InMemoryEpisodeBackend
from sandboxed_gym.config import EpisodeBrokerConfig
from sandboxed_gym.egress import build_egress_policy


def build_backend(config: EpisodeBrokerConfig) -> EpisodeSandboxBackend:
    """Instantiate the episode backend named by ``config``.

    The egress policy is built exactly once, here, and handed to the backend. Every consumer --
    the create path, the audit record -- reads it back off the backend rather than rebuilding it,
    because construction is not deterministic: it reads ``/etc/resolv.conf`` and resolves names at
    call time.

    Args:
        config: Broker configuration.

    Returns:
        A backend satisfying :class:`EpisodeSandboxBackend`.

    Raises:
        ValueError: If the in-memory backend is selected without the explicit insecure opt-in, or
            the backend name is unknown.
    """
    egress = build_egress_policy(config.egress_allowlist)

    if config.backend == "memory":
        if not config.allow_insecure_memory_backend:
            raise ValueError(
                "Episode backend 'memory' provisions no real sandbox and applies no isolation. "
                "Set allow_insecure_memory_backend=true to use it in development or tests."
            )
        return InMemoryEpisodeBackend(egress)

    if config.backend == "opensandbox":
        from sandboxed_gym.backends.opensandbox import (
            OpenSandboxEpisodeBackend,
        )

        return OpenSandboxEpisodeBackend(
            egress=egress,
            verification=config.egress_verification,
            **config.backend_options,
        )

    raise ValueError(f"Unknown episode backend: {config.backend!r}")
