# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from scaled_evals.api.repositories.base_repository import (
    created_at_cursor_clause,
    join_where,
    normalize_order,
    order_by_clause,
)

AGENT_BUNDLE_COLUMNS = """
id, owner_id, bundle_name, agent_name, agent_version, image_ref, image_digest, entrypoint,
platform, runtime_abi,
bundle_layout_version, builder_profile, source_lock_digest, fingerprint,
metadata, visibility, qualification_status, qualification_evidence,
qualified_at, qualified_by, created_at, updated_at
"""


class AgentBundleRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def create(
        self,
        bundle_id: str,
        *,
        owner_id: str,
        bundle_name: str,
        agent_name: str,
        agent_version: str,
        image_ref: str,
        image_digest: str,
        entrypoint: str,
        platform: str,
        runtime_abi: str,
        bundle_layout_version: int,
        builder_profile: str,
        source_lock_digest: str,
        fingerprint: str,
        metadata: dict[str, Any],
    ) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (owner_id,),
            )
            cur.execute(
                f"""
                INSERT INTO agent_bundles (
                    id, owner_id, bundle_name, agent_name, agent_version,
                    image_ref, image_digest, entrypoint,
                    platform, runtime_abi, bundle_layout_version, builder_profile,
                    source_lock_digest, fingerprint, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {AGENT_BUNDLE_COLUMNS}
                """,
                (
                    bundle_id,
                    owner_id,
                    bundle_name,
                    agent_name,
                    agent_version,
                    image_ref,
                    image_digest,
                    entrypoint,
                    platform,
                    runtime_abi,
                    bundle_layout_version,
                    builder_profile,
                    source_lock_digest,
                    fingerprint,
                    Jsonb(metadata),
                ),
            )
            return cur.fetchone()

    def get_accessible(self, bundle_id: str, *, owner_id: str, include_all: bool = False) -> dict | None:
        filters = ["id = %s", "deleted_at IS NULL"]
        params: list[Any] = [bundle_id]
        if not include_all:
            filters.append("(owner_id = %s OR visibility = 'public')")
            params.append(owner_id)
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT {AGENT_BUNDLE_COLUMNS} FROM agent_bundles WHERE {join_where(filters)}",
                params,
            )
            return cur.fetchone()

    def list_accessible(
        self,
        *,
        owner_id: str,
        include_all: bool,
        mine: bool,
        visibility: str | None,
        limit: int,
        cursor: str | None,
        order: str,
    ) -> list[dict]:
        direction = normalize_order(order)
        filters = ["deleted_at IS NULL"]
        params: list[Any] = []
        if mine:
            filters.append("owner_id = %s")
            params.append(owner_id)
        elif not include_all:
            filters.append("(owner_id = %s OR visibility = 'public')")
            params.append(owner_id)
        if visibility is not None:
            filters.append("visibility = %s")
            params.append(visibility)
        cursor_filter, cursor_params = created_at_cursor_clause(cursor, direction)
        if cursor_filter:
            filters.append(cursor_filter)
            params.extend(cursor_params)
        params.append(limit + 1)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {AGENT_BUNDLE_COLUMNS}
                FROM agent_bundles
                WHERE {join_where(filters)}
                ORDER BY {order_by_clause(("created_at", "id"), direction)}
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()

    def set_qualification(
        self,
        bundle_id: str,
        *,
        status: str,
        evidence: dict[str, Any],
        qualified_by: str,
    ) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE agent_bundles
                SET qualification_status = %s,
                    qualification_evidence = %s,
                    qualified_at = NOW(),
                    qualified_by = %s,
                    visibility = CASE WHEN %s = 'rejected' THEN 'private' ELSE visibility END,
                    updated_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
                RETURNING {AGENT_BUNDLE_COLUMNS}
                """,
                (status, Jsonb(evidence), qualified_by, status, bundle_id),
            )
            return cur.fetchone()

    def promote(self, bundle_id: str, *, qualified_by: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE agent_bundles
                SET visibility = 'public', qualified_by = %s, updated_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
                  AND qualification_status = 'qualified'
                RETURNING {AGENT_BUNDLE_COLUMNS}
                """,
                (qualified_by, bundle_id),
            )
            return cur.fetchone()

    def soft_delete(self, bundle_id: str, *, owner_id: str, include_all: bool) -> bool:
        filters = ["id = %s", "deleted_at IS NULL"]
        params: list[Any] = [bundle_id]
        if not include_all:
            filters.extend(["owner_id = %s", "visibility = 'private'"])
            params.append(owner_id)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE agent_bundles SET deleted_at = NOW(), updated_at = NOW()
                WHERE {join_where(filters)}
                RETURNING id
                """,
                params,
            )
            return cur.fetchone() is not None
