# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for log-value scrubbing."""

from __future__ import annotations

from nemo_agents_plugin.log_utils import scrub


def test_scrub_strips_crlf() -> None:
    assert scrub("ok\r\nINFO forged log line") == "okINFO forged log line"


def test_scrub_stringifies_non_str() -> None:
    assert scrub(42) == "42"
    assert scrub(RuntimeError("boom\nfake")) == "boomfake"
