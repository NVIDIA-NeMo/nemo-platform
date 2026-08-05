# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Auth service entities."""

from datetime import datetime
from typing import Optional

from nmp.common.entities import EntityBase


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
    revoked_at: Optional[datetime] = None


class AccessKeyEntity(EntityBase):
    """Persistent lifecycle record for a Scoped Access Key."""

    __entity_type__ = "access_key"

    key_name: str | None = None
    description: str | None = None
    principal: str
    issuer: str
    audiences: list[str]
    issued_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
