# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the additive run-progress reporter."""

from __future__ import annotations

import io
from pathlib import Path

from nemo_experimentalist_plugin.experimentalist.reporting import (
    RunReporter,
    Verbosity,
    reward_scalar,
)


def _reporter(verbosity: Verbosity = Verbosity.NORMAL) -> tuple[RunReporter, io.StringIO]:
    sink = io.StringIO()
    return RunReporter(sink=sink, verbosity=verbosity), sink


def test_run_started_emits_header_with_run_dir_and_insight() -> None:
    r, sink = _reporter()
    r.run_started(run_dir=Path("/exp/run-1"), agent="nemo-oo-airline", insight="insight-892a", strategy="evolutionary")
    out = sink.getvalue()
    assert "strategy=evolutionary" in out
    assert "agent=nemo-oo-airline" in out
    assert "/exp/run-1" in out
    assert "insight-892a" in out


def test_run_started_handles_missing_insight() -> None:
    r, sink = _reporter()
    r.run_started(run_dir=Path("/exp/run-1"), agent="a", insight=None, strategy="evolutionary")
    assert "dataset-driven" in sink.getvalue()


def test_progress_renders_fraction_and_bare_phase() -> None:
    r, sink = _reporter()
    r.progress(phase="baseline", completed=0, total=15)
    r.progress(phase="proposing candidates")
    out = sink.getvalue()
    assert "round 0/≤15" in out
    assert "baseline" in out
    assert "proposing candidates" in out


def test_candidate_evaluated_sets_baseline_then_shows_delta() -> None:
    r, sink = _reporter()
    r.candidate_evaluated(
        label="agent-0", split="validation", reward=0.05, artifacts=Path("/exp/results/agent-0-validation")
    )
    r.candidate_evaluated(
        label="agent-1", split="validation", reward=0.19, artifacts=Path("/exp/results/agent-1-validation")
    )
    lines = sink.getvalue().splitlines()
    assert "reward 0.050" in lines[0]
    assert "▲" not in lines[0]  # baseline has no delta
    assert "reward 0.190" in lines[1]
    assert "+0.140" in lines[1]  # delta vs baseline


def test_seed_baseline_sets_delta_reference_silently_for_resume() -> None:
    # On resume agent-0 is not re-evaluated; seed_baseline sets the delta
    # reference from its cached reward without emitting a line, so the first
    # newly evaluated candidate is measured against agent-0, not itself.
    r, sink = _reporter()
    r.seed_baseline(0.05)
    assert sink.getvalue() == ""  # silent: no line emitted
    r.candidate_evaluated(
        label="agent-1", split="validation", reward=0.19, artifacts=Path("/exp/results/agent-1-validation")
    )
    out = sink.getvalue()
    assert "reward 0.190" in out
    assert "+0.140" in out  # delta measured against the seeded 0.05 baseline


def test_seed_baseline_is_noop_once_baseline_set() -> None:
    r, sink = _reporter()
    r.candidate_evaluated(
        label="agent-0", split="validation", reward=0.05, artifacts=Path("/exp/results/agent-0-validation")
    )
    r.seed_baseline(0.99)  # must not clobber the real baseline
    r.candidate_evaluated(
        label="agent-1", split="validation", reward=0.19, artifacts=Path("/exp/results/agent-1-validation")
    )
    assert "+0.140" in sink.getvalue()  # still measured against 0.05, not 0.99


def test_train_split_shows_no_delta() -> None:
    r, sink = _reporter()
    r.candidate_evaluated(label="agent-0", split="train", reward=0.23, artifacts=Path("/exp/results/agent-0-train"))
    assert "▲" not in sink.getvalue()
    assert "▼" not in sink.getvalue()


def test_run_finished_winner_and_no_winner() -> None:
    r, sink = _reporter()
    r.candidate_evaluated(label="agent-0", split="validation", reward=0.05, artifacts=Path("/x"))
    r.run_finished(winner="agent-1", scores={"reward": 0.19}, report_path=Path("/exp/final_report.md"))
    out = sink.getvalue()
    assert "winner=agent-1" in out
    assert "validation 0.190" in out
    assert "baseline 0.050" in out
    assert "final_report.md" in out

    r2, sink2 = _reporter()
    r2.run_finished(winner=None, scores={}, report_path=None)
    assert "no winner" in sink2.getvalue()


