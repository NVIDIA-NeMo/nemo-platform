# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility shim — the environment boundary was promoted to the Evaluator SDK.

The generic boundary now lives in
``nemo_evaluator_sdk.agent_eval.runtimes.environment``. The only platform-specific
piece kept here is the default task→image mapping (``nmp-nat-<id>:latest``): the
adapter's :class:`DockerEnvironmentProvider` injects :func:`task_image_tag` so
``DockerEnvironmentProvider()`` keeps producing platform-tagged images.
"""

from __future__ import annotations

from collections.abc import Callable

from nemo_evaluator_sdk.agent_eval.runtimes.environment import (
    AbstractEnvironmentHandle,
    AgentEnvironmentHandle,
    AgentEnvironmentProvider,
    DockerEnvironmentHandle,
    EnvCommandResult,
    EnvRole,
    EnvRunSpec,
    default_image_tag,
)
from nemo_evaluator_sdk.agent_eval.runtimes.environment import (
    DockerEnvironmentProvider as _SDKDockerEnvironmentProvider,
)

from runtimes.shared.layout import task_image_tag

__all__ = [
    "AbstractEnvironmentHandle",
    "AgentEnvironmentHandle",
    "AgentEnvironmentProvider",
    "DockerEnvironmentHandle",
    "DockerEnvironmentProvider",
    "EnvCommandResult",
    "EnvRole",
    "EnvRunSpec",
    "default_image_tag",
]


class DockerEnvironmentProvider(_SDKDockerEnvironmentProvider):
    """Platform default: map ``task.id`` to ``nmp-nat-<id>:latest``."""

    def __init__(self, *, image_tag_fn: Callable[[str], str] = task_image_tag) -> None:
        super().__init__(image_tag_fn=image_tag_fn)
