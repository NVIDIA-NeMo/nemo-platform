# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run one evaluation of the hello-harbor-agent example, through either evaluator.

The evaluator seam only — no Coder, no Analyzer, no Proposer — so this needs
Docker but **no model API key**. Use it to A/B the two Harbor evaluator types:

    uv run plugins/nemo-experimentalist/docs/e2e/run-eval-only.py --evaluator-type harbor
    uv run plugins/nemo-experimentalist/docs/e2e/run-eval-only.py --evaluator-type harbor_agent_task_runner

Both should print the same aggregate: {"format_ok": 1.0, "reward": 0.5}.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path

from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import EvaluatorFactory
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset

_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "hello-harbor-agent"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--evaluator-type",
        default="harbor_agent_task_runner",
        choices=["harbor", "harbor_agent_task_runner"],
        help="Which evaluator orchestrates the Harbor run.",
    )
    parser.add_argument(
        "--split",
        default="validation",
        choices=["train", "validation"],
        help="Which split of the example dataset to evaluate.",
    )
    parser.add_argument(
        "--experiment-dir",
        type=Path,
        default=Path("tmp") / "eval-only",
        help="Where the agent copy and the Harbor job directory are written.",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Discard a cached job directory and re-run every trial.",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    experiment_dir = args.experiment_dir.resolve()

    # Mirror what the loop does: materialize the baseline as agent-0. The dataset
    # is deliberately not copied — the agent is evaluated against it, not shipped
    # with it.
    agent_dir = experiment_dir / "eval-and-optimize" / "agents" / "agent-0"
    if not agent_dir.exists():
        shutil.copytree(_EXAMPLE_DIR, agent_dir, ignore=shutil.ignore_patterns("dataset", "__pycache__"))

    dataset = HarborDataset.from_path(_EXAMPLE_DIR / "dataset" / args.split)
    evaluator = EvaluatorFactory().build_evaluator(
        args.evaluator_type,
        {"force_rerun": args.force_rerun},
        experiment_dir=experiment_dir,
    )
    result = await evaluator.run(agent_dir, dataset)

    print(f"\nevaluator:  {args.evaluator_type}")
    print(f"evaluation: {result.id}")
    print(f"aggregate:  {json.dumps(result.aggregate_metrics, sort_keys=True)}")
    for trial in sorted(result.trials, key=lambda trial: trial.task_id):
        metrics = {name: metric.value for name, metric in sorted(trial.metrics.items())}
        print(f"  {trial.task_id:<16} {trial.status:<9} {metrics}  trace={trial.trace is not None}")
    print(f"\njob dir:    {experiment_dir / 'eval-and-optimize' / 'results' / result.id}")


if __name__ == "__main__":
    asyncio.run(main())
