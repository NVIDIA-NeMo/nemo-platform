# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Emit a minimal JUnit XML report for the benchmark harness.

We deliberately use ``xml.etree`` rather than a third-party JUnit library to
avoid adding a dependency just for this one consumer. Schema is the standard
``<testsuite><testcase>...`` shape that GitHub Actions and most CI dashboards
render natively.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

from nemo_guardrails_plugin.benchmarks.aiperf_runner import SweepRunResult
from nemo_guardrails_plugin.benchmarks.constants import JUNIT_SUITE_NAME


@dataclass(frozen=True)
class JUnitCase:
    name: str
    classname: str
    time_seconds: float
    passed: bool
    failure_message: str | None = None
    system_out: str | None = None


def cases_from_sweep_results(results: list[SweepRunResult]) -> list[JUnitCase]:
    """Translate AIPerf per-sweep outcomes into JUnit test cases.

    Pass criterion is just ``return_code == 0``; downstream tooling can layer
    on threshold-based failures later.
    """
    cases: list[JUnitCase] = []
    for r in results:
        message = None if r.passed else f"aiperf exited with code {r.return_code}"
        cases.append(
            JUnitCase(
                name=r.sweep_label,
                classname=JUNIT_SUITE_NAME,
                time_seconds=r.duration_seconds,
                passed=r.passed,
                failure_message=message,
                system_out=f"output_dir={r.output_dir}",
            )
        )
    return cases


def write_junit_report(path: Path, *, suite_name: str, cases: list[JUnitCase]) -> None:
    """Render a single-suite JUnit XML file at ``path``."""
    failure_count = sum(1 for c in cases if not c.passed)
    total_time = sum(c.time_seconds for c in cases)

    testsuites = ET.Element(
        "testsuites",
        attrib={
            "name": suite_name,
            "tests": str(len(cases)),
            "failures": str(failure_count),
            "errors": "0",
            "time": f"{total_time:.3f}",
        },
    )
    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        attrib={
            "name": suite_name,
            "tests": str(len(cases)),
            "failures": str(failure_count),
            "errors": "0",
            "time": f"{total_time:.3f}",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )

    for case in cases:
        tc = ET.SubElement(
            testsuite,
            "testcase",
            attrib={
                "name": case.name,
                "classname": case.classname,
                "time": f"{case.time_seconds:.3f}",
            },
        )
        if not case.passed:
            failure = ET.SubElement(
                tc,
                "failure",
                attrib={"message": case.failure_message or "failed", "type": "BenchmarkFailure"},
            )
            failure.text = case.failure_message or ""
        if case.system_out:
            ET.SubElement(tc, "system-out").text = case.system_out

    path.parent.mkdir(parents=True, exist_ok=True)
    rough = ET.tostring(testsuites, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    path.write_text(pretty, encoding="utf-8")
