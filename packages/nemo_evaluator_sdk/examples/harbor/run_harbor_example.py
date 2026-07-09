# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run a Harbor job through the SDK's dependency-light Harbor runtime.

Two runnable modes, both over the bundled ``hello_world_task`` (a copy of
Harbor's ``hello-world`` task) scored with the deterministic **oracle** agent so
no LLM/API key is needed:

* ``--mode native`` — the plain path: build a Harbor :class:`JobConfig`, wrap
  ``job.run()`` in the ``run_job`` callback the SDK's
  :class:`HarborAgentTaskRunner` expects, and score it through
  :class:`AgentEvaluator` + :class:`HarborRewardMetric`.
* ``--mode optimizer`` — mirrors how NeMo Optimizer consumes Harbor: run the
  same job, then collapse the scored :class:`AgentEvalResult` back into the
  legacy ``{reward, reward_details, exceptions}`` payload via
  :func:`reward_payload_from_result`.

Harbor is imported lazily inside :func:`build_hello_world_job_runner` so this
module stays importable (e.g. from the e2e test) even when ``harbor`` is not
installed. Running either mode requires ``harbor`` and a working Docker daemon.

Run it as a module from the repository root::

    python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode native
    python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode optimizer
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import tomllib
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
    HarborAgentTaskRunner,
    HarborRewardMetric,
    reward_payload_from_result,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask

logger = logging.getLogger(__name__)

# A Harbor "local dataset" is just a directory whose immediate subdirectories are
# task folders (each with task.toml, environment/, tests/, solution/). Pointing a
# DatasetConfig at this directory is exactly how user Harbor tasks are found: Harbor
# scans the subdirs and runs every valid task. Drop more task folders in here and
# both Harbor and this example pick them up with no code changes.
HELLO_WORLD_DATASET_DIR = Path(__file__).resolve().parent / "hello_world_dataset"

# Each task's ``task.toml`` declares ``[task] name`` (here "harbor/hello-world").
# Harbor stamps that exact string onto each trial's ``result.json["task_name"]``,
# and ``build_trials_from_job_dir`` matches trials to tasks by equality, so each
# AgentEvalTask id must be the full task name (not the "hello-world" dir leaf).
HELLO_WORLD_TASK_NAME = "harbor/hello-world"


def discover_tasks(dataset_dir: Path) -> list[AgentEvalTask]:
    """Build one :class:`AgentEvalTask` per Harbor task folder in ``dataset_dir``.

    Mirrors Harbor's own local-dataset discovery: every immediate subdirectory
    that contains a ``task.toml`` is a task. The AgentEvalTask id is read from
    ``[task] name`` so it matches the ``task_name`` Harbor writes into each
    trial's ``result.json``.

    Args:
        dataset_dir: Directory whose subdirectories are Harbor task folders.

    Returns:
        One scoring task per discovered Harbor task, ordered by directory name.
    """
    tasks: list[AgentEvalTask] = []
    for task_dir in sorted(p for p in dataset_dir.iterdir() if (p / "task.toml").is_file()):
        config = tomllib.loads((task_dir / "task.toml").read_text())
        task_name = config.get("task", {}).get("name", task_dir.name)
        instruction_path = task_dir / "instruction.md"
        intent = instruction_path.read_text().strip() if instruction_path.is_file() else task_name
        tasks.append(
            AgentEvalTask(
                id=task_name,
                intent=intent,
                inputs={"instruction": intent},
                metrics=[HarborRewardMetric()],
            )
        )
    return tasks


def build_hello_world_job_runner(
    jobs_dir: Path,
    *,
    dataset_dir: Path = HELLO_WORLD_DATASET_DIR,
    job_name: str = "harbor-hello-world",
    agent_import_path: str | None = None,
) -> tuple[HarborAgentTaskRunner, list[AgentEvalTask]]:
    """Build a :class:`HarborAgentTaskRunner` and the tasks it will score.

    Points a Harbor :class:`JobConfig` at ``dataset_dir`` — a directory of task
    folders — so Harbor discovers and runs every task in it, the same way user
    Harbor task collections are found. The returned runner's ``run_job`` callback
    creates and runs that job; ``build_hello_world_job_runner`` owns the Harbor
    ``JobConfig`` build (the SDK runtime never imports Harbor), and the runner only
    reads the job's on-disk ``result.json`` files afterward.

    Args:
        jobs_dir: Parent directory Harbor writes the ``<job_name>/`` tree into.
        dataset_dir: Harbor local-dataset directory whose subfolders are tasks
            (defaults to the bundled ``hello_world_dataset``).
        job_name: Harbor job name; also the results subdirectory name.
        agent_import_path: When set, run a custom Harbor agent via
            ``AgentConfig(import_path=...)`` (the NeMo Optimizer path). When
            ``None``, use Harbor's deterministic ``oracle`` agent so the run
            needs no model or API key.

    Returns:
        A ``(runner, tasks)`` pair ready to pass to ``AgentEvaluator.run``.
    """
    from harbor.job import DatasetConfig, Job, JobConfig  # ty: ignore[unresolved-import]
    from harbor.models.job.config import AgentConfig  # ty: ignore[unresolved-import]

    if agent_import_path is not None:
        agent = AgentConfig(import_path=agent_import_path)
    else:
        agent = AgentConfig(name="oracle")

    job_config = JobConfig(
        job_name=job_name,
        jobs_dir=jobs_dir,
        quiet=True,
        agents=[agent],
        datasets=[DatasetConfig(path=dataset_dir)],
    )
    job_dir = job_config.jobs_dir / job_config.job_name

    async def run_job() -> None:
        job = await Job.create(job_config)
        await job.run()

    runner = HarborAgentTaskRunner(job_dir=job_dir, run_job=run_job)
    return runner, discover_tasks(dataset_dir)


async def run_native(jobs_dir: Path) -> AgentEvalResult:
    """Run the hello-world Harbor job and score it through the SDK."""
    runner, tasks = build_hello_world_job_runner(jobs_dir)
    result = await AgentEvaluator().run(
        tasks=tasks,
        target=runner,
        config=AgentEvalRunConfig(write_dashboard=False),
    )
    print(f"run_id: {result.run_id}  tasks: {result.summary.task_count}  trials: {result.summary.trial_count}")
    for aggregate in result.summary.scores.scores:
        print(f"  {aggregate.name}: mean={aggregate.mean}")
    for score in result.scores:
        reward = score.outputs[0].value if score.outputs else None
        print(f"  {score.task_id}: reward={reward} status={score.status.value}")
    return result


async def run_optimizer_style(jobs_dir: Path) -> dict:
    """Run the same job, then rebuild NeMo Optimizer's legacy reward payload."""
    runner, tasks = build_hello_world_job_runner(jobs_dir)
    result = await AgentEvaluator().run(
        tasks=tasks,
        target=runner,
        config=AgentEvalRunConfig(write_dashboard=False),
    )
    payload = reward_payload_from_result(result)
    print("Legacy optimizer reward payload:")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


async def _main(mode: str, jobs_dir: Path) -> None:
    if mode == "native":
        await run_native(jobs_dir)
    else:
        await run_optimizer_style(jobs_dir)


if __name__ == "__main__":
    if __package__ in {None, ""}:
        raise SystemExit(
            "Run this example as a module from the repository root:\n"
            "  python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode native"
        )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["native", "optimizer"], default="native")
    parser.add_argument(
        "--jobs-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "harbor-example-output",
        help="Directory Harbor writes its job results into.",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.mode, args.jobs_dir))
