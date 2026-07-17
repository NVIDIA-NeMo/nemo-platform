# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run an agent evaluation through the Docker Codex CLI evidence path.

Prerequisites:

* Docker is installed and the daemon is running.
* ``codex login`` has created ``~/.codex/auth.json``. Set ``CODEX_AUTH_PATH``
  when the auth file lives elsewhere.

Run from the repository root with::

    uv run python packages/nemo_evaluator_sdk/examples/codex_docker/example.py

Run bundles are stored under ``temp/codex-docker-eval-output`` by default.
Set ``CODEX_DOCKER_EVAL_OUTPUT_ROOT`` to use a different location.

The example deliberately reads a nested file through the trial's ``workspace``
evidence descriptor. A successful score therefore exercises the Docker bind mount,
post-run ownership/permission normalization, private-tree validation, final-output
publication, and metric-side filesystem evidence access.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from nemo_evaluator_sdk import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import CodexDockerCliAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentTaskRunner

EXPECTED_TEXT = "codex docker evidence works"
ARTIFACT_PATH = "sanity/result.txt"
CODEX_AUTH_PATH_ENV_NAME = "CODEX_AUTH_PATH"
CODEX_MODEL_ENV_NAME = "CODEX_MODEL"
OUTPUT_ROOT_ENV_NAME = "CODEX_DOCKER_EVAL_OUTPUT_ROOT"
REPO_ROOT = Path(__file__).resolve().parents[4]


class WorkspaceArtifactMetric:
    """Score the final response and a file read through workspace evidence."""

    @property
    def type(self) -> str:
        return "workspace_artifact"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [
            MetricOutputSpec.boolean("output_matches"),
            MetricOutputSpec.boolean("artifact_matches"),
        ]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        reference = input.row.data.get("reference", {})
        expected = reference.get("expected") if isinstance(reference, dict) else None
        artifact_path = reference.get("artifact_path") if isinstance(reference, dict) else None

        output_matches = (
            isinstance(expected, str)
            and input.candidate.output_text is not None
            and input.candidate.output_text.strip() == expected
        )

        artifact_matches = False
        evidence = input.candidate.evidence
        if evidence is not None and isinstance(expected, str) and isinstance(artifact_path, str):
            try:
                workspace = await evidence.filesystem("workspace")
                artifact_matches = (await workspace.read_text(artifact_path)).strip() == expected
            except (KeyError, OSError, ValueError):
                artifact_matches = False

        return MetricResult(
            outputs=[
                MetricOutput(name="output_matches", value=output_matches),
                MetricOutput(name="artifact_matches", value=artifact_matches),
            ]
        )


def _new_output_dir() -> Path:
    default_root = REPO_ROOT / "temp" / "codex-docker-eval-output"
    output_root = Path(os.getenv(OUTPUT_ROOT_ENV_NAME, str(default_root))).expanduser()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return output_root / timestamp


def _docker_runtime(output_dir: Path) -> CodexDockerCliAgentRuntime:
    auth_path = os.getenv(CODEX_AUTH_PATH_ENV_NAME)
    model = os.getenv(CODEX_MODEL_ENV_NAME)
    return CodexDockerCliAgentRuntime(
        model=model or None,
        work_root=output_dir / "evidence" / "codex-docker",
        auth_path=auth_path or None,
    )


async def evaluate(
    *,
    output_dir: str | Path | None = None,
    runtime: AgentTaskRunner | None = None,
    write_dashboard: bool = True,
) -> AgentEvalResult:
    """Run one Docker Codex task and score its host-readable workspace evidence."""
    resolved_output_dir = Path(output_dir).expanduser() if output_dir is not None else _new_output_dir()
    target = runtime or _docker_runtime(resolved_output_dir)

    task = AgentEvalTask(
        id="codex-docker-evidence",
        intent="Create a nested artifact that remains private and host-readable after Docker exits.",
        inputs={
            "instruction": (
                f"Create the directory {Path(ARTIFACT_PATH).parent.as_posix()} in the workspace. "
                f"Write exactly '{EXPECTED_TEXT}' followed by a newline to {ARTIFACT_PATH}. "
                f"Then reply with exactly: {EXPECTED_TEXT}"
            )
        },
        reference={"artifact_path": ARTIFACT_PATH, "expected": EXPECTED_TEXT},
        metrics=[WorkspaceArtifactMetric()],
    )

    return await AgentEvaluator().run(
        tasks=[task],
        target=target,
        config=AgentEvalRunConfig(
            output_dir=resolved_output_dir,
            parallelism=1,
            write_dashboard=write_dashboard,
            benchmark={"name": "codex-docker-evidence-sanity"},
        ),
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    result = await evaluate()

    trial = result.trials[0]
    if trial.output is None or trial.evidence is None:
        raise RuntimeError(f"Docker Codex trial failed: {trial.metadata}")

    workspace = await trial.evidence.filesystem("workspace")
    artifact = workspace.path(ARTIFACT_PATH)
    scores = {f"{score.metric_type}.{output.name}": output.value for score in result.scores for output in score.outputs}

    print(f"response: {trial.output.output_text}")
    print(f"artifact: {artifact}")
    print(f"artifact contents: {artifact.read_text(encoding='utf-8').strip()}")
    print(f"workspace_artifact.output_matches: {scores['workspace_artifact.output_matches']}")
    print(f"workspace_artifact.artifact_matches: {scores['workspace_artifact.artifact_matches']}")
    print(f"run bundle: {result.output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
