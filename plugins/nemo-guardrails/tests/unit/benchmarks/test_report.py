# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import xml.etree.ElementTree as ET
from pathlib import Path

from nemo_guardrails_plugin.benchmarks.aiperf_runner import SweepRunResult
from nemo_guardrails_plugin.benchmarks.report import (
    JUnitCase,
    cases_from_sweep_results,
    write_junit_report,
)


def _result(label: str, *, returncode: int, duration: float = 60.0) -> SweepRunResult:
    return SweepRunResult(
        sweep_label=label,
        output_dir=Path("/tmp") / label,
        return_code=returncode,
        duration_seconds=duration,
        metadata_path=None,
        process_result_path=None,
    )


class TestCasesFromSweepResults:
    def test_passing_case_has_no_failure_message(self) -> None:
        cases = cases_from_sweep_results([_result("concurrency1", returncode=0)])
        assert len(cases) == 1
        assert cases[0].passed
        assert cases[0].failure_message is None
        assert cases[0].time_seconds == 60.0

    def test_failing_case_includes_exit_code(self) -> None:
        cases = cases_from_sweep_results([_result("concurrency1", returncode=3)])
        assert not cases[0].passed
        assert "code 3" in (cases[0].failure_message or "")


class TestWriteJunitReport:
    def test_basic_report_structure(self, tmp_path: Path) -> None:
        cases = [
            JUnitCase(name="concurrency1", classname="suite", time_seconds=70.0, passed=True),
            JUnitCase(
                name="concurrency2",
                classname="suite",
                time_seconds=72.5,
                passed=False,
                failure_message="boom",
                system_out="output_dir=/tmp/concurrency2",
            ),
        ]

        path = tmp_path / "report.xml"
        write_junit_report(path, suite_name="suite", cases=cases)

        tree = ET.parse(path)
        root = tree.getroot()
        assert root.tag == "testsuites"
        assert root.attrib["tests"] == "2"
        assert root.attrib["failures"] == "1"

        testsuite = root.find("testsuite")
        assert testsuite is not None
        assert testsuite.attrib["name"] == "suite"
        assert testsuite.attrib["failures"] == "1"

        testcases = testsuite.findall("testcase")
        assert [tc.attrib["name"] for tc in testcases] == ["concurrency1", "concurrency2"]

        passing, failing = testcases
        assert passing.find("failure") is None
        failure = failing.find("failure")
        assert failure is not None
        assert failure.attrib["message"] == "boom"
        system_out = failing.find("system-out")
        assert system_out is not None
        assert system_out.text == "output_dir=/tmp/concurrency2"

    def test_writes_pretty_xml(self, tmp_path: Path) -> None:
        path = tmp_path / "report.xml"
        write_junit_report(
            path,
            suite_name="suite",
            cases=[JUnitCase(name="x", classname="suite", time_seconds=0.0, passed=True)],
        )

        text = path.read_text(encoding="utf-8")
        assert text.startswith("<?xml")
        assert "  <testsuite" in text  # indentation present
