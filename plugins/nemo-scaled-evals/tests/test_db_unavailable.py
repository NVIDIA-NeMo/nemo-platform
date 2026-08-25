# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest import mock

import pytest
from fastapi import HTTPException
from psycopg_pool import PoolTimeout
from scaled_evals.api import db


def test_unreachable_database_is_503_not_500() -> None:
    """A dead Postgres must not look like a bug in whichever route was called.

    This is the guard for a real misdiagnosis: when the database pod was deleted
    under the cluster, `GET /evaluations/{id}/archive` returned 500 with a
    PoolTimeout traceback and got filed as a broken archive route.
    """
    with mock.patch.object(db, "pooled_connection", side_effect=PoolTimeout("no conn")):
        with pytest.raises(HTTPException) as caught:
            next(db.get_conn())

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "database_unavailable"
