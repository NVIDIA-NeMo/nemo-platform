# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run a Harbor dataset through the SDK's native Harbor runtime.

The point of this example is how *little* plumbing the caller needs: apart from
imports, running a whole Harbor local dataset is two lines — build a
:class:`HarborRuntimeConfig`, call :func:`run_harbor_eval`. The SDK builds and
runs Harbor's ``JobConfig`` and scores the results; the caller never imports
``harbor`` or assembles a job.

Two modes, both over the bundled ``hello_world_dataset`` (Harbor's ``hello-world``
task) scored with the deterministic **oracle** agent, so no LLM/API key is needed:

* ``--mode native`` — print the SDK summary.
* ``--mode optimizer`` — collapse the result into NeMo Optimizer's legacy
  ``{reward, reward_details, exceptions}`` payload.

Running either mode requires ``harbor`` installed and a working Docker daemon.

Run it as a module from the repository root::

    python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode native
    python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode optimizer
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
    HarborRuntimeConfig,
    reward_payload_from_result,
    run_harbor_eval,
)

logger = logging.getLogger(__name__)

# A Harbor "local dataset" is a directory whose immediate subdirectories are task
# folders. Point the runtime at it and every task is discovered, run, and scored.
HELLO_WORLD_DATASET_DIR = Path(__file__).resolve().parent / "hello_world_dataset"


async def _main(mode: str, jobs_dir: Path) -> None:
    # The entire caller-side plumbing: a config and one call.
    config = HarborRuntimeConfig(jobs_dir=jobs_dir, agent_name="oracle")
    result = await run_harbor_eval(config, HELLO_WORLD_DATASET_DIR)

    if mode == "optimizer":
        print("Legacy optimizer reward payload:")
        print(json.dumps(reward_payload_from_result(result), indent=2, sort_keys=True))
        return

    print(f"run_id: {result.run_id}  tasks: {result.summary.task_count}  trials: {result.summary.trial_count}")
    for aggregate in result.summary.scores.scores:
        print(f"  {aggregate.name}: mean={aggregate.mean}")
    for score in result.scores:
        reward = score.outputs[0].value if score.outputs else None
        print(f"  {score.task_id}: reward={reward} status={score.status.value}")


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
