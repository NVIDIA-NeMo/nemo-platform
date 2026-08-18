# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Step through the four layers between a Harbor verifier and the reward the loop ranks on.

A missing ``/logs/verifier/reward.txt`` is invisible by the time it reaches the
operator: the run prints ``reward n/a`` and keeps going. This tool prints the
state at every layer the value passes through, so you can see which one drops it
and which one is entitled to complain.

The layers, in order:

1. **on disk** — what the verifier left in the trial directory.
2. ``trials_from_job_dir`` — the ``TrialResult`` status and metrics parsed from it.
3. ``Evaluator.aggregate_results`` — the per-candidate aggregate the loop stores.
4. ``missing_objective_reason`` / ``RunReporter`` — the lines an operator reads.
   ``reward_scalar`` is printed alongside them because it looks like the loop's
   scalar reward, but no caller in the loop uses it.
5. ``pareto_objectives`` / ``has_metric_dimensions`` — the projection the selector
   ranks on and the predicate the selector and terminator share, which together
   decide whether the loop can compare candidates or stop early.

Every layer is called through production code. Nothing here is imported by the
plugin; this is a read-only inspector for humans.

Usage::

    # Compare synthetic trial shapes side by side.
    uv run plugins/nemo-experimentalist/tools/reward_pipeline_inspector.py

    # One shape only.
    uv run plugins/nemo-experimentalist/tools/reward_pipeline_inspector.py \
        --scenario verifier-silent

    # Inspect a real Harbor job directory from a run that reported `reward n/a`.
    uv run plugins/nemo-experimentalist/tools/reward_pipeline_inspector.py \
        --job-dir eval-and-optimize/results/agent-0-validation
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from nemo_experimentalist_plugin.entities import Dataset, MetricTarget, Task, TrialResult
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    Evaluator,
    EvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import trials_from_job_dir
from nemo_experimentalist_plugin.experimentalist.components.models import (
    has_metric_dimensions,
    missing_objective_reason,
    pareto_objectives,
)
from nemo_experimentalist_plugin.experimentalist.reporting import RunReporter, reward_scalar

_OBJECTIVES = [MetricTarget(name="reward", direction="maximize")]


class _AggregateOnlyEvaluator(Evaluator):
    """The real ``aggregate_results``, with the abstract run step stubbed out."""

    evaluator_type = "reward-pipeline-inspector"

    async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
        """Never called: the inspector adapts a job directory that already exists."""
        raise NotImplementedError("The inspector reads an existing job directory; it never runs an evaluation.")


@dataclass(frozen=True)
class TrialSpec:
    """One synthetic trial: its task, the reward it wrote, and any Harbor exception."""

    task: str
    reward_text: str | None = None
    exception_type: str | None = None


@dataclass(frozen=True)
class Scenario:
    """One synthetic trial shape, plus what the verifier did to produce it."""

    name: str
    verifier_behaviour: str
    trials: tuple[TrialSpec, ...]


SCENARIOS = (
    Scenario(
        name="reward-written",
        verifier_behaviour="test.sh writes /logs/verifier/reward.txt. The control case.",
        trials=(TrialSpec("task-a", reward_text="1.0"), TrialSpec("task-b", reward_text="0.0")),
    ),
    Scenario(
        name="verifier-raised",
        verifier_behaviour=(
            "test.sh exits 0 without writing a reward file, so Harbor's verifier raises "
            "RewardFileNotFoundError and the trial records exception_info."
        ),
        trials=(TrialSpec("task-a", exception_type="RewardFileNotFoundError"),),
    ),
    Scenario(
        name="verifier-silent",
        verifier_behaviour=(
            "The trial finishes with no exception and no reward file — a disabled verifier, "
            "a bind mount that never reflected the write, or a reward stripped during log collection."
        ),
        trials=(TrialSpec("task-a"), TrialSpec("task-b")),
    ),
    Scenario(
        name="partial",
        verifier_behaviour="One task writes a reward and another does not.",
        trials=(TrialSpec("task-a", reward_text="1.0"), TrialSpec("task-b")),
    ),
    Scenario(
        name="thin-denominator",
        verifier_behaviour=(
            "One easy task scores 1.0 and three harder tasks crash before their verifier runs. "
            "The reward survives; the sample it was averaged over does not."
        ),
        trials=(
            TrialSpec("task-easy", reward_text="1.0"),
            TrialSpec("task-hard-1", exception_type="AgentTimeoutError"),
            TrialSpec("task-hard-2", exception_type="AgentTimeoutError"),
            TrialSpec("task-hard-3", exception_type="NonZeroAgentExitCodeError"),
        ),
    ),
)


def materialize(scenario: Scenario, root: Path) -> Path:
    """Write *scenario* as a Harbor job directory and return it."""
    job_dir = root / scenario.name
    for index, spec in enumerate(scenario.trials):
        trial_dir = job_dir / f"{spec.task}__{index}"
        trial_dir.mkdir(parents=True)
        (trial_dir / "result.json").write_text(
            json.dumps(
                {
                    "task_name": f"harbor/{spec.task}",
                    "trial_name": trial_dir.name,
                    "verifier_result": None,
                    "exception_info": (
                        None
                        if spec.exception_type is None
                        else {
                            "exception_type": spec.exception_type,
                            "exception_message": "No reward file found at /logs/verifier/reward.txt",
                            "exception_traceback": "<elided>",
                        }
                    ),
                }
            ),
            encoding="utf-8",
        )
        verifier_dir = trial_dir / "verifier"
        verifier_dir.mkdir()
        (verifier_dir / "test-stdout.txt").write_text("tests passed\n", encoding="utf-8")
        if spec.reward_text is not None:
            (verifier_dir / "reward.txt").write_text(spec.reward_text, encoding="utf-8")
    return job_dir


