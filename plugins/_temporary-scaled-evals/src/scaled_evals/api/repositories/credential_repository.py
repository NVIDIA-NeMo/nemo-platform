# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# The repository below defines a ``list`` method, which shadows the builtin for
# annotations in the same class body, so those spell the type ``builtins.list``.
import builtins
from typing import Any

import psycopg

from scaled_evals.api.repositories.base_repository import (
    Conflict,
    created_at_cursor_clause,
    join_where,
    normalize_order,
    order_by_clause,
    substring_search_pattern,
)

CREDENTIAL_COLUMNS = "id, name, provider, payload_kind, fingerprint, created_at, updated_at"


class CredentialRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def create(
        self,
        credential_id: str,
        *,
        name: str,
        provider: str,
        payload_kind: str,
        encrypted_payload: bytes | str,
        fingerprint: str,
        owner_id: str,
    ) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO credentials
                    (id, owner_id, name, provider, payload_kind, encrypted_payload, fingerprint)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING {CREDENTIAL_COLUMNS}
                """,
                (
                    credential_id,
                    owner_id,
                    name,
                    provider,
                    payload_kind,
                    encrypted_payload,
                    fingerprint,
                ),
            )
            return cur.fetchone()

    def list(
        self,
        *,
        provider: str | None,
        limit: int,
        cursor: str | None,
        order: str,
        owner_id: str,
        include_unowned: bool = False,
        q: str | None = None,
    ) -> builtins.list[dict]:
        direction = normalize_order(order)
        ordering = order_by_clause(("created_at", "id"), direction)
        filters = ["deleted_at IS NULL", "(owner_id = %s OR (%s AND owner_id IS NULL))"]
        params: list[Any] = [owner_id, include_unowned]
        if provider is not None:
            filters.append("provider = %s")
            params.append(provider)
        if search := substring_search_pattern(q):
            filters.append(
                "(id ILIKE %s ESCAPE '\\' OR name ILIKE %s ESCAPE '\\' "
                "OR provider::text ILIKE %s ESCAPE '\\' "
                "OR payload_kind::text ILIKE %s ESCAPE '\\' "
                "OR fingerprint ILIKE %s ESCAPE '\\')"
            )
            params.extend([search] * 5)
        cursor_filter, cursor_params = created_at_cursor_clause(cursor, direction)
        if cursor_filter:
            filters.append(cursor_filter)
            params.extend(cursor_params)
        params.append(limit + 1)

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {CREDENTIAL_COLUMNS}
                FROM credentials
                WHERE {join_where(filters)}
                ORDER BY {ordering}
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()

    def get_metadata(self, credential_id: str, *, owner_id: str, include_unowned: bool = False) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {CREDENTIAL_COLUMNS}
                FROM credentials
                WHERE id = %s AND deleted_at IS NULL
                  AND (owner_id = %s OR (%s AND owner_id IS NULL))
                """,
                (credential_id, owner_id, include_unowned),
            )
            return cur.fetchone()

    def rename(
        self,
        credential_id: str,
        *,
        name: str,
        owner_id: str,
        include_unowned: bool = False,
    ) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE credentials
                SET name = %s, updated_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
                  AND (owner_id = %s OR (%s AND owner_id IS NULL))
                RETURNING {CREDENTIAL_COLUMNS}
                """,
                (name, credential_id, owner_id, include_unowned),
            )
            return cur.fetchone()

    def rotate(
        self,
        credential_id: str,
        *,
        payload_kind: str,
        encrypted_payload: bytes | str,
        fingerprint: str,
        owner_id: str,
        include_unowned: bool = False,
    ) -> dict | None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM credentials
                WHERE id = %s AND deleted_at IS NULL
                  AND (owner_id = %s OR (%s AND owner_id IS NULL))
                FOR UPDATE
                """,
                (credential_id, owner_id, include_unowned),
            )
            if cur.fetchone() is None:
                return None
            if self.active_evaluation_reference_exists(credential_id):
                raise Conflict(
                    "credential_in_use",
                    "credential is referenced by an active evaluation",
                )
            cur.execute(
                f"""
                UPDATE credentials
                SET payload_kind = %s,
                    encrypted_payload = %s,
                    fingerprint = %s,
                    updated_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
                  AND (owner_id = %s OR (%s AND owner_id IS NULL))
                RETURNING {CREDENTIAL_COLUMNS}
                """,
                (
                    payload_kind,
                    encrypted_payload,
                    fingerprint,
                    credential_id,
                    owner_id,
                    include_unowned,
                ),
            )
            return cur.fetchone()

    def active_evaluation_reference_exists(self, credential_id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM evaluations
                WHERE deleted_at IS NULL
                  AND status NOT IN ('succeeded', 'failed', 'cancelled')
                  AND EXISTS (
                      SELECT 1
                      FROM jsonb_each_text(credentials) AS credential_refs(role, credential_id)
                      WHERE credential_refs.credential_id = %s
                  )
                LIMIT 1
                """,
                (credential_id,),
            )
            return cur.fetchone() is not None

    def soft_delete(self, credential_id: str, *, owner_id: str, include_unowned: bool = False) -> bool:
        if (
            self.get_metadata(
                credential_id,
                owner_id=owner_id,
                include_unowned=include_unowned,
            )
            is None
        ):
            return False
        if self.active_evaluation_reference_exists(credential_id):
            raise Conflict(
                "credential_in_use",
                "credential is referenced by an active evaluation",
            )
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE credentials
                SET deleted_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
                  AND (owner_id = %s OR (%s AND owner_id IS NULL))
                RETURNING id
                """,
                (credential_id, owner_id, include_unowned),
            )
            return cur.fetchone() is not None

    def get_secret_payload(self, credential_id: str, *, owner_id: str, include_unowned: bool = False) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, provider, payload_kind, encrypted_payload, fingerprint
                FROM credentials
                WHERE id = %s AND deleted_at IS NULL
                  AND (owner_id = %s OR (%s AND owner_id IS NULL))
                """,
                (credential_id, owner_id, include_unowned),
            )
            return cur.fetchone()

    def load_for_dispatch(
        self,
        credential_ids: builtins.list[str],
        *,
        owner_id: str | None = None,
        include_unowned: bool = False,
    ) -> builtins.list[dict]:
        if not credential_ids:
            return []
        owner_filter = ""
        params: list[Any] = [credential_ids]
        if owner_id is not None:
            owner_filter = "AND (owner_id = %s OR (%s AND owner_id IS NULL))"
            params.extend((owner_id, include_unowned))
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, provider, payload_kind, encrypted_payload, fingerprint
                FROM credentials
                WHERE id = ANY(%s) AND deleted_at IS NULL
                  {owner_filter}
                """,
                params,
            )
            return cur.fetchall()
