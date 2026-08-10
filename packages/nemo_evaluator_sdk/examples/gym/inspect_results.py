# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read and display the results of an agent-eval run.

Companion to ``run_gym_eval.py``: that script *produces* a run bundle, this one *reads* it and shows
how to get at each kind of result — headline aggregates, ``pass@k``, per-task outcomes, and the
runner's own aggregations.

The helpers below (:func:`aggregate`, :func:`per_task_outcomes`) are written to be lifted directly
into your own code. Everything shown here also works on the in-memory ``AgentEvalResult`` returned by
``AgentEvaluator().run(...)`` — reading from a bundle just makes the example runnable without a live
run.

There is no bundle checked into the repo — ``run_gym_eval.py`` makes one. It writes to a fresh
temporary directory by default, so give it an explicit ``--output-dir`` and point this script at the
same path. From the repository root::

    uv run python -m packages.nemo_evaluator_sdk.examples.gym.run_gym_eval \\
        --output-dir /tmp/gym-eval
    uv run python -m packages.nemo_evaluator_sdk.examples.gym.inspect_results --bundle /tmp/gym-eval

Any agent-eval bundle works, not just a Gym one: pass ``--metric-type``/``--output-name`` for the
metric it was scored with. Only the ``runner.gym.`` section is Gym-specific, and it is skipped when a
run has no imported aggregations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.results import AgentEvalSummary
from nemo_evaluator_sdk.values.results import AggregateScalarScore, AggregateScore

#: Value at which an attempt counts as a pass, matching the SDK's pass@k definition (full credit).
PASS_VALUE = 1.0

#: Namespace the Gym runner's own aggregations are imported under, so they never collide with ours.
RUNNER_PREFIX = "runner.gym."

# --------------------------------------------------------------------------------------------------
# Accessors — lift these into your own code.
# --------------------------------------------------------------------------------------------------


def aggregate(summary: AgentEvalSummary, name: str) -> AggregateScore:
    """Look up one aggregate by name, e.g. ``"gym_reward.reward.pass@2"``.

    Aggregates are a flat list, so this is a scan. Raises with the available names on a miss, which is
    the failure you actually want when a metric or output was renamed.
    """
    for score in summary.scores.scores:
        if score.name == name:
            return score
    available = ", ".join(sorted(score.name for score in summary.scores.scores))
    raise KeyError(f"no aggregate named {name!r}; available: {available}")


def per_task_outcomes(
    summary: AgentEvalSummary,
    *,
    metric_type: str,
    output_name: str,
) -> dict[str, list[float | None]]:
    """Read ordered attempt values from the summary for one metric output.

    ``None`` is a failed trial and therefore a failed attempt. An empty list means the task had no
    usable measurement because its metric failed or omitted the output.
    """
    key = f"{metric_type}.{output_name}"
    return {
        task_id: list(metric_values[key])
        for task_id, metric_values in summary.task_metric_values.items()
        if key in metric_values
    }


# --------------------------------------------------------------------------------------------------
# Bundle loading (see the run.json manifest for the full artifact list).
# --------------------------------------------------------------------------------------------------


def load_bundle(bundle: Path) -> AgentEvalSummary:
    """Load the persisted summary, including native and runner aggregates and per-task attempts."""
    return AgentEvalSummary.model_validate(json.loads((bundle / "summary.json").read_text(encoding="utf-8")))


# --------------------------------------------------------------------------------------------------
# Display
# --------------------------------------------------------------------------------------------------


def headline_value(score: AggregateScore) -> float | None:
    """The one number for an aggregate: a scalar's ``value``, otherwise the mean of its distribution.

    Scores named ``runner.<name>.*`` came from the runner rather than being computed here, and a
    backend that reports a single figure (no underlying distribution) arrives as an
    :class:`AggregateScalarScore` with no ``mean`` — so reading ``mean`` alone would show nothing.
    """
    return score.value if isinstance(score, AggregateScalarScore) else score.mean


