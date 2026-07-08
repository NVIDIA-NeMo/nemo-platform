# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Packaging guardrails for the slim Intake client distribution."""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import distribution


def test_client_distribution_has_no_service_entry_point() -> None:
    entry_points = distribution("nemo-intake-client").entry_points

    assert not [entry_point for entry_point in entry_points if entry_point.group == "nemo.services"]


def test_importing_client_does_not_import_service_stack() -> None:
    script = """
import sys
import nemo_intake_client.client

assert "nemo_intake_plugin" not in sys.modules
assert "clickhouse_connect" not in sys.modules
"""

    subprocess.run([sys.executable, "-c", script], check=True)
