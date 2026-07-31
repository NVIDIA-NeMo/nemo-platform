# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live end-to-end: run an existing NeMo Gym environment through NeMo Evaluator.

Points the Gym runner (:class:`GymAgentTaskRunner`) at an installed Gym checkout and runs a dataset
(mcqa's bundled ``example.jsonl`` by default) via the two-step Gym flow — ``gym env start`` brings up
the resources-server + agent + model servers, then ``gym eval run --no-serve --input`` collects
rollouts against them — and scores the result with :class:`AgentEvaluator`. Gym owns execution *and*
scoring; :class:`GymRewardMetric` surfaces the per-attempt reward (Evaluator does not re-derive it).

One Gym dataset → one run; each distinct row → one task (id = content hash of the row); each attempt
(``num_repeats``) → one trial. The runner materializes the tasks into a normalized dataset with
``_ng_task_index`` stamped per row and hands *that* to Gym, which honors the stamp — so rollouts join
back to tasks by an explicit map rather than by position (see the README).

Prerequisites (see README.md):

* A **NeMo Gym checkout** whose venv has the target env's deps installed — each env ships its own
  ``requirements.txt`` (mcqa needs ``tiktoken``; Gym itself needs ``ray`` and ``uv >= 0.9.30``).
* A **gitignored ``<gym_root>/env.yaml``** holding the model credentials the collector calls
  (``policy_base_url`` / ``policy_api_key`` / ``policy_model_name``). This SDK never handles secrets —
  the ``gym`` subprocess reads them from that file.

Run from the repository root::

    python -m packages.nemo_evaluator_sdk.examples.gym.run_gym_eval --gym-root /path/to/Gym
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.gym_runtime import (
    GymAgentTaskRunner,
    GymRuntimeConfig,
    discover_gym_tasks,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--gym-root", required=True, type=Path, help="NeMo Gym checkout; its venv + env.yaml provide deps/creds."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Dataset jsonl (default: <gym-root>/resources_servers/<resources-server>/data/example.jsonl).",
    )
    parser.add_argument("--resources-server", default="mcqa", help="Gym resources-server (environment) name.")
    parser.add_argument("--agent", default="simple_agent", help="Agent to collect rollouts with.")
    parser.add_argument(
        "--agent-config",
        default="responses_api_agents/simple_agent/configs/simple_agent.yaml",
        help="Repo-relative agent config passed to `gym env start`.",
    )
    parser.add_argument(
        "--model-type",
        default="inference_provider",
        help="`inference_provider` speaks OpenAI-compatible chat; `openai_model` uses the Responses API.",
    )
    parser.add_argument("--num-repeats", type=int, default=2, help="Attempts per task (each becomes a trial).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where the run bundle is written (default: a fresh temporary directory). Each run needs its own "
        "directory — the runner refuses to reuse one that already holds Gym rollout output.",
    )
    return parser.parse_args(argv)


async def _main(args: argparse.Namespace) -> int:
    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="gym-eval-"))
    dataset = args.dataset or (args.gym_root / "resources_servers" / args.resources_server / "data" / "example.jsonl")
    tasks = discover_gym_tasks(dataset)
    print(f"discovered {len(tasks)} tasks from {dataset}")

    runner = GymAgentTaskRunner(
        config=GymRuntimeConfig(
            gym_root=args.gym_root,
            agent=args.agent,
            agent_config=args.agent_config,
            resources_server=args.resources_server,
            model_type=args.model_type,
            num_repeats=args.num_repeats,
        )
    )

    result = await AgentEvaluator().run(
        tasks=tasks,
        target=runner,
        config=AgentEvalRunConfig(output_dir=output_dir, parallelism=1),
    )

    print("=== RESULT ===")
    print(f"tasks: {result.summary.task_count}  trials: {result.summary.trial_count}")
    print("aggregate scores:")
    for aggregate in result.summary.scores.scores:
        print(f"  {aggregate.name}: mean={aggregate.mean}")
    print(f"\nRun bundle (run.json, trials.jsonl, scores.jsonl, report.html): {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(_parse_args())))
