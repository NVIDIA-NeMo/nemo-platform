# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Auth service entities."""

from datetime import datetime
from typing import Any, Literal

from nmp.common.entities import EntityBase
from pydantic import model_validator


class RoleBindingEntity(EntityBase):
    """Role binding entity for authorization.

    Extends EntityBase which provides:
    - id: str (auto-generated UUID)
    - workspace: str (the workspace this binding grants access to)
    - created_at: datetime
    - updated_at: datetime

    The workspace field from EntityBase serves dual purpose:
    - It's the workspace where this entity is stored
    - It's also the workspace this role binding grants access to
    """

    __entity_type__ = "role_binding"

    principal: str
    role: str
    granted_by: str
    granted_at: datetime
    revoked_at: datetime | None = None


class AccessKeyEntity(EntityBase):
    """Persistent lifecycle record for a Scoped Access Key.

    The inherited ``name`` field stores the JWT ID (jti) as the stable entity key.
    ``key_name`` is the optional human-readable label supplied at creation time.
    """

    __entity_type__ = "access_key"

    key_name: str | None = None
    description: str | None = None
    principal: str
    issuer: str
    audiences: list[str]
    issued_at: datetime
    expires_at: datetime | None = None
    status: Literal["ACTIVE", "REVOKED", "SUSPENDED"] = "ACTIVE"

    @model_validator(mode="before")
    @classmethod
    def _migrate_revoked_at(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("revoked_at") is not None:
            data = dict(data)
            data["status"] = "REVOKED"
        return data
