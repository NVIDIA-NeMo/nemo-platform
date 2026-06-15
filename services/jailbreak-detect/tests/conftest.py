# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest wiring: opt-in gate for slow integration tests.

Tests marked ``@pytest.mark.integration`` load the real embedder + random forest
(CPU is fine, just slow, and the first run downloads weights). They're skipped by
default so the fast mocked suite stays the norm; pass ``--run-integration`` to run
them.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run slow integration tests that load the real model (CPU ok; downloads weights).",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(reason="needs --run-integration (slow: loads real model + weights)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
