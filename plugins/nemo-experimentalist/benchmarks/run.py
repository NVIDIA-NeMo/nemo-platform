# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run the canonical Terminal-Bench Experimentalist benchmark."""

import argparse
import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from harbor.registry.client.package import PackageDatasetClient
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    EvaluationResult,
    TrialResult,
    local_path_from_uri,
)
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig, resolve_dataset
from pydantic import BaseModel, Field, model_validator

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = Path(__file__).resolve().parent
DEFAULT_SUITE = BENCHMARK_ROOT / "suites" / "terminal-bench-2.1.yaml"
DEFAULT_CONFIG = BENCHMARK_ROOT / "configs" / "smoke.yaml"
DEFAULT_AGENT = PLUGIN_ROOT / "examples" / "terminal-bench-agent"
DEFAULT_DATASET_CACHE = PLUGIN_ROOT / "tmp" / "benchmark-datasets"
DEFAULT_RUNTIME_CACHE = PLUGIN_ROOT / "tmp" / "runtime-cache"


class CanonicalDatasetSpec(BaseModel):
    name: str
    ref: str
    resolved_ref: str
    registry_url: str
    source_url: str
    expected_task_count: int = Field(gt=0)

    @property
    def requested_reference(self) -> str:
        return f"{self.name}@{self.ref}"


class SplitSpec(BaseModel):
    train: list[str]
    validation: list[str]
    test: list[str]

    @model_validator(mode="after")
    def validate_ids(self) -> Self:
        groups = {"train": self.train, "validation": self.validation, "test": self.test}
        for name, task_ids in groups.items():
            if not task_ids or any(not task_id for task_id in task_ids):
                raise ValueError(f"{name} task IDs must be non-empty strings")
            if len(task_ids) != len(set(task_ids)):
                raise ValueError(f"{name} task IDs contain duplicates")
        all_ids = self.train + self.validation + self.test
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("train, validation, and test task IDs must be disjoint")
        return self

    def all_ids(self) -> list[str]:
        return self.train + self.validation + self.test


class PartitionSource(BaseModel):
    commit: str
    note: str


class PartitionsSpec(BaseModel):
    source: PartitionSource
    quality: SplitSpec
    fast: SplitSpec


class SuiteSpec(BaseModel):
    schema_version: Literal[1]
    dataset: CanonicalDatasetSpec
    partitions: PartitionsSpec


class ModelSpec(BaseModel):
    aut: str
    experimentalist_smart: str
    experimentalist_mid: str
    experimentalist_fast: str


class BenchmarkConfig(BaseModel):
    suite_partition: Literal["fast", "quality"]
    test_attempts: int = Field(gt=0)
    models: ModelSpec
    optimizer: EvolutionaryOptimizerConfig


def _load_yaml(path: Path) -> Any:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


def load_suite(path: Path) -> SuiteSpec:
    """Load and validate a suite manifest."""
    return SuiteSpec.model_validate(_load_yaml(path))


def load_benchmark_config(path: Path) -> BenchmarkConfig:
    """Load and validate a benchmark configuration."""
    return BenchmarkConfig.model_validate(_load_yaml(path))


def validate_canonical_suite(
    suite: SuiteSpec,
    *,
    canonical_task_ids: set[str],
    resolved_ref: str,
) -> None:
    """Verify immutable revision, quality coverage, and all partition IDs."""
    if resolved_ref != suite.dataset.resolved_ref:
        raise ValueError(
            f"Dataset {suite.dataset.requested_reference} resolved to {resolved_ref}, "
            f"expected {suite.dataset.resolved_ref}"
        )
    if len(canonical_task_ids) != suite.dataset.expected_task_count:
        raise ValueError(
            f"Canonical dataset has {len(canonical_task_ids)} tasks, expected {suite.dataset.expected_task_count}"
        )
    quality_ids = set(suite.partitions.quality.all_ids())
    if quality_ids != canonical_task_ids:
        missing = sorted(canonical_task_ids - quality_ids)
        unknown = sorted(quality_ids - canonical_task_ids)
        raise ValueError(
            f"Quality partition does not exactly cover the canonical dataset; missing={missing}, unknown={unknown}"
        )
    unknown_fast = sorted(set(suite.partitions.fast.all_ids()) - canonical_task_ids)
    if unknown_fast:
        raise ValueError(f"Fast partition contains unknown canonical task IDs: {unknown_fast}")


