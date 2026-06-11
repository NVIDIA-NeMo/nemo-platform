# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customization SDK hub — composes contributor backends under ``client.customization``."""

from __future__ import annotations

import logging

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.customization_contributor import CustomizationContributor
from nemo_platform_plugin.discovery import discover_customization_contributors
from nemo_platform_plugin.sdk import NemoPluginSDKResources

logger = logging.getLogger(__name__)


def _mount_contributor_sdk_resources(
    target: object,
    platform: NeMoPlatform | AsyncNeMoPlatform,
    contributors: dict[str, CustomizationContributor],
    *,
    async_: bool,
) -> None:
    for key in sorted(contributors.keys()):
        contributor = contributors[key]
        sdk_resources = contributor.get_sdk_resources()
        if sdk_resources is None:
            continue
        resource_cls = sdk_resources.async_resource if async_ else sdk_resources.sync_resource
        if resource_cls is None:
            continue
        try:
            setattr(target, key, resource_cls(platform))
        except ImportError:
            logger.warning(
                "Customization contributor %r is installed but SDK resources are unavailable",
                key,
            )


class Customization:
    """Sync SDK namespace mounted as ``client.customization``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        contributors = discover_customization_contributors()
        _mount_contributor_sdk_resources(self, platform, contributors, async_=False)


class AsyncCustomization:
    """Async SDK namespace mounted as ``client.customization``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        contributors = discover_customization_contributors()
        _mount_contributor_sdk_resources(self, platform, contributors, async_=True)


customization_sdk_resources = NemoPluginSDKResources(
    sync_resource=Customization,
    async_resource=AsyncCustomization,
)
