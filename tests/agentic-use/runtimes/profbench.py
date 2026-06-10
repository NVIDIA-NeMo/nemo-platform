# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ProfBench integration for the agentic-use runtime PoC."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval import (
    AgentEvalBenchmarkEvaluationKind,
    AgentEvalBenchmarkLoadConfig,
    AgentEvalBenchmarkReports,
    AgentEvalRunResult,
    AgentEvalTarget,
    benchmark_report_writer,
    run_benchmark_bundle,
)
from nemo_evaluator_sdk.agent_eval.types import AgentEvalTask
from nemo_evaluator_sdk.values import Model, RunConfigOnlineModel, SecretRef

from packages.nemo_evaluator_sdk.examples.profbench.profbench import (
    ProfBenchAgentEvalBenchmark,
    ProfBenchModelJudge,
)
from runtimes.shared.constants import AGENTIC_USE_DIR
from runtimes.shared.docker import docker_image_exists
from runtimes.shared.environment import DockerEnvironmentProvider
from runtimes.shared.environment_spec import execute_build_plan, plan_task_build
from runtimes.shared.layout import task_image_tag

PROFBENCH_TASK_NAME = "profbench"
PROFBENCH_TASK_DIR = AGENTIC_USE_DIR / PROFBENCH_TASK_NAME
PROFBENCH_IMAGE_TAG = task_image_tag(PROFBENCH_TASK_NAME)
DEFAULT_PROFBENCH_OUTPUT_ROOT = Path("env/profbench-results")
DEFAULT_JUDGE_MODEL_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_JUDGE_MODEL_NAME = "nvidia/nemotron-3-nano-30b-a3b"
DEFAULT_JUDGE_API_KEY_ENV = "NVIDIA_API_KEY"


@dataclass(frozen=True)
class ProfBenchRuntimeConfig:
    """Options for running ProfBench through an agentic-use runtime."""

    source: str | Path | None = None
    limit: int | None = 1
    judge_model_url: str = DEFAULT_JUDGE_MODEL_URL
    judge_model_name: str = DEFAULT_JUDGE_MODEL_NAME
    judge_api_key_env: str = DEFAULT_JUDGE_API_KEY_ENV
    skip_build: bool = False


async def run_profbench_agent_eval(
    *,
    target: AgentEvalTarget,
    output_dir: Path | None = None,
    run_id: str | None = None,
    config: ProfBenchRuntimeConfig | None = None,
    params: RunConfigOnlineModel | None = None,
) -> tuple[AgentEvalRunResult, AgentEvalBenchmarkReports]:
    """Evaluate a selected runtime target on ProfBench."""
    profbench_config = config or ProfBenchRuntimeConfig()
    output_dir, resolved_run_id = _resolve_profbench_run(output_dir, run_id)
    target = _prepare_target(target, skip_build=profbench_config.skip_build)

    benchmark = _live_judge_benchmark(profbench_config)
    bundle = benchmark.load(
        AgentEvalBenchmarkLoadConfig(
            evaluation_kind=AgentEvalBenchmarkEvaluationKind.LIVE_TARGET,
            source=profbench_config.source,
            limit=profbench_config.limit,
            evidence_dir=output_dir / "evidence",
        )
    )
    bundle = bundle.model_copy(update={"tasks": [_profbench_runtime_task(task) for task in bundle.tasks]})

    return await run_benchmark_bundle(
        bundle=bundle,
        output_dir=output_dir,
        run_id=resolved_run_id,
        target=target,
        params=params,
        report_writer=benchmark_report_writer(benchmark),
    )


def _prepare_target(target: AgentEvalTarget, *, skip_build: bool) -> AgentEvalTarget:
    """Attach the shared ProfBench Docker image provider when the target uses one."""
    if not hasattr(target, "environment"):
        return target

    _ensure_profbench_image(skip_build=skip_build)
    setattr(
        target,
        "environment",
        DockerEnvironmentProvider(image_tag_fn=lambda _task_id: PROFBENCH_IMAGE_TAG),
    )
    return target


def _ensure_profbench_image(*, skip_build: bool) -> None:
    if skip_build:
        if not docker_image_exists(PROFBENCH_IMAGE_TAG):
            raise RuntimeError(
                f"--skip-build requested but task image {PROFBENCH_IMAGE_TAG!r} is not available locally. "
                "Run without skip_build to build the ProfBench task image first."
            )
        return
    execute_build_plan(plan_task_build(PROFBENCH_TASK_DIR, PROFBENCH_IMAGE_TAG))


def _profbench_runtime_task(task: AgentEvalTask) -> AgentEvalTask:
    metadata: dict[str, Any] = {
        **task.metadata,
        "task_dir": str(PROFBENCH_TASK_DIR.resolve()),
        "instruction_path": str((PROFBENCH_TASK_DIR / "instruction.md").resolve()),
        "agentic_use_run_subdir": f"agent-runtime/{_safe_path_name(task.id)}",
    }
    return task.model_copy(update={"metadata": metadata})


def _live_judge_benchmark(config: ProfBenchRuntimeConfig) -> ProfBenchAgentEvalBenchmark:
    judge_model = Model(
        url=config.judge_model_url,
        name=config.judge_model_name,
        api_key_secret=SecretRef(root=config.judge_api_key_env),
    )
    return ProfBenchAgentEvalBenchmark(
        judge_factory=lambda: ProfBenchModelJudge(model=judge_model),
        score_source="agentic_use_candidate_and_live_judge",
    )


def _resolve_profbench_run(output_root: Path | None, run_id: str | None) -> tuple[Path, str]:
    run_instance_id = run_id or _new_profbench_run_instance_id()
    root = Path(output_root) if output_root is not None else DEFAULT_PROFBENCH_OUTPUT_ROOT
    return (root / run_instance_id).resolve(), run_instance_id


def _new_profbench_run_instance_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid = os.getpid() % 100000
    return f"{timestamp}_{pid:05d}_{uuid.uuid4().hex[:6]}"


def _safe_path_name(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip(".-")[:120]
    return sanitized or "task"
