# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The evaluator plugin's authz scope.

The service and the metrics route module import :data:`SCOPE` so the plugin shares one
``AuthzScope("evaluator")``.
"""

from __future__ import annotations

from nemo_platform_plugin.authz import AuthzScope

SCOPE = AuthzScope("evaluator")
