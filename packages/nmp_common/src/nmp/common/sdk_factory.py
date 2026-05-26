# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backward-compat re-exports — canonical home is nemo_platform_plugin.sdk_factory.

Service-side callers may keep importing from this module. New code (especially
plugins) should import directly from nemo_platform_plugin.sdk_factory to avoid
pulling nmp-common's server-side deps.
"""

from nemo_platform_plugin.sdk_factory import (
    _test_http_client as _test_http_client,
)
from nemo_platform_plugin.sdk_factory import (
    get_async_platform_sdk as get_async_platform_sdk,
)
from nemo_platform_plugin.sdk_factory import (
    get_entity_parts as get_entity_parts,
)
from nemo_platform_plugin.sdk_factory import (
    get_platform_sdk as get_platform_sdk,
)
from nemo_platform_plugin.sdk_factory import (
    get_request_scoped_sdk as get_request_scoped_sdk,
)
from nemo_platform_plugin.sdk_factory import (
    get_sdk_on_behalf_of as get_sdk_on_behalf_of,
)
from nemo_platform_plugin.sdk_factory import (
    get_task_sdk as get_task_sdk,
)
