# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from scaled_evals.api.auth import CurrentPrincipal, current_principal
from scaled_evals.api.db import Database, get_db
from scaled_evals.api.settings import settings


def record_principal(db: Database, principal: CurrentPrincipal) -> None:
    """JIT-register normalized identity claims; never persists bearer tokens."""
    db.users.upsert(
        principal.owner_id,
        email=principal.email,
        username=principal.username,
        display_name=principal.display_name,
    )


def is_admin(principal: CurrentPrincipal) -> bool:
    subjects = {value.strip() for value in settings.control_plane_admin_subjects.split(",") if value.strip()}
    emails = {value.strip().lower() for value in settings.control_plane_admin_emails.split(",") if value.strip()}
    groups = {value.strip() for value in settings.control_plane_admin_groups.split(",") if value.strip()}
    roles = {value.strip() for value in settings.control_plane_admin_roles.split(",") if value.strip()}
    return (
        principal.owner_id in subjects
        or bool(principal.email and principal.email.lower() in emails)
        or bool(groups.intersection(principal.groups))
        or bool(roles.intersection(principal.roles))
    )


def require_admin(
    principal: Annotated[CurrentPrincipal, Depends(current_principal)],
    db: Annotated[Database, Depends(get_db)],
) -> CurrentPrincipal:
    # Deliberately hide the admin surface from non-admin callers.
    # Auth-disabled development has one server-generated principal and is
    # already treated as unrestricted by the owner-scoped repositories.
    if principal.source != "disabled" and not is_admin(principal):
        raise HTTPException(status_code=404, detail="not found")
    record_principal(db, principal)
    return principal
