# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public NeMo Platform plugin contract."""

from typing import TYPE_CHECKING

from nemo_platform_plugin.client.client import AsyncNemoClient as AsyncNemoClient
from nemo_platform_plugin.client.client import NemoClient as NemoClient

if TYPE_CHECKING:
    from nemo_platform_plugin.client.adapter import client_from_platform as client_from_platform

__all__ = ["AsyncNemoClient", "NemoClient", "client_from_platform"]


def __getattr__(name: str) -> object:
    if name == "client_from_platform":
        from nemo_platform_plugin.client.adapter import client_from_platform

        return client_from_platform
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
