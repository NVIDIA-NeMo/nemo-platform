# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies for the deployments plugin API."""

from __future__ import annotations

from fastapi import HTTPException, Request
from nemo_platform_plugin.entity_client import get_entity_client

__all__ = ["get_entity_client", "require_service_principal"]

_PRINCIPAL_ID_HEADER = "X-NMP-Principal-Id"
_ON_BEHALF_OF_HEADER = "X-NMP-Principal-On-Behalf-Of"


def _effective_principal_id(request: Request) -> str:
    return request.headers.get(_ON_BEHALF_OF_HEADER) or request.headers.get(_PRINCIPAL_ID_HEADER, "")


def require_service_principal(request: Request) -> None:
    """Restrict controller-only status writes to service principals."""
    if not _effective_principal_id(request).startswith("service:"):
        raise HTTPException(
            status_code=403,
            detail="Status updates require a service principal.",
        )
