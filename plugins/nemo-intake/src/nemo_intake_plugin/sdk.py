# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin-owned Intake SDK resources."""

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.sdk import NemoPluginSDKResources

from nemo_intake_plugin.client.client import AsyncIntakeClient, IntakeClient


def _sync_resource(platform: NeMoPlatform) -> IntakeClient:
    return client_from_platform(platform, IntakeClient)


def _async_resource(platform: AsyncNeMoPlatform) -> AsyncIntakeClient:
    return client_from_platform(platform, AsyncIntakeClient)


intake_sdk_resources = NemoPluginSDKResources(
    sync_resource=_sync_resource,
    async_resource=_async_resource,
)