def test_quiet_suppresses_phase_and_candidate_but_keeps_header_footer() -> None:
    r, sink = _reporter(Verbosity.QUIET)
    r.run_started(run_dir=Path("/x"), agent="a", insight=None, strategy="evolutionary")
    r.progress(phase="baseline", completed=0, total=15)
    r.candidate_evaluated(label="agent-0", split="validation", reward=0.05, artifacts=Path("/x"))
    r.run_finished(winner="agent-0", scores={"reward": 0.05}, report_path=None)
    out = sink.getvalue()
    assert "strategy=evolutionary" in out  # header kept
    assert "winner=agent-0" in out  # footer kept
    assert "baseline" not in out  # phase suppressed
    assert "reward 0.050" not in out  # candidate suppressed


def test_methods_never_raise_on_broken_sink() -> None:
    class BrokenSink(io.StringIO):
        def write(self, s: str) -> int:  # type: ignore[override]
            raise OSError("sink is broken")

    r = RunReporter(sink=BrokenSink())
    # None of these may raise:
    r.run_started(run_dir=Path("/x"), agent="a", insight=None, strategy="s")
    r.progress(phase="p", completed=1, total=2)
    r.candidate_started(label="agent-1", optimization="x", i=1, n=3)
    r.candidate_evaluated(label="agent-1", split="validation", reward=0.1, artifacts=Path("/x"))
    r.run_finished(winner="agent-1", scores={"reward": 0.1}, report_path=None)
    r.note("hello")


def test_reward_scalar_defaults_to_zero_when_absent() -> None:
    assert reward_scalar({"reward": 0.42}) == 0.42
    assert reward_scalar({}) == 0.0


def test_candidate_evaluated_renders_subset_style_result_id_verbatim() -> None:
    sink = io.StringIO()
    r = RunReporter(sink=sink)
    # Real candidate train dirs look like agent-1-train-subset-1-<sha>, not agent-1-train.
    r.candidate_evaluated(
        label="agent-1",
        split="train",
        reward=0.2,
        artifacts=Path("/exp/results/agent-1-train-subset-1-42e2eab5a4e0"),
    )
    assert "agent-1-train-subset-1-42e2eab5a4e0" in sink.getvalue()


def test_full_run_transcript_is_the_loop_emission_contract() -> None:
    # This scripts the exact sequence loop.py must emit, locking the contract
    # the wiring tasks implement.
    r, sink = _reporter()
    r.run_started(run_dir=Path("/exp/run-1"), agent="nemo-oo-airline", insight="insight-892a", strategy="evolutionary")
    r.progress(phase="baseline", completed=0, total=15)
    r.candidate_evaluated(
        label="agent-0", split="validation", reward=0.05, artifacts=Path("/exp/results/agent-0-validation")
    )
    r.candidate_evaluated(label="agent-0", split="train", reward=0.23, artifacts=Path("/exp/results/agent-0-train"))
    r.progress(phase="evaluating candidates", completed=1, total=15)
    r.candidate_started(label="agent-1", optimization="ground tool signatures", i=1, n=3)
    r.candidate_evaluated(
        label="agent-1", split="validation", reward=0.19, artifacts=Path("/exp/results/agent-1-validation")
    )
    r.run_finished(winner="agent-1", scores={"reward": 0.19}, report_path=Path("/exp/final_report.md"))
    out = sink.getvalue()
    # ordering sanity: baseline before round-1 before finish
    assert out.index("baseline") < out.index("evaluating candidates") < out.index("Finished")
    # candidate_started narrates work beginning, so it precedes its evaluation line
    assert out.index("ground tool signatures") < out.index("agent-1 · validation")
    assert "agent-1 · validation" in out
    assert "+0.140" in out


def test_build_run_reporter_emits_header_and_is_reusable() -> None:
    from nemo_experimentalist_plugin.experimentalist.run import build_run_reporter

    sink = io.StringIO()
    reporter = build_run_reporter(
        run_dir=Path("/exp/run-2"),
        agent="nemo-oo-airline",
        insight="insight-892a",
        sink=sink,
    )
    out = sink.getvalue()
    assert "strategy=evolutionary" in out  # default strategy
    assert "/exp/run-2" in out
    # returned reporter is live and usable for later verbs
    reporter.progress(phase="baseline", completed=0, total=15)
    assert "baseline" in sink.getvalue()


def test_deps_accepts_a_reporter() -> None:
    from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
    from nemo_experimentalist_plugin.experimentalist.deps import ExperimentalistDeps

    reporter = RunReporter(sink=io.StringIO())
    deps = ExperimentalistDeps(
        workspace="w",
        reporter=reporter,
        insight=Path("/test/insight"),
        train_dataset=DatasetRef(uri="test-train"),
        validation_dataset=DatasetRef(uri="test-val"),
        task_template=DatasetRef(uri="test-task"),
    )
    assert deps.reporter is reporter
