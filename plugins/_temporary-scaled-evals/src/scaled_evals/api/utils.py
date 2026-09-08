# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from scaled_evals.api.schemas.common import ListEnvelope


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:26]}"


def list_envelope(
    items: list[Any] | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> ListEnvelope[Any]:
    if cursor is not None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_cursor", "message": "invalid cursor", "details": {}}},
        )
    _ = limit
    return ListEnvelope(data=items or [], next_cursor=None)