def _configure_models(models: ModelSpec) -> None:
    api_key = os.environ.get("INFERENCE_API_KEY") or os.environ.get("EXPERIMENTALIST_API_KEY")
    if not api_key:
        raise RuntimeError("INFERENCE_API_KEY or EXPERIMENTALIST_API_KEY is required")
    api_base = os.environ.get("INFERENCE_API_BASE") or os.environ.get("EXPERIMENTALIST_API_BASE")
    api_base = api_base or "https://inference-api.nvidia.com/v1"
    os.environ.setdefault("INFERENCE_API_KEY", api_key)
    os.environ.setdefault("EXPERIMENTALIST_API_KEY", api_key)
    os.environ.setdefault("INFERENCE_API_BASE", api_base)
    os.environ.setdefault("EXPERIMENTALIST_API_BASE", api_base)
    os.environ["AUT_MODEL_NAME"] = models.aut
    os.environ["EXPERIMENTALIST_SMART_MODEL_NAME"] = models.experimentalist_smart
    os.environ["EXPERIMENTALIST_MID_MODEL_NAME"] = models.experimentalist_mid
    os.environ["EXPERIMENTALIST_FAST_MODEL_NAME"] = models.experimentalist_fast
    os.environ.setdefault("NEMO_EXPERIMENTALIST_RUNTIME_CACHE", str(DEFAULT_RUNTIME_CACHE))


