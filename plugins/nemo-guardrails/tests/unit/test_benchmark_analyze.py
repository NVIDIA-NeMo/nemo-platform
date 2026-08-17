# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_guardrails_plugin.benchmarks.analyze import LatencyReport


@pytest.mark.parametrize(
    ("observed_ms", "expected"),
    [
        (890.0, True),
        (1390.0, True),
        (1590.0, True),
        (1591.0, False),
    ],
)
def test_latency_report_only_fails_regressions_beyond_tolerance(observed_ms: float, expected: bool) -> None:
    report = LatencyReport(
        concurrency=16,
        metric="delta_p50",
        baseline_ms=1390.0,
        observed_ms=observed_ms,
        tolerance_ms=200.0,
    )

    assert report.passed is expected
