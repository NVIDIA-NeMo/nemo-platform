# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backward-compat re-exports — canonical home is nemo_platform_plugin.http_clients."""

from nemo_platform_plugin.http_clients import (
    close_shared_http_clients as close_shared_http_clients,
)
from nemo_platform_plugin.http_clients import (
    shared_async_http_client as shared_async_http_client,
)
from nemo_platform_plugin.http_clients import (
    shared_sync_http_client as shared_sync_http_client,
)
