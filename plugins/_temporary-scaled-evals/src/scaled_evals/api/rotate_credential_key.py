# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Atomically re-encrypt stored credential payloads with the primary key."""

from __future__ import annotations

import argparse

import psycopg
from psycopg.rows import dict_row

from scaled_evals.api import crypto
from scaled_evals.api.settings import settings


def rotate_credentials(*, dry_run: bool = False) -> int:
    """Rotate every live credential in one transaction and return its count."""
    with (
        psycopg.connect(
            settings.resolved_database_url(),
            row_factory=dict_row,
        ) as conn,
        conn.transaction(),
        conn.cursor() as cur,
    ):
        cur.execute("SELECT id, encrypted_payload FROM credentials WHERE deleted_at IS NULL ORDER BY id FOR UPDATE")
        rows = cur.fetchall()
        rotated = [(crypto.reencrypt(row["encrypted_payload"]), row["id"]) for row in rows]
        if not dry_run:
            cur.executemany(
                "UPDATE credentials SET encrypted_payload = %s, updated_at = NOW() WHERE id = %s",
                rotated,
            )
        return len(rotated)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-encrypt all live credential payloads with the configured primary key."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify every payload can be decrypted without updating PostgreSQL.",
    )
    args = parser.parse_args()
    count = rotate_credentials(dry_run=args.dry_run)
    action = "verified" if args.dry_run else "rotated"
    print(f"{action} {count} credential payload(s)")


if __name__ == "__main__":
    main()