def _agent_digest(agent_dir: Path) -> str:
    digest = hashlib.sha256()
    excluded = {".git", ".runtime-cache", ".venv", "__pycache__"}
    files = sorted(
        path
        for path in agent_dir.rglob("*")
        if path.is_file() and not any(part in excluded for part in path.relative_to(agent_dir).parts)
    )
    for path in files:
        digest.update(path.relative_to(agent_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _result_document(trial: TrialResult) -> dict[str, Any] | None:
    result_ref = trial.resources.get("result")
    if result_ref is None:
        return None
    try:
        path = local_path_from_uri(result_ref.uri, context="Harbor result")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _agent_contexts(document: dict[str, Any]) -> list[dict[str, Any]]:
    direct = document.get("agent_result")
    if isinstance(direct, dict):
        return [direct]
    contexts: list[dict[str, Any]] = []
    step_results = document.get("step_results")
    if isinstance(step_results, list):
        for step in step_results:
            if isinstance(step, dict) and isinstance(step.get("agent_result"), dict):
                contexts.append(step["agent_result"])
    return contexts


def summarize_evaluation(
    result: EvaluationResult,
    *,
    task_count: int,
    attempts: int,
) -> dict[str, Any]:
    """Summarize all expected trials, counting missing and failed trials as zero reward."""
    expected_trials = task_count * attempts
    reward_sum = 0.0
    passes = 0
    harness_errors: list[dict[str, Any]] = []
    usage = {"input_tokens": 0, "cache_tokens": 0, "output_tokens": 0}
    costs: list[float] = []

    for trial in result.trials:
        reward = trial.metrics.get("reward")
        reward_value = float(reward.value) if reward is not None else 0.0
        reward_sum += reward_value
        passes += int(reward_value >= 1.0)
        if trial.status == "failed" or trial.error is not None:
            harness_errors.append({"trial": trial.id, "task_id": trial.task_id, "error": trial.error})
        document = _result_document(trial)
        if document is None:
            continue
        for context in _agent_contexts(document):
            usage["input_tokens"] += int(context.get("n_input_tokens") or 0)
            usage["cache_tokens"] += int(context.get("n_cache_tokens") or 0)
            usage["output_tokens"] += int(context.get("n_output_tokens") or 0)
            cost = context.get("cost_usd")
            if isinstance(cost, int | float):
                costs.append(float(cost))

    missing_trials = max(0, expected_trials - len(result.trials))
    return {
        "expected_trials": expected_trials,
        "observed_trials": len(result.trials),
        "missing_trials": missing_trials,
        "passes": passes,
        "reward_sum": reward_sum,
        "mean_reward_over_expected": reward_sum / expected_trials,
        "harness_error_count": len(harness_errors) + missing_trials,
        "harness_errors": harness_errors,
        "tokens": usage,
        "cost_usd": sum(costs) if costs else None,
    }


def summarize_experimentalist_jobs(results_dir: Path) -> dict[str, Any]:
    """Summarize Harbor job-level results produced during optimization."""
    jobs: list[dict[str, Any]] = []
    totals = {
        "jobs": 0,
        "trials": 0,
        "completed_trials": 0,
        "errored_trials": 0,
        "input_tokens": 0,
        "cache_tokens": 0,
        "output_tokens": 0,
    }
    costs: list[float] = []
    for result_path in sorted(results_dir.glob("*/result.json")):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("stats"), dict):
            continue
        stats = payload["stats"]
        job = {
            "name": result_path.parent.name,
            "trials": int(payload.get("n_total_trials") or 0),
            "completed_trials": int(stats.get("n_completed_trials") or 0),
            "errored_trials": int(stats.get("n_errored_trials") or 0),
            "input_tokens": int(stats.get("n_input_tokens") or 0),
            "cache_tokens": int(stats.get("n_cache_tokens") or 0),
            "output_tokens": int(stats.get("n_output_tokens") or 0),
            "cost_usd": stats.get("cost_usd") if isinstance(stats.get("cost_usd"), int | float) else None,
            "evals": stats.get("evals") if isinstance(stats.get("evals"), dict) else {},
        }
        jobs.append(job)
        totals["jobs"] += 1
        for key in (
            "trials",
            "completed_trials",
            "errored_trials",
            "input_tokens",
            "cache_tokens",
            "output_tokens",
        ):
            totals[key] += job[key]
        if job["cost_usd"] is not None:
            costs.append(float(job["cost_usd"]))
    return {**totals, "cost_usd": sum(costs) if costs else None, "job_results": jobs}


async def _evaluate_heldout(
    *,
    label: str,
    agent_dir: Path,
    dataset: HarborDataset,
    run_dir: Path,
    attempts: int,
    concurrency: int,
) -> dict[str, Any]:
    options = HarborEvaluatorConfig(
        job_name=f"heldout-{label}",
        jobs_dir=Path("heldout-results"),
        n_attempts=attempts,
        n_concurrent_trials=concurrency,
        quiet=True,
        force_rerun=False,
        agent_setup_timeout_multiplier=2.0,
        environment_build_timeout_multiplier=2.0,
    )
    started = time.monotonic()
    result = await HarborEvaluator(experiment_dir=run_dir).run(
        agent=agent_dir,
        dataset=dataset,
        options=options,
    )
    summary = summarize_evaluation(result, task_count=len(dataset.tasks), attempts=attempts)
    summary["elapsed_seconds"] = time.monotonic() - started
    summary["job_name"] = options.job_name
    return summary


async def run_benchmark(args: argparse.Namespace) -> Path:
    """Execute baseline, optimization, and held-out winner evaluation."""
    suite = load_suite(args.suite)
    benchmark_config = load_benchmark_config(args.config)
    split: SplitSpec = getattr(suite.partitions, benchmark_config.suite_partition)

    package_client = PackageDatasetClient()
    metadata = await package_client.get_dataset_metadata(suite.dataset.requested_reference)
    canonical_task_ids = {task.name for task in metadata.task_ids}
    validate_canonical_suite(suite, canonical_task_ids=canonical_task_ids, resolved_ref=metadata.version)

    if args.validate_only:
        print(
            f"Validated {suite.dataset.requested_reference}: {len(canonical_task_ids)} tasks; "
            f"{benchmark_config.suite_partition} split "
            f"{len(split.train)}/{len(split.validation)}/{len(split.test)}"
        )
        return args.output

    _configure_models(benchmark_config.models)
    from nemo_experimentalist_plugin.experimentalist.run import run_experimentalist  # noqa: PLC0415

    run_dir = args.output.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    benchmark_started = time.monotonic()
    dataset_path = Path(
        await resolve_dataset(
            suite.dataset.requested_reference,
            PLUGIN_ROOT,
            registry_url=suite.dataset.registry_url,
            cache_dir=args.cache_dir,
        )
    )
    test_ref = DatasetRef(
        uri=str(dataset_path),
        metadata={"id": f"{benchmark_config.suite_partition}-test", "task_ids": split.test},
    )
    test_dataset = HarborDataset.from_ref(test_ref)
    baseline_dir = args.agent.resolve()

    baseline = await _evaluate_heldout(
        label="baseline",
        agent_dir=baseline_dir,
        dataset=test_dataset,
        run_dir=run_dir,
        attempts=benchmark_config.test_attempts,
        concurrency=args.test_concurrency,
    )

    experimentalist_dir = run_dir / "optimizer"
    experimentalist_summary = await run_experimentalist(
        agent=str(baseline_dir),
        agent_spec=str(baseline_dir / "AGENT-SPEC.md"),
        insight=None,
        train_dataset=DatasetRef(
            uri=str(dataset_path),
            metadata={"id": f"{benchmark_config.suite_partition}-train", "task_ids": split.train},
        ),
        validation_dataset=DatasetRef(
            uri=str(dataset_path),
            metadata={"id": f"{benchmark_config.suite_partition}-validation", "task_ids": split.validation},
        ),
        experiment_dir=experimentalist_dir,
        workspace="canonical-terminal-bench-2-1",
        client=None,
        config=benchmark_config.optimizer,
        framework_skills_dirs=[PLUGIN_ROOT / "framework-skills" / "langchain-framework"],
    )
    run_document = json.loads((experimentalist_dir / "eval-and-optimize" / "run.json").read_text(encoding="utf-8"))
    winner_label = run_document.get("winner_agent")
    if not isinstance(winner_label, str) or not winner_label:
        raise RuntimeError("Experimentalist completed without a selected winner")
    winner_dir = experimentalist_dir / "eval-and-optimize" / "agents" / winner_label
    winner = await _evaluate_heldout(
        label="winner",
        agent_dir=winner_dir,
        dataset=test_dataset,
        run_dir=run_dir,
        attempts=benchmark_config.test_attempts,
        concurrency=args.test_concurrency,
    )

    summary = {
        "schema_version": 1,
        "started_at": started_at.isoformat(),
        "elapsed_seconds": time.monotonic() - benchmark_started,
        "dataset": {
            **suite.dataset.model_dump(),
            "requested_reference": suite.dataset.requested_reference,
            "materialized_path": str(dataset_path),
        },
        "partition": benchmark_config.suite_partition,
        "task_counts": {
            "canonical": len(canonical_task_ids),
            "train": len(split.train),
            "validation": len(split.validation),
            "test": len(split.test),
        },
        "provenance": {
            "partition_source": suite.partitions.source.model_dump(),
            "agent_path": str(baseline_dir),
            "baseline_agent_sha256": _agent_digest(baseline_dir),
            "suite_path": str(args.suite.resolve()),
            "config_path": str(args.config.resolve()),
        },
        "models": benchmark_config.models.model_dump(),
        "config": benchmark_config.model_dump(mode="json"),
        "baseline": baseline,
        "optimizer": {
            "summary": experimentalist_summary,
            "winner_label": winner_label,
            "run_path": str(experimentalist_dir / "eval-and-optimize" / "run.json"),
            "harbor": summarize_experimentalist_jobs(experimentalist_dir / "eval-and-optimize" / "results"),
        },
        "winner": winner,
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(summary_path)
    return summary_path


def _default_output() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return PLUGIN_ROOT / "artifacts" / "experimentalist-benchmarks" / stamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--agent", type=Path, default=DEFAULT_AGENT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_DATASET_CACHE)
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument("--test-concurrency", type=int, default=1)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    asyncio.run(run_benchmark(parse_args()))


if __name__ == "__main__":
    main()
