# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Secrets API schemas.

The request/response contract lives in ``nemo_platform_plugin.secrets.types`` —
the shared single source of truth imported by both the server (here) and the
typed ``SecretsClient``. This module re-exports those models and adds the
server-only ``from_entity`` conversion helpers.
"""

from __future__ import annotations

from nemo_platform_plugin.secrets.types import (
    PlatformSecretAccessResponse as PlatformSecretAccessResponse,
)
from nemo_platform_plugin.secrets.types import (
    PlatformSecretCreateRequest as PlatformSecretCreateRequest,
)
from nemo_platform_plugin.secrets.types import (
    PlatformSecretResponse as _PlatformSecretResponse,
)
from nemo_platform_plugin.secrets.types import (
    PlatformSecretUpdateRequest as PlatformSecretUpdateRequest,
)
from nmp.core.secrets.entities import PlatformSecret


class PlatformSecretResponse(_PlatformSecretResponse):
    """Server-side response model — adds entity conversion."""

    @classmethod
    def from_entity(cls, secret: PlatformSecret) -> PlatformSecretResponse:
        """Create a PlatformSecretResponse from a PlatformSecret entity."""
        return cls(
            name=secret.name,
            workspace=secret.workspace,
            description=secret.description,
            created_at=secret.created_at,
            updated_at=secret.updated_at,
        )
