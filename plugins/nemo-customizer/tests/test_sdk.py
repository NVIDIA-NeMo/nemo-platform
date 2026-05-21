# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

from nemo_customizer.sdk.resources import (
    AsyncCustomization,
    Customization,
    customization_sdk_resources,
)
from nemo_platform_plugin.sdk import NemoPluginSDKResources


def test_customization_sdk_resources_entry_point_shape() -> None:
    assert isinstance(customization_sdk_resources, NemoPluginSDKResources)
    assert customization_sdk_resources.sync_resource is Customization
    assert customization_sdk_resources.async_resource is AsyncCustomization


def test_customization_composes_automodel_when_contributor_present() -> None:
    platform = MagicMock()
    platform._client = MagicMock()
    platform.workspace = "default"
    platform.base_url = "http://localhost:8000"
    platform.default_headers = {}

    fake_contributor = object()
    with patch(
        "nemo_customizer.sdk.resources.discover_customization_contributors",
        return_value={"automodel": fake_contributor},
    ):
        customization = Customization(platform)

    assert hasattr(customization, "automodel")
    assert hasattr(customization.automodel, "jobs")
