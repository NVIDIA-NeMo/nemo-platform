# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the Auth service (v2)."""

from typing import Optional

from nmp.common.config import AuthConfig as SharedAuthConfig
from pydantic import Field


class AuthServiceConfig(SharedAuthConfig):
    """
    Configuration for the Auth Service.

    Extends the shared AuthConfig (which has enabled, policy_decision_point_base_url,
    policy_decision_point_provider) with auth-service-specific fields.

    Environment variables use the NMP_AUTH_ prefix.
    """

    port: int = Field(
        default=8000,
        description="Port to run the service on",
    )

    # Refresh interval for policy data (seconds) - only used when provider=embedded
    policy_data_refresh_interval: float = Field(
        default=30,
        description="Refresh interval for policy data in seconds",
    )

    bundle_cache_seconds: float = Field(
        default=5,
        description="Seconds to cache the OPA bundle",
    )

    # Platform admin bootstrap
    admin_email: Optional[str] = Field(
        default=None,
        description="Bootstrap admin email for platform setup",
    )

    # Default workspace for all-users Editor role
    default_workspace: str = Field(
        default="default",
        description="Name of the default workspace where all authenticated users get Editor role",
    )

    # Embedded PDP resource limits
    embedded_pdp_cpu_limit: int = Field(
        default=200,
        description="CPU budget for embedded PDP policy evaluation, in millions of WASM fuel units. "
        "Default of 200 provides headroom for full plugin-merged authorization data.",
    )
    embedded_pdp_memory_limit_mb: int = Field(
        default=32,
        description="Maximum linear memory (MB) the embedded PDP WASM runtime can consume.",
    )


# Backward compatibility alias
AuthConfig = AuthServiceConfig
