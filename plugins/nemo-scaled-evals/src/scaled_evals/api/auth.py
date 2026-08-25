# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The ownership identity every ``/v1`` route resolves a caller through.

This is deliberately only a seam. The standalone service authenticated callers
itself: OIDC discovery against a fixed internal issuer, JWKS fetching and JWT
signature validation, an OAuth client-credentials exchange, API-key
introspection, and a proxy-header trust path — all populating
``request.state.principal`` from a middleware.

None of that belongs in a platform plugin. The platform authenticates the request
before a plugin route runs, so a second identity provider inside the plugin would
be both redundant and a competing source of truth. The verification stack is
gone; what remains is the ownership model the repositories filter on
(``owner_id``) plus one function that produces it.

Until platform identity is bridged into that model, every caller resolves to a
single development principal. That is why ``/v1`` data is not multi-tenant yet:
callers share one owner, so they share one view of tasks and evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from scaled_evals.api.settings import settings


@dataclass(frozen=True)
class CurrentPrincipal:
    """Who a request acts as, for ownership and attribution.

    ``owner_id`` is the only field the repositories filter on. The rest is
    attribution that ``GET /users/me`` echoes and ``record_principal`` stores.
    """

    owner_type: str
    owner_id: str
    # Load-bearing, not descriptive: seven call sites treat "disabled" as
    # "skip owner filtering" so single-owner development can still reach rows
    # written before ownership existed (owner_id IS NULL). Renaming this string
    # silently hides those rows.
    source: str = "disabled"
    email: str | None = None
    username: str | None = None
    display_name: str | None = None
    groups: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()


def current_principal(request: Request) -> CurrentPrincipal:
    """Resolve the caller's ownership identity.

    Nothing populates ``request.state.principal`` today. This reads it anyway so
    that bridging platform identity becomes a matter of setting it upstream
    rather than editing every route.

    Raises:
        HTTPException: 401 when ``CONTROL_PLANE_AUTH_ENABLED`` is set. Failing is
            the honest answer: there is no identity provider left to consult, so
            attributing the request to the shared development owner would hand
            one caller another caller's data.
    """
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, CurrentPrincipal):
        return principal
    if settings.control_plane_auth_enabled:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "principal_unavailable",
                    "message": (
                        "control-plane auth is enabled but no identity provider is wired; "
                        "platform identity is not yet bridged into scaled-evals ownership"
                    ),
                }
            },
        )
    return CurrentPrincipal(owner_type="DEV", owner_id="dev", source="disabled")
