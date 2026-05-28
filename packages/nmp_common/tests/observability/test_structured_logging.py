# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the structured-logging processors."""

from __future__ import annotations

import logging

import pytest
from nmp.common.observability.structured_logging import _sanitize_log_strings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("admin\n[ERROR] forged log line", "admin [ERROR] forged log line"),
        ("with\r\ncrlf", "with  crlf"),
        ("tab\tis fine", "tab\tis fine"),
        ("plain string", "plain string"),
        ("nel\x85next", "nel next"),
        ("ls lsep", "ls lsep"),
    ],
)
def test_sanitize_log_strings_replaces_newline_variants(raw: str, expected: str) -> None:
    event = {"event": "test", "user": raw}
    result = _sanitize_log_strings(logging.getLogger(), "info", event)
    assert result["user"] == expected


def test_sanitize_log_strings_leaves_non_string_values_alone() -> None:
    event = {"event": "test", "count": 5, "ok": True, "items": [1, 2, 3]}
    result = _sanitize_log_strings(logging.getLogger(), "info", event)
    assert result == event


def test_sanitize_log_strings_skips_clean_strings() -> None:
    event = {"event": "test", "name": "default/workspace"}
    result = _sanitize_log_strings(logging.getLogger(), "info", event)
    assert result["name"] == "default/workspace"
