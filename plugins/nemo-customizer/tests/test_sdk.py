# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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


def _health_platform() -> MagicMock:
    platform = MagicMock()
    platform.workspace = "default"
    platform.base_url = "http://localhost:8000"
    platform.default_headers = {}
    return platform


def test_plugin_status_hits_versioned_hub_healthz() -> None:
    platform = _health_platform()
    response = MagicMock()
    response.json.return_value = {"plugin": "customization", "status": "ok", "contributors": ["automodel"]}
    platform._client.get.return_value = response

    with patch(
        "nemo_customizer.sdk.resources.discover_customization_contributors",
        return_value={},
    ):
        status = Customization(platform).plugin_status()

    called_url = platform._client.get.call_args.args[0]
    assert called_url == "http://localhost:8000/apis/customization/v2/healthz"
    assert status["contributors"] == ["automodel"]


def test_plugin_status_rejects_non_object_payload() -> None:
    platform = _health_platform()
    response = MagicMock()
    response.json.return_value = ["not", "an", "object"]
    platform._client.get.return_value = response

    with patch(
        "nemo_customizer.sdk.resources.discover_customization_contributors",
        return_value={},
    ):
        resource = Customization(platform)
    with pytest.raises(TypeError):
        resource.plugin_status()


async def test_async_plugin_status_hits_versioned_hub_healthz() -> None:
    platform = _health_platform()
    response = MagicMock()
    response.json.return_value = {"plugin": "customization", "status": "ok", "contributors": []}
    platform._client.get = AsyncMock(return_value=response)

    with patch(
        "nemo_customizer.sdk.resources.discover_customization_contributors",
        return_value={},
    ):
        status = await AsyncCustomization(platform).plugin_status()

    called_url = platform._client.get.call_args.args[0]
    assert called_url == "http://localhost:8000/apis/customization/v2/healthz"
    assert status["status"] == "ok"
