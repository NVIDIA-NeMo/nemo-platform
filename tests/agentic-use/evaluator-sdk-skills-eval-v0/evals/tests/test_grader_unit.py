# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the evaluator SDK eval custom grader."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_grader_module():
    grader_path = Path(__file__).with_name("grader.py")
    spec = importlib.util.spec_from_file_location("evaluator_sdk_eval_grader", grader_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_custom_metrics_are_emitted_per_pytest_function(tmp_path: Path) -> None:
    junit_xml = tmp_path / "pytest.xml"
    junit_xml.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="1" errors="0" skipped="0">
    <testcase classname="test_outputs" name="test_saved_script_exists" time="0.01" />
    <testcase classname="test_outputs" name="test_saved_script_passes_ty_check" time="0.02">
      <failure message="assert 1 == 0">ty failed</failure>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )
    grader = _load_grader_module()

    metrics, details = grader._custom_metrics_from_junit(junit_xml)

    assert metrics == {
        "nemo_evaluator_test_saved_script_exists": 1.0,
        "nemo_evaluator_test_saved_script_passes_ty_check": 0.0,
    }
    assert details["nemo_evaluator_test_saved_script_exists"]["test_name"] == "test_saved_script_exists"
    assert details["nemo_evaluator_test_saved_script_passes_ty_check"]["outcome"] == "failed"
