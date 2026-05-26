# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Image helper utilities for plugins.

Builds qualified Docker image names from the platform config. Lives here
(in nemo-platform-plugin) instead of nmp-common so plugins don't need to
pull in nmp-common's server-side deps (sqlalchemy, k8s, hvac, prometheus,
OTEL SDK) just to resolve a registry/tag pair.
"""

from nemo_platform_plugin.config import Configuration, NemoPlatformConfig


def get_qualified_image(name: str, tag: str | None = None, registry: str | None = None) -> str:
    """Build a fully qualified Docker image name (``{registry}/{name}:{tag}``).

    Reads the platform's ``image_registry`` and ``image_tag`` defaults from
    :class:`NemoPlatformConfig` unless explicit overrides are supplied.
    """
    config = Configuration.get_service_config(NemoPlatformConfig)
    effective_registry = registry if registry is not None else config.image_registry
    effective_tag = tag if tag is not None else config.image_tag
    return f"{effective_registry}/{name}:{effective_tag}"


def image_builder(registry: str | None = None, tag: str | None = None):
    """Return a function that builds qualified image names with preset registry/tag."""
    config = Configuration.get_service_config(NemoPlatformConfig)
    effective_registry = registry if registry is not None else config.image_registry
    effective_tag = tag if tag is not None else config.image_tag

    def _build(name: str) -> str:
        return f"{effective_registry}/{name}:{effective_tag}"

    return _build
