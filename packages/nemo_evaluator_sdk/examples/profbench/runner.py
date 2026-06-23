# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Command-line runner for the ProfBench agent-eval example."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from pathlib import Path

if __package__ in {None, ""}:
    raise SystemExit(
        "Run ProfBench as a module from the repository root:\n"
        "  python -m packages.nemo_evaluator_sdk.examples.profbench.runner"
    )

from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import (
    EffectiveCodexRuntime,
    RuntimeChoice,
    print_codex_agent_models,
    resolve_codex_target,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_evaluator_sdk.values import InferenceParams, Model, RunConfigOnlineModel, SecretRef

from .profbench import (
    PROFBENCH_DATASET_URL,
    PROFBENCH_METRIC_ID,
    PROFBENCH_METRIC_TYPE,
    ProfBenchModelJudge,
    load_profbench,
    write_example_dashboards,
)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "profbench-agent-eval-output"
DEFAULT_MODEL_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL_NAME = "nvidia/nemotron-3-nano-30b-a3b"
DEFAULT_API_KEY_SECRET = os.getenv("NMP_EVALUATOR_DEFAULT_API_KEY_SECRET", "NVIDIA_API_KEY")


class AgentChoice(StrEnum):
    MODEL = "model"
    CODEX = "codex"


class ProfBenchMode(StrEnum):
    BASELINE = "baseline"
    LIVE_JUDGE = "live-judge"
    LIVE_CANDIDATE = "live-candidate"


def configure_example_logging() -> None:
    """Enable SDK progress logs when this example file is executed directly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("nemo_evaluator_sdk.inference").setLevel(logging.WARNING)


async def run_profbench_mode(
    mode: ProfBenchMode,
    *,
    limit: int | None,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
    agent: AgentChoice = AgentChoice.MODEL,
    agent_model: str | None = None,
    runtime: RuntimeChoice = RuntimeChoice.DOCKER,
) -> None:
    """Run one ProfBench mode.

    - ``baseline``: score the dataset's recorded responses against their cached fulfilment labels.
    - ``live-judge``: re-score those recorded responses with a live LLM judge.
    - ``live-candidate``: generate fresh candidate responses, then score them with a live judge.
    """
    _print_example_separator(mode.value)

    output_root = _resolve_profbench_output_root(output_root)
    run_instance_id = run_instance_id or _new_profbench_run_instance_id()
    output_dir = _profbench_output_dir(output_root, run_instance_id, mode.value)

    judge = None if mode is ProfBenchMode.BASELINE else ProfBenchModelJudge(model=_judge_model())
    benchmark = load_profbench(
        _profbench_source(),
        limit=limit,
        judge=judge,
        evidence_dir=output_dir / "evidence",
        include_cached_fulfilments=mode is ProfBenchMode.BASELINE,
    )

    target: AgentEvalTarget | None = None
    trials: list[AgentEvalTrial] | None = None
    params: RunConfigOnlineModel | None = None
    benchmark_meta = dict(benchmark.metadata)
    if mode is ProfBenchMode.LIVE_CANDIDATE:
        target, params, score_source, effective_codex_runtime = _live_candidate_target(
            agent=agent,
            agent_model=agent_model,
            runtime=runtime,
            output_dir=output_dir,
        )
        if effective_codex_runtime is not None:
            print(f"Codex runtime: {effective_codex_runtime}")
        benchmark_meta["score_source"] = score_source
    else:
        trials = benchmark.trials
        if mode is ProfBenchMode.LIVE_JUDGE:
            benchmark_meta["score_source"] = "live_judge"

    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        trials=trials,
        target=target,
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            run_id=f"{run_instance_id}-{mode.value}",
            params=params,
            benchmark=benchmark_meta,
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, dashboard_path = write_example_dashboards(result, output_dir)

    overall = _profbench_overall(result)
    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"ProfBench trials: {result.summary.trial_count}")
    print(f"Overall score: {overall:.3f}" if overall is not None else "Overall score: n/a")
    print(f"Aggregated scores: {result.summary.scores.model_dump(mode='json')}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"Dashboard: {dashboard_path}")


async def run_examples(
    *,
    limit: int | None,
    run_live_judge: bool,
    run_live_candidate: bool,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
    agent: AgentChoice = AgentChoice.MODEL,
    agent_model: str | None = None,
    runtime: RuntimeChoice = RuntimeChoice.DOCKER,
) -> None:
    """Execute the enabled ProfBench agent-eval modes under one shared run folder."""
    output_root = _resolve_profbench_output_root(output_root)
    run_instance_id = run_instance_id or _new_profbench_run_instance_id()
    run_output_dir = Path(output_root) / run_instance_id
    run_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"ProfBench output root: {output_root}")
    print(f"ProfBench run instance: {run_instance_id}")

    await run_profbench_mode(
        ProfBenchMode.BASELINE,
        limit=limit,
        output_root=output_root,
        run_instance_id=run_instance_id,
    )

    if run_live_judge:
        await run_profbench_mode(
            ProfBenchMode.LIVE_JUDGE,
            limit=limit,
            output_root=output_root,
            run_instance_id=run_instance_id,
        )
    else:
        print("Skipping live ProfBench judge example. Remove --no-run-live-judge to run it.")

    if run_live_candidate:
        await run_profbench_mode(
            ProfBenchMode.LIVE_CANDIDATE,
            limit=limit,
            output_root=output_root,
            run_instance_id=run_instance_id,
            agent=agent,
            agent_model=agent_model,
            runtime=runtime,
        )
    else:
        print("Skipping live ProfBench candidate example. Remove --no-run-live-candidate to run it.")


def _profbench_source() -> str:
    return os.getenv("NEMO_EVALUATOR_PROFBENCH_SOURCE", PROFBENCH_DATASET_URL)


def _profbench_limit_from_args(limit: int) -> int | None:
    return None if limit == 0 else limit


def _profbench_overall(result: AgentEvalResult) -> float | None:
    """Return the mean ProfBench rubric score from the run summary, if present."""
    score_name = f"{PROFBENCH_METRIC_TYPE}.{PROFBENCH_METRIC_ID}"
    for score in result.summary.scores.scores:
        if score.name == score_name:
            return score.mean
    return None


def _resolve_profbench_output_root(output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser()
    env_output_dir = os.getenv("NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR")
    if env_output_dir:
        return Path(env_output_dir).expanduser()
    return DEFAULT_OUTPUT_DIR


def _new_profbench_run_instance_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-1]
    return f"{timestamp}_{uuid.uuid4().hex[:6]}"


def _profbench_output_dir(output_root: str | Path, run_instance_id: str, mode: str) -> Path:
    return Path(output_root).expanduser() / run_instance_id / mode


def _evaluated_model(model_name: str | None = None) -> Model:
    return Model(
        url=DEFAULT_MODEL_URL,
        name=model_name or DEFAULT_MODEL_NAME,
        api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
    )


def _judge_model() -> Model:
    return Model(
        url=DEFAULT_MODEL_URL,
        name=DEFAULT_MODEL_NAME,
        api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
    )


def _live_candidate_target(
    *,
    agent: AgentChoice,
    agent_model: str | None,
    runtime: RuntimeChoice,
    output_dir: Path,
    env: Mapping[str, str] = os.environ,
) -> tuple[
    AgentEvalTarget,
    RunConfigOnlineModel | None,
    str,
    EffectiveCodexRuntime | None,
]:
    if agent == AgentChoice.MODEL:
        return (
            _evaluated_model(agent_model),
            RunConfigOnlineModel(
                parallelism=2,
                inference=InferenceParams(temperature=0.0, max_tokens=32768),
            ),
            "fresh_candidate_and_live_judge",
            None,
        )
    if agent == AgentChoice.CODEX:
        target, score_source, effective_runtime = resolve_codex_target(
            runtime=runtime,
            model=agent_model,
            output_dir=output_dir,
            env=env,
        )
        return target, None, score_source, effective_runtime
    raise ValueError(f"unsupported ProfBench agent {agent!r}")


def _print_example_separator(name: str) -> None:
    edge = "====="
    middle_line = f"{edge} {name} {edge}"
    rule = "=" * len(middle_line)
    print(f"\n{rule}\n{middle_line}\n{rule}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ProfBench agent-eval examples.")
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum number of ProfBench tasks to evaluate (0 = no limit). Default: 1.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Root directory for ProfBench outputs. "
            "Defaults to NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR or the example output directory."
        ),
    )
    parser.add_argument(
        "--run-live-judge",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Score the recorded ProfBench responses with a live LLM judge after the baseline example.",
    )
    parser.add_argument(
        "--run-live-candidate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate fresh candidate responses from the configured model, then score them with a live LLM judge.",
    )
    parser.add_argument(
        "--agent",
        type=AgentChoice,
        choices=list(AgentChoice),
        default=AgentChoice.MODEL,
        help="Candidate agent for live-candidate mode. Use 'codex' for Codex-backed candidate generation.",
    )
    parser.add_argument(
        "--runtime",
        type=RuntimeChoice,
        choices=list(RuntimeChoice),
        default=RuntimeChoice.DOCKER,
        help=(
            "Runtime for --agent codex. Default: docker. Docker uses SDK Docker when OPENAI_API_KEY is an "
            "OpenAI secret key and runs Codex CLI inside Docker otherwise. Use local to force the host Codex CLI."
        ),
    )
    parser.add_argument(
        "--agent-model",
        default=None,
        help=(
            "Model name for the selected candidate agent. With --agent codex --runtime local this "
            "is passed to `codex exec --model`; with --agent codex --runtime docker this is passed "
            "to the effective Codex runtime; with --agent model it overrides the evaluated model name."
        ),
    )
    parser.add_argument(
        "--list-agent-models",
        action="store_true",
        help="List locally visible Codex model slugs for --agent codex and exit.",
    )
    args = parser.parse_args()
    if args.list_agent_models:
        if args.agent != AgentChoice.CODEX:
            parser.error("--list-agent-models is only supported with --agent codex")
        print_codex_agent_models()
        raise SystemExit(0)
    configure_example_logging()

    asyncio.run(
        run_examples(
            limit=_profbench_limit_from_args(args.limit),
            run_live_judge=bool(args.run_live_judge),
            run_live_candidate=bool(args.run_live_candidate),
            output_root=args.output_dir,
            agent=args.agent,
            agent_model=args.agent_model,
            runtime=args.runtime,
        )
    )
