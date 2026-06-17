# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for platform runner startup display helpers."""

import logging

import pytest
from nmp.platform_runner.run import _database_display


@pytest.mark.parametrize(
    ("db_url", "expected"),
    [
        (
            "sqlite:////var/data/nmp-platform.db",
            "sqlite (/var/data/nmp-platform.db)",
        ),
        (
            "sqlite+aiosqlite:////var/data/nmp-platform.db",
            "sqlite (/var/data/nmp-platform.db)",
        ),
        ("sqlite:///relative/nmp-platform.db", "sqlite (relative/nmp-platform.db)"),
        ("sqlite+aiosqlite:///relative/nmp-platform.db", "sqlite (relative/nmp-platform.db)"),
    ],
)
def test_database_display_formats_sqlite_paths(db_url: str, expected: str) -> None:
    assert _database_display(db_url) == expected


def test_database_display_formats_non_sqlite_driver() -> None:
    assert _database_display("postgresql+asyncpg://user:pass@localhost:5432/nemo") == "postgresql"


def test_database_display_logs_parse_failures(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="nmp.platform_runner.run"):
        assert _database_display("postgresql://localhost:not-a-port/nemo") == "postgresql"

    records = [record for record in caplog.records if record.name == "nmp.platform_runner.run"]
    assert len(records) == 1
    assert records[0].message == "Failed to parse database URL for startup banner"
    assert records[0].exc_info is not None
