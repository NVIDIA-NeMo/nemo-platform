# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The smoke agent's traces must be consumable by the Analyzer's TraceExplorer.

Needs a trace produced by a container run, so it skips when none is present.
Produce one by running ``main.py`` in the task image with ``/app/traces`` mounted
out, then point ``SMOKE_TRACE_DIR`` at it.

NOOA instruments plain, non-@strategy methods automatically, so one AGENT span
per method call arrives with no instrumentation of our own. That is the signal
every group's diagnosis rests on, and this pins it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import TraceExplorer

_TRACE_DIR = Path(os.environ.get("SMOKE_TRACE_DIR", "/tmp/smoke-traces"))


def _traces() -> list[Path]:
    return sorted(_TRACE_DIR.glob("*.jsonl")) if _TRACE_DIR.is_dir() else []


@pytest.mark.skipif(not _traces(), reason="no recorded smoke-agent trace")
@pytest.mark.asyncio
async def test_trace_carries_the_method_call_graph() -> None:
    """One AGENT span per method call, which is how a diagnosis identifies the fault.

    The G4 assertion needs a trace of a *counting* question. A lookup-only trace
    records solve and handle_lookup and nothing else, so taking whichever file
    sorted first would fail here even though tracing works perfectly. Search for
    the trace that carries the call path instead, and say so if none does.
    """
    per_trace: dict[Path, dict[str, int]] = {}
    for path in _traces():
        explorer = await TraceExplorer.from_file(path)
        per_trace[path] = await explorer.get_method_counts()

    assert any(per_trace.values()), "no agent methods traced — NOOA instrumentation is not engaging"
    assert any("ReportAgent.solve" in counts for counts in per_trace.values()), (
        f"expected solve to be traced in some trace; saw {sorted({m for c in per_trace.values() for m in c})}"
    )

    # G4's fingerprint: a counting question answered by the list handler.
    with_list = [path.name for path, counts in per_trace.items() if "ReportAgent.handle_list" in counts]
    assert with_list, (
        "no recorded trace runs handle_list, so none captures a counting question. "
        f"Record one against g4-dispatch-order; traces present: {[p.name for p in _traces()]}"
    )


@pytest.mark.skipif(not _traces(), reason="no recorded smoke-agent trace")
@pytest.mark.asyncio
async def test_overview_exposes_nesting_and_results() -> None:
    """The Analyzer reads the call graph and result previews, not a turn list.

    A zero-LLM agent emits no LLM or TOOL spans, so turn_count is 0 and the
    turn-oriented helpers return nothing. That is expected; the evidence lives in
    the call graph and each method's recorded input and output.
    """
    explorer = await TraceExplorer.from_file(_traces()[0])

    overview = await explorer.get_overview_data()
    assert overview is not None
    assert overview.root.agent_name == "ReportAgent"
    assert overview.stats.session_count >= 2, "handlers should nest under solve"

    depths = {entry["full_name"]: entry["depth"] for entry in overview.call_graph}
    assert depths["ReportAgent.solve"] == 0
    assert any(depth == 1 for name, depth in depths.items() if name != "ReportAgent.solve")

    previews = [s.result_preview for s in overview.sessions if s.result_preview]
    assert previews, "result previews are how the Analyzer sees what each method returned"
