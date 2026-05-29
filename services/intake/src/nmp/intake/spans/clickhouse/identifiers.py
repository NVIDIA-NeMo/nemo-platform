# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validated ClickHouse identifier helpers."""

from __future__ import annotations

import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_clickhouse_identifier(identifier: str) -> str:
    """Return identifier after validating it is safe for SQL interpolation."""

    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Invalid ClickHouse identifier: {identifier!r}")
    return identifier


def column(name: str, *, qualifier: str | None = None) -> str:
    """Build a validated column reference, optionally qualified by table alias."""

    validate_clickhouse_identifier(name)
    if qualifier is None:
        return name
    validate_clickhouse_identifier(qualifier)
    return f"{qualifier}.{name}"
