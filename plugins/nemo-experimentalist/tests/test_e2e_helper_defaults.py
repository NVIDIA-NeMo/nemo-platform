# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Defaults exposed by the reviewer-facing evaluator-only helper."""

import runpy
import sys
from pathlib import Path

import pytest


def test_eval_only_helper_defaults_to_native_harbor(monkeypatch: pytest.MonkeyPatch) -> None:
    script = Path(__file__).parents[1] / "docs" / "e2e" / "run-eval-only.py"
    namespace = runpy.run_path(str(script))
    monkeypatch.setattr(sys, "argv", [str(script)])

    args = namespace["_parse_args"]()

    assert args.evaluator_type == "harbor_native"
