# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin-safe auth dependencies.

Holds the request-scoped ``auth_client_context`` ContextVar and the two
header helpers that the sdk_factory needs. ``AuthClient`` itself stays in
nmp.common.auth.client (server-side) — the ContextVar value is treated as
any object exposing a ``.principal`` attribute, so plugins don't import the
heavy client class.
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional

# Server-side middleware sets this. Plugins read it but don't construct
# the AuthClient — so we type the slot as ``Any`` to avoid importing the
# heavy client class here.
auth_client_context: ContextVar[Optional[Any]] = ContextVar("auth_client_context", default=None)


def get_principal_auth_headers() -> Dict[str, str]:
    """Return principal headers from the current auth context, or empty dict."""
    auth_client = auth_client_context.get()
    if auth_client is not None and getattr(auth_client, "principal", None) is not None:
        return auth_client.principal.get_headers()
    return {}


def build_service_principal_headers(service_name: str) -> Dict[str, str]:
    """Build outbound service-to-service headers.

    Emits ``X-NMP-Principal-Id: service:<service_name>`` and, when the current
    request principal is a non-service user, also forwards on-behalf-of fields
    so downstream PDP checks see the acting user (not the elevated service row).
    """
    headers: Dict[str, str] = {"X-NMP-Principal-Id": f"service:{service_name}"}

    auth_client = auth_client_context.get()
    if auth_client is None:
        return headers
    principal = getattr(auth_client, "principal", None)
    if principal is None or not principal.id:
        return headers

    effective = principal.effective_principal
    if effective.id.startswith("service:"):
        return headers

    headers["X-NMP-Principal-On-Behalf-Of"] = effective.id
    if effective.email:
        headers["X-NMP-Principal-On-Behalf-Of-Email"] = effective.email
    if effective.groups:
        headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(effective.groups)

    return headers
