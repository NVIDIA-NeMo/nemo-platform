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

from nemo_experimentalist_plugin.entities import MetricTarget

_RULE = "═" * 62
_THIN = "─" * 62


class Verbosity(str, Enum):
    """Reporter output level. Set once at construction from the run shell.

    An enum (rather than a bool) so levels read clearly at call sites and a
    richer level (e.g. VERBOSE with per-trial detail / sub-metrics / timings)
    can be added when it earns its keep.
    """

    QUIET = "quiet"
    NORMAL = "normal"


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
        self._baseline_metrics: dict[str, float] | None = None
        self._objective_metrics: list[MetricTarget] = []

    def _emit(self, line: str) -> None:
        try:
            self._sink.write(line + "\n")
            self._sink.flush()
        except Exception:  # noqa: BLE001 - narration must never break the run
            pass

    def seed_baseline(self, metrics: dict[str, float | int]) -> None:
        """Set the validation delta reference without emitting a line.

        Used on resume, where agent-0 is not re-evaluated: without this, the
        first newly evaluated candidate would become the baseline and later
        deltas would be measured against the wrong candidate. No-op once a
        baseline is already set.
        """
        try:
            if self._baseline_metrics is None:
                self._baseline_metrics = {name: float(value) for name, value in metrics.items()}
        except Exception:  # noqa: BLE001
            pass

    def run_started(self, *, run_dir: Path, agent: str, insight: str | None, strategy: str) -> None:
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
                frac = f" {unit} {completed}/≤{total}" if total is not None else f" {unit} {completed}"
            self._emit(f"▶{frac} · {phase}")
        except Exception:  # noqa: BLE001
            pass

    def candidate_started(self, *, label: str, optimization: str, i: int | None, n: int | None) -> None:
        if self._verbosity is Verbosity.QUIET:
            return
        try:
            counter = f" ({i}/{n})" if i is not None and n is not None else ""
            self._emit(f"   {label}{counter}: {optimization}")
        except Exception:  # noqa: BLE001
            pass

    def candidate_evaluated(
        self,
        *,
        label: str,
        split: str,
        metrics: dict[str, float | int],
        objective_metrics: list[MetricTarget],
        artifacts: Path,
    ) -> None:
        """Narrate an evaluation using all configured objective metrics.

        Objective directions determine whether validation deltas are displayed
        as improvements or declines. Regression metrics are guardrails and are
        intentionally not presented as progress dimensions.
        """
        if self._verbosity is Verbosity.QUIET:
            return
        try:
            self._objective_metrics = objective_metrics
            has_baseline = self._baseline_metrics is not None
            if split == "validation":
                self.seed_baseline(metrics)
            rendered_metrics: list[str] = []
            for target in objective_metrics:
                value = metrics.get(target.name)
                if value is None:
                    rendered_metrics.append(f"{target.name} n/a")
                    continue
                rendered = f"{target.name} {float(value):.3f}"
                baseline_value = (self._baseline_metrics or {}).get(target.name)
                if split == "validation" and has_baseline and baseline_value is not None:
                    delta = float(value) - baseline_value
                    improved = delta >= 0 if target.direction == "maximize" else delta <= 0
                    rendered += f" {'▲' if improved else '▼'}{delta:+.3f}"
                rendered_metrics.append(rendered)
            self._emit(f"   {label} · {split:<10} · {', '.join(rendered_metrics)}   → {artifacts}")
        except Exception:  # noqa: BLE001
            pass

    def run_finished(
        self,
        *,
        winner: str | None,
        scores: dict[str, float],
        report_path: Path | None,
    ) -> None:
        try:
            self._emit(_THIN)
            if winner is None:
                self._emit(" Finished · no winner (no scored candidates)")
            else:
                head = f" Finished · winner={winner}"
                rendered_metrics = [
                    f"{target.name} {float(scores[target.name]):.3f}"
                    for target in self._objective_metrics
                    if target.name in scores
                ]
                if rendered_metrics:
                    head += f" · validation {', '.join(rendered_metrics)}"
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
