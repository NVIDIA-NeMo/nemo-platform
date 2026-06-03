# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customization SDK hub — composes contributor backends under ``client.customization``."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.discovery import discover_customization_contributors
from nemo_platform_plugin.sdk import NemoPluginSDKResources

logger = logging.getLogger(__name__)

# Contributor entry-point key → (module, sync class, async class)
_CONTRIBUTOR_SDK: dict[str, tuple[str, str, str]] = {
    "automodel": (
        "nemo_automodel_plugin.sdk.resources",
        "AutomodelCustomization",
        "AsyncAutomodelCustomization",
    ),
    "unsloth": (
        "nemo_unsloth_plugin.sdk.resources",
        "UnslothCustomization",
        "AsyncUnslothCustomization",
    ),
}


def _load_contributor_sdk_class(module_path: str, class_name: str) -> type[Any]:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class Customization:
    """Sync SDK namespace mounted as ``client.customization``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        contributors = discover_customization_contributors()
        for key, (module_path, sync_cls, _async_cls) in _CONTRIBUTOR_SDK.items():
            if key not in contributors:
                continue
            try:
                cls = _load_contributor_sdk_class(module_path, sync_cls)
                setattr(self, key, cls(platform))
            except ImportError:
                logger.warning(
                    "Customization contributor %r is installed but SDK module %s is missing",
                    key,
                    module_path,
                )


class AsyncCustomization:
    """Async SDK namespace mounted as ``client.customization``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        contributors = discover_customization_contributors()
        for key, (module_path, _sync_cls, async_cls) in _CONTRIBUTOR_SDK.items():
            if key not in contributors:
                continue
            try:
                cls = _load_contributor_sdk_class(module_path, async_cls)
                setattr(self, key, cls(platform))
            except ImportError:
                logger.warning(
                    "Customization contributor %r is installed but SDK module %s is missing",
                    key,
                    module_path,
                )


customization_sdk_resources = NemoPluginSDKResources(
    sync_resource=Customization,
    async_resource=AsyncCustomization,
)
