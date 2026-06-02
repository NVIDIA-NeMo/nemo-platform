#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run the evaluator SDK pytest verifier as ACES custom metrics."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

LOG_DIR = Path("/logs/verifier")
REWARD_JSON = LOG_DIR / "reward.json"
REWARD_TXT = LOG_DIR / "reward.txt"
PYTEST_LOG = LOG_DIR / "nemo_evaluator_pytest.log"
PYTEST_XML = LOG_DIR / "nemo_evaluator_pytest.xml"
METRIC_PREFIX = "nemo_evaluator"


def _metric_name(test_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", test_name).strip("_").lower()
    return f"{METRIC_PREFIX}_{safe or 'pytest'}"


def _case_outcome(testcase: ElementTree.Element) -> tuple[float, str, str]:
    failure = testcase.find("failure")
    if failure is not None:
        return 0.0, "failed", failure.attrib.get("message") or (failure.text or "test failed")

    error = testcase.find("error")
    if error is not None:
        return 0.0, "error", error.attrib.get("message") or (error.text or "test errored")

    skipped = testcase.find("skipped")
    if skipped is not None:
        return 0.0, "skipped", skipped.attrib.get("message") or (skipped.text or "test skipped")

    return 1.0, "passed", "Pytest function passed."


def _custom_metrics_from_junit(junit_xml: Path) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    root = ElementTree.parse(junit_xml).getroot()
    metrics: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}

    for testcase in root.findall(".//testcase"):
        test_name = testcase.attrib.get("name") or "unknown_test"
        metric_name = _metric_name(test_name)
        if metric_name in metrics:
            metric_name = f"{metric_name}_{len(metrics)}"

        score, outcome, reason = _case_outcome(testcase)
        metrics[metric_name] = score
        details[metric_name] = {
            "score": score,
            "reason": reason,
            "outcome": outcome,
            "test_name": test_name,
            "classname": testcase.attrib.get("classname", ""),
            "time_seconds": float(testcase.attrib.get("time", "0") or 0),
            "log": str(PYTEST_LOG),
            "junit_xml": str(PYTEST_XML),
        }

    return metrics, details


def _fallback_metrics(exit_code: int) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    score = 1.0 if exit_code == 0 else 0.0
    metric_name = f"{METRIC_PREFIX}_pytest_collection"
    return {
        metric_name: score,
    }, {
        metric_name: {
            "score": score,
            "reason": (
                "Pytest completed but produced no per-test JUnit records."
                if score == 1.0
                else "Pytest failed before per-test JUnit records were available."
            ),
            "outcome": "passed" if score == 1.0 else "failed",
            "test_name": "pytest_collection",
            "log": str(PYTEST_LOG),
            "junit_xml": str(PYTEST_XML),
        }
    }


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "/app/.venv/bin/python",
            "-m",
            "pytest",
            "/tests/test_outputs.py",
            "-rA",
            "--junitxml",
            str(PYTEST_XML),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    PYTEST_LOG.write_text(
        f"$ /app/.venv/bin/python -m pytest /tests/test_outputs.py -rA --junitxml {PYTEST_XML}\n"
        f"exit_code={result.returncode}\n\n"
        f"--- stdout ---\n{result.stdout}\n\n"
        f"--- stderr ---\n{result.stderr}\n",
        encoding="utf-8",
    )

    if PYTEST_XML.exists():
        custom_metrics, details = _custom_metrics_from_junit(PYTEST_XML)
    else:
        custom_metrics, details = _fallback_metrics(result.returncode)
    if not custom_metrics:
        custom_metrics, details = _fallback_metrics(result.returncode)

    score = sum(custom_metrics.values()) / len(custom_metrics)
    reward = {
        "overall": score,
        "custom_metrics": custom_metrics,
        "details": details,
        "pytest_exit_code": result.returncode,
    }
    REWARD_JSON.write_text(json.dumps(reward, indent=2), encoding="utf-8")
    REWARD_TXT.write_text(str(score), encoding="utf-8")


if __name__ == "__main__":
    main()
