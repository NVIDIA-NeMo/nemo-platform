# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-owned, best-effort human narration of an experimentalist run.

Fed by the universal verbs the loop/strategy calls (mirroring the future
``OptimizerContext`` surface), this formats permanent lines to a sink
(default stderr, matching the run's other startup lines). It is additive and
non-critical: every public method swallows its own exceptions, so narration
can never break a run.
"""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import TextIO

_RULE = "═" * 62
_THIN = "─" * 62


class Verbosity(str, Enum):
    """Reporter output level. Set once at construction from the run shell.

    NOTE: VERBOSE is a forward-declared seam and currently renders EXACTLY the
    same output as NORMAL — only QUIET changes behavior today. The richer
    VERBOSE output (per-trial detail, per-split sub-metrics, timings) is
    deferred; see the "Verbosity (future)" section of the design spec. Wire the
    extra detail here when the ``--verbose`` CLI flag lands.
    """

    QUIET = "quiet"
    NORMAL = "normal"
    VERBOSE = "verbose"  # == NORMAL for now; see class docstring


def reward_scalar(aggregate_metrics: dict[str, float | int]) -> float:
    """Extract the scalar reward from an evaluation's aggregate metrics."""
    return float(aggregate_metrics.get("reward", 0.0))


class RunReporter:
    """Formats run-progress narration to a sink. Never raises into the run."""

    def __init__(
        self,
        *,
        sink: TextIO | None = None,
        verbosity: Verbosity = Verbosity.NORMAL,
    ) -> None:
        self._sink: TextIO = sink if sink is not None else sys.stderr
        self._verbosity = verbosity
        self._baseline_val: float | None = None

    def _emit(self, line: str) -> None:
        try:
            self._sink.write(line + "\n")
            self._sink.flush()
        except Exception:  # noqa: BLE001 - narration must never break the run
            pass

    def run_started(
        self, *, run_dir: Path, agent: str, insight: str | None, strategy: str
    ) -> None:
        try:
            self._emit(_RULE)
            self._emit(f" NeMo Experimentalist · strategy={strategy} · agent={agent}")
            self._emit(f" run:     {run_dir}")
            self._emit(f" insight: {insight or '(none — dataset-driven)'}")
            self._emit(_RULE)
        except Exception:  # noqa: BLE001
            pass

    def progress(
        self,
        *,
        phase: str,
        completed: int | None = None,
        total: int | None = None,
        unit: str = "round",
    ) -> None:
        if self._verbosity is Verbosity.QUIET:
            return
        try:
            frac = ""
            if completed is not None:
                frac = (
                    f" {unit} {completed}/≤{total}"
                    if total is not None
                    else f" {unit} {completed}"
                )
            self._emit(f"▶{frac} · {phase}")
        except Exception:  # noqa: BLE001
            pass

    def candidate_started(
        self, *, label: str, optimization: str, i: int | None, n: int | None
    ) -> None:
        if self._verbosity is Verbosity.QUIET:
            return
        try:
            counter = f" ({i}/{n})" if i is not None and n is not None else ""
            self._emit(f"   {label}{counter}: {optimization}")
        except Exception:  # noqa: BLE001
            pass

    def candidate_evaluated(
        self, *, label: str, split: str, reward: float, artifacts: Path
    ) -> None:
        if self._verbosity is Verbosity.QUIET:
            return
        try:
            delta = ""
            if split == "validation":
                if self._baseline_val is None:
                    self._baseline_val = reward
                else:
                    d = reward - self._baseline_val
                    delta = f"  {'▲' if d >= 0 else '▼'}{d:+.3f}"
            self._emit(
                f"   {label} · {split:<10} · reward {reward:.3f}{delta}   → {artifacts}"
            )
        except Exception:  # noqa: BLE001
            pass

    def run_finished(
        self, *, winner: str | None, scores: dict[str, float], report_path: Path | None
    ) -> None:
        try:
            self._emit(_THIN)
            if winner is None:
                self._emit(" Finished · no winner (no scored candidates)")
            else:
                head = f" Finished · winner={winner}"
                val = scores.get("reward")
                if val is not None:
                    base = (
                        f" (baseline {self._baseline_val:.3f})"
                        if self._baseline_val is not None
                        else ""
                    )
                    head += f" · validation {val:.3f}{base}"
                self._emit(head)
            if report_path is not None:
                self._emit(f" report:  {report_path}")
            self._emit(_THIN)
        except Exception:  # noqa: BLE001
            pass

    def note(self, msg: str) -> None:
        if self._verbosity is Verbosity.QUIET:
            return
        try:
            self._emit(f"   … {msg}")
        except Exception:  # noqa: BLE001
            pass
