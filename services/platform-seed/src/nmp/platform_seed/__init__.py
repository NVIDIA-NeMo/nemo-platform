# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Platform seeding for built-in and plugin-contributed seed jobs."""

from nmp.platform_seed.config import PlatformSeedConfig
from nmp.platform_seed.tasks.seed import (
    PlatformSeedResult,
    run_platform_seed,
    run_platform_seed_from_startup,
)

__all__ = [
    "PlatformSeedConfig",
    "PlatformSeedResult",
    "run_platform_seed",
    "run_platform_seed_from_startup",
]
