# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_platform_plugin import AsyncNemoClient, NemoClient, client_from_platform
from nemo_platform_plugin.client.adapter import client_from_platform as adapter_client_from_platform
from nemo_platform_plugin.client.client import AsyncNemoClient as ClientAsyncNemoClient
from nemo_platform_plugin.client.client import NemoClient as ClientNemoClient


def test_client_exports_are_available_from_package_root() -> None:
    assert NemoClient is ClientNemoClient
    assert AsyncNemoClient is ClientAsyncNemoClient
    assert client_from_platform is adapter_client_from_platform