def _describe_on_disk(job_dir: Path) -> list[str]:
    """One line per trial directory: its reward files, recorded rewards, and exception."""
    lines = []
    for trial_dir in sorted(path for path in job_dir.iterdir() if path.is_dir()):
        result_path = trial_dir / "result.json"
        if not result_path.is_file():
            lines.append(f"{trial_dir.name}: no result.json (this directory is skipped entirely)")
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        rewards = (result.get("verifier_result") or {}).get("rewards")
        exception_info = result.get("exception_info") or {}
        files = [
            name
            for name in ("verifier/reward.json", "verifier/reward.txt", "reward.json", "reward.txt")
            if (trial_dir / name).is_file()
        ]
        lines.append(
            f"{trial_dir.name}: reward files={files or 'none'} · "
            f"result.json rewards={rewards if rewards else 'none'} · "
            f"exception={exception_info.get('exception_type', 'none')}"
        )
    return lines


def _reporter_lines(metrics: dict[str, float | int], reason: str | None) -> list[str]:
    """The lines `ExperimentContext.evaluate` would narrate for this aggregate."""
    sink = io.StringIO()
    RunReporter(sink=sink).candidate_evaluated(
        label="agent-0",
        split="validation",
        metrics=metrics,
        objective_metrics=_OBJECTIVES,
        artifacts=Path("eval-and-optimize/results/agent-0-validation"),
        reason=reason,
    )
    return [line.strip() for line in sink.getvalue().splitlines()]


async def inspect(job_dir: Path, *, behaviour: str | None = None) -> None:
    """Print the state of every layer between *job_dir* and the loop's scalar reward."""
    print(f"\n{'=' * 78}\n{job_dir.name}\n{'=' * 78}")
    if behaviour is not None:
        print(f"verifier: {behaviour}\n")

    print("[1] on disk")
    for line in _describe_on_disk(job_dir):
        print(f"    {line}")

    task_ids = sorted({path.name.rsplit("__", 1)[0] for path in job_dir.iterdir() if path.is_dir()})
    trials = trials_from_job_dir(job_dir, [Task(id=task_id) for task_id in task_ids])
    print("\n[2] trials_from_job_dir")
    for trial in trials:
        metrics = {name: metric.value for name, metric in trial.metrics.items()}
        error = (trial.error or {}).get("type", "none")
        print(f"    {trial.id}: status={trial.status} metrics={metrics or '{}'} error={error}")

    print("\n[3] Evaluator.aggregate_results")
    try:
        aggregate = await _AggregateOnlyEvaluator(EvaluatorConfig()).aggregate_results(trials)
    except ValueError as exc:
        print(f"    raises ValueError: {exc}")
        print("\n[4] reward_scalar / RunReporter")
        print("    not reached — the run fails here, which is the loud case")
        return
    completed = [trial for trial in trials if trial.status == "completed"]
    print(f"    completed trials={len(completed)}/{len(trials)} · aggregate={aggregate or '{}'}")

    reason = missing_objective_reason(trials, aggregate, _OBJECTIVES)
    print("\n[4] reward_scalar / RunReporter")
    print(f"    reward_scalar={reward_scalar(aggregate)!r}   (defined in reporting.py; no caller in the loop)")
    print("    operator sees:")
    for line in _reporter_lines(aggregate, reason):
        print(f"      {line}")

    metrics = {name: float(value) for name, value in aggregate.items()}
    print("\n[5] pareto_objectives / has_metric_dimensions (what the loop really ranks on)")
    print(f"    pareto_objectives={pareto_objectives(metrics, _OBJECTIVES) or '{}'}")
    print(f"    has_metric_dimensions={has_metric_dimensions(metrics, _OBJECTIVES)}")
    if reason is None:
        print("    the selector can rank, the terminator can detect a stagnant front, and a winner exists")
        return
    # Which of these applies depends on whose evaluation this is, and the job
    # directory alone cannot say.
    print("    as the baseline's validation: the run stops here, because nothing measured the starting point")
    print("    as a later candidate:         it projects to {}, so _dominates is False against every peer")
    print("                                  and it can never be ranked or win, but the run continues")


async def main() -> None:
    """Inspect a real job directory, or the synthetic scenarios when none is given."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--job-dir",
        type=Path,
        help="Inspect a real Harbor job directory instead of the synthetic scenarios.",
    )
    parser.add_argument(
        "--scenario",
        choices=[scenario.name for scenario in SCENARIOS],
        help="Run one synthetic scenario instead of all of them.",
    )
    args = parser.parse_args()

    if args.job_dir is not None:
        await inspect(args.job_dir.expanduser().resolve())
        return

    selected = [s for s in SCENARIOS if args.scenario is None or s.name == args.scenario]
    with tempfile.TemporaryDirectory(prefix="reward-pipeline-") as tmp:
        for scenario in selected:
            job_dir = materialize(scenario, Path(tmp))
            await inspect(job_dir, behaviour=scenario.verifier_behaviour)


if __name__ == "__main__":
    asyncio.run(main())