def show_aggregates(summary: AgentEvalSummary) -> None:
    print("Aggregates ('runner.*' are the runner's own numbers, imported)")
    print(f"  {'name':<40} {'value':>8} {'count':>6} {'nan':>5}")
    for score in sorted(summary.scores.scores, key=lambda item: item.name):
        value = headline_value(score)
        shown = "—" if value is None else f"{value:.3f}"
        # None means the producer didn't report a sample size; a real 0 means every sample was NaN.
        count = "—" if score.count is None else str(score.count)
        print(f"  {score.name:<40} {shown:>8} {count:>6} {score.nan_count:>5}")
    print(f"\n  {summary.task_count} tasks · {summary.trial_count} trials · {summary.score_count} scores")


def show_per_task(by_task: dict[str, list[float | None]]) -> None:
    """Per-task outcomes: which tasks were solved, and how consistently.

    An attempt passes on full credit (``>= PASS_VALUE``), matching how the SDK computes pass@k. A
    ``None`` is a trial that died: it counts as an attempt and never as a pass, so a task that passed
    once and crashed once reads as flaky rather than solved.
    """
    print("\nPer-task outcomes (attempt values; an attempt passes at full credit)")
    solved = flaky = failed = unmeasured = 0
    for task_id, values in sorted(by_task.items()):
        if not values:
            verdict, marker = "unmeasured", "?"
            unmeasured += 1
            attempts = ""
        else:
            passes = sum(1 for value in values if value is not None and value >= PASS_VALUE)
            if passes == len(values):
                verdict, marker = "solved", "+"
                solved += 1
            elif passes:
                verdict, marker = f"flaky ({passes}/{len(values)})", "~"
                flaky += 1
            else:
                verdict, marker = "failed", "-"
                failed += 1
            attempts = ", ".join("died" if value is None else f"{value:g}" for value in values)
        print(f"  {marker} {task_id[:16]}…  [{attempts}]  {verdict}")
    print(f"\n  {solved} solved · {flaky} flaky · {failed} failed · {unmeasured} unmeasured")


def show_runner_aggregations(summary: AgentEvalSummary) -> None:
    """The runner's own numbers, plus a cross-check against the SDK's native aggregates.

    Imported figures sit in the same ``summary.scores`` list as everything else, distinguished only by
    the ``runner.`` prefix — so they are read exactly like the natively-computed ones. Units and names
    stay the runner's own: Gym reports accuracy on a 0-100 scale where the SDK uses 0-1.
    """
    imported = [score for score in summary.scores.scores if score.name.startswith(RUNNER_PREFIX)]
    if not imported:
        print("\nNo runner-provided aggregations (this runner doesn't supply any).")
        return

    print("\nRunner-provided aggregations (imported into summary.scores)")
    for score in sorted(imported, key=lambda item: item.name):
        value = headline_value(score)
        shown = "—" if value is None else f"{value:g}"
        print(f"      {score.name[len(RUNNER_PREFIX) :]:<34} {shown}")

    # Cross-check: the SDK computes pass@k natively from the trials; Gym computes its own. They should
    # agree once you normalise the scale.
    try:
        native = aggregate(summary, "gym_reward.reward.pass@1").mean
        reported = headline_value(aggregate(summary, f"{RUNNER_PREFIX}pass@1/accuracy"))
    except KeyError:
        return
    if native is not None and reported is not None:
        agreement = "agree" if abs(native - reported / 100) < 1e-9 else "DIFFER"
        print(f"\n  cross-check pass@1: native={native:.3f} · runner={reported / 100:.3f} (0-100 scale) -> {agreement}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", type=Path, default=Path("/tmp/gym-eval"), help="Run bundle directory to read.")
    parser.add_argument("--metric-type", default="gym_reward", help="Metric type to break down per task.")
    parser.add_argument("--output-name", default="reward", help="Metric output to break down per task.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not (args.bundle / "summary.json").exists():
        raise SystemExit(f"{args.bundle} is not a run bundle (no summary.json). Run run_gym_eval.py first.")

    summary = load_bundle(args.bundle)

    show_aggregates(summary)
    by_task = per_task_outcomes(summary, metric_type=args.metric_type, output_name=args.output_name)
    if by_task:
        show_per_task(by_task)
    show_runner_aggregations(summary)

    print(f"\nFull report: {args.bundle / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
