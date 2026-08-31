# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Auth helpers exposed to plugins.

Plugins must not import ``nmp_common`` directly. This module wraps the pieces of
the platform auth configuration that plugins need. The underlying auth config
lives in ``nmp_common`` (only present in the platform process image), so it is
imported lazily and failures degrade to "disabled" rather than raising in
environments without it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class AuthContext(BaseModel):
    """Auth context captured at resource creation for delegated access."""

    model_config = ConfigDict(from_attributes=True)

    principal_id: str = Field(..., description="The principal's unique identifier")
    principal_email: str | None = Field(default=None, description="The principal's email address")
    principal_groups: list[str] = Field(default_factory=list, description="Groups the principal belongs to")
    principal_on_behalf_of: str | None = Field(
        default=None, description="If acting on behalf of another principal, their principal ID"
    )
    principal_on_behalf_of_groups: list[str] | None = Field(
        default=None, description="Groups the on-behalf-of principal belongs to"
    )
    principal_on_behalf_of_email: str | None = Field(
        default=None, description="The on-behalf-of principal's email address"
    )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AuthContext):
            return super().__eq__(other)
        model_dump = getattr(other, "model_dump", None)
        if callable(model_dump):
            return self.model_dump(mode="python") == model_dump(mode="python")
        if isinstance(other, Mapping):
            return self.model_dump(mode="python") == dict(other)
        return False

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> "AuthContext | None":
        """Create an auth context from validated NeMo principal headers."""
        lower = {key.lower(): value for key, value in headers.items()}
        principal_id = lower.get("x-nmp-principal-id", "").strip()
        if not principal_id:
            return None
        on_behalf_of = lower.get("x-nmp-principal-on-behalf-of", "").strip() or None
        return cls(
            principal_id=principal_id,
            principal_email=lower.get("x-nmp-principal-email", "").strip() or None,
            principal_groups=_split_groups(lower.get("x-nmp-principal-groups")),
            principal_on_behalf_of=on_behalf_of,
            principal_on_behalf_of_groups=_split_groups(lower.get("x-nmp-principal-on-behalf-of-groups"))
            if on_behalf_of
            else None,
            principal_on_behalf_of_email=lower.get("x-nmp-principal-on-behalf-of-email", "").strip() or None
            if on_behalf_of
            else None,
        )

    @classmethod
    def from_principal(cls, principal: Any) -> Self:
        """Create from a runtime Principal-like object."""
        return cls(
            principal_id=principal.id,
            principal_email=principal.email,
            principal_groups=list(principal.groups or []),
            principal_on_behalf_of=principal.on_behalf_of,
            principal_on_behalf_of_groups=list(principal.on_behalf_of_groups or [])
            if principal.on_behalf_of_groups is not None
            else None,
            principal_on_behalf_of_email=principal.on_behalf_of_email,
        )

    def to_principal(self) -> Any:
        """Convert to the platform Principal model when nmp-common is available."""
        from nmp.common.auth.models import Principal

        return Principal(
            id=self.principal_id,
            email=self.principal_email,
            groups=self.principal_groups,
            on_behalf_of=self.principal_on_behalf_of,
            on_behalf_of_groups=self.principal_on_behalf_of_groups,
            on_behalf_of_email=self.principal_on_behalf_of_email,
        )


def _split_groups(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [group.strip() for group in raw.split(",") if group.strip()]


def platform_auth_enabled() -> bool:
    """Return whether platform authentication is enabled.

    Returns ``False`` on any failure to resolve the auth config. The realistic
    failure is ``ImportError``: ``nmp_common`` ships only in the platform process
    image, so when this package is used standalone (outside the platform) there
    is no auth config and "disabled" is the correct answer.

    Other failures are effectively unreachable in the context that matters here
    (the deployment controller, which runs *inside* the platform image): a
    missing config file resolves to defaults (``enabled=False``) rather than
    raising, and a malformed/invalid config file would have already crashed the
    platform service at startup before any deployment is reconciled. The config
    read is cached from that successful startup load. We therefore accept the
    narrow, largely theoretical fail-open window rather than propagate and block
    deployments on a transient/unexpected error.
    """
    try:
        from nmp.common.config import get_auth_config

        return bool(get_auth_config().enabled)
    except Exception:
        logger.debug("Could not resolve auth config; assuming auth disabled", exc_info=True)
        return False


__all__ = ["AuthContext", "platform_auth_enabled"]
