# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customization SDK hub — composes contributor backends under ``client.customization``."""

from __future__ import annotations

import logging

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.customization_contributor import CustomizationContributor
from nemo_platform_plugin.discovery import discover_customization_contributors
from nemo_platform_plugin.sdk import NemoPluginSDKResources
from nmp.customization_common.sdk.client import platform_default_headers, url

logger = logging.getLogger(__name__)

_HEALTHZ_PATH = "v2/healthz"


def _coerce_health_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError("customization health response must be a JSON object.")
    return {str(key): value for key, value in payload.items()}


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
        self._platform = platform
        contributors = discover_customization_contributors()
        _mount_contributor_sdk_resources(self, platform, contributors, async_=False)

    def plugin_status(self) -> dict[str, object]:
        """Return customization router health, including the registered contributors."""
        response = self._platform._client.get(
            url(self._platform, _HEALTHZ_PATH),
            headers=platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return _coerce_health_payload(response.json())


class AsyncCustomization:
    """Async SDK namespace mounted as ``client.customization``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        contributors = discover_customization_contributors()
        _mount_contributor_sdk_resources(self, platform, contributors, async_=True)

    async def plugin_status(self) -> dict[str, object]:
        """Return customization router health, including the registered contributors."""
        response = await self._platform._client.get(
            url(self._platform, _HEALTHZ_PATH),
            headers=platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return _coerce_health_payload(response.json())


customization_sdk_resources = NemoPluginSDKResources(
    sync_resource=Customization,
    async_resource=AsyncCustomization,
)
