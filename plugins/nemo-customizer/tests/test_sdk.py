# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

from nemo_automodel_plugin.sdk.resources import AutomodelCustomization
from nemo_customizer.sdk.resources import (
    AsyncCustomization,
    Customization,
    customization_sdk_resources,
)
from nemo_platform_plugin.customization_contributor import CustomizationContributorSDKResources
from nemo_platform_plugin.sdk import NemoPluginSDKResources


class _AutomodelContributorStub:
    def get_sdk_resources(self) -> CustomizationContributorSDKResources:
        return CustomizationContributorSDKResources(sync_resource=AutomodelCustomization)


class _ContributorWithoutSdk:
    def get_sdk_resources(self) -> None:
        return None


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

    with patch(
        "nemo_customizer.sdk.resources.discover_customization_contributors",
        return_value={"automodel": _AutomodelContributorStub()},
    ):
        customization = Customization(platform)

    assert hasattr(customization, "automodel")
    assert hasattr(customization.automodel, "jobs")


def test_customization_skips_contributors_without_sdk() -> None:
    platform = MagicMock()
    platform._client = MagicMock()
    platform.workspace = "default"
    platform.base_url = "http://localhost:8000"
    platform.default_headers = {}

    with patch(
        "nemo_customizer.sdk.resources.discover_customization_contributors",
        return_value={"noop": _ContributorWithoutSdk()},
    ):
        customization = Customization(platform)

    assert not hasattr(customization, "noop")
