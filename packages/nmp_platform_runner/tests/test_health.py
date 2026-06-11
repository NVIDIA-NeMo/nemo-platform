# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nmp.platform_runner.health import get_platform_health_endpoint_paths


def test_get_platform_health_endpoint_paths():
    assert get_platform_health_endpoint_paths() == (
        "/cluster-info",
        "/health/live",
        "/health/ready",
        "/plugins",
        "/status",
    )
