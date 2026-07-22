# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bounded asynchronous read load generator for Intake."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import secrets
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any, Literal

import httpx
from nmp.intake.benchmarks.loadgen import WORKSPACE, ensure_ready
from nmp.intake.benchmarks.resources import (
    ResourceMonitorConfig,
    ResourceSample,
    sample_resources,
    summarize_resources,
)

ReadScenario = Literal[
    "evaluation-overview",
    "evaluation-sessions",
    "evaluation-sessions-metric",
    "evaluation-metric-limit-probe",
    "traces-summary",
    "traces-preview",
    "trace-detailed",
    "trace-spans",
    "trace-annotations",
    "trace-detail-transaction",
]

SCENARIOS: tuple[ReadScenario, ...] = (
    "evaluation-overview",
    "evaluation-sessions",
    "evaluation-sessions-metric",
    "evaluation-metric-limit-probe",
    "traces-summary",
    "traces-preview",
    "trace-detailed",
    "trace-spans",
    "trace-annotations",
    "trace-detail-transaction",
)
_TRACE_SCENARIOS = frozenset({"trace-detailed", "trace-spans", "trace-detail-transaction"})
_SESSION_SCENARIOS = frozenset({"trace-annotations", "trace-detail-transaction"})
_EVALUATION_GROUP_SCENARIOS = frozenset({"evaluation-overview"})
_EVALUATION_SCENARIOS = frozenset(
    {"evaluation-sessions", "evaluation-sessions-metric", "evaluation-metric-limit-probe"}
)
_INTAKE_SERVICE_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _INTAKE_SERVICE_ROOT.parents[1]
_DEFAULT_ARTIFACTS_ROOT = _INTAKE_SERVICE_ROOT / "benchmarks" / "artifacts" / "runs"


@dataclass(frozen=True)
class ReadConfig:
    base_url: str
    run_id: str
    scenario: ReadScenario
    experiment_group_id: str | None
    evaluation_name: str | None
    trace_id: str | None
    session_id: str | None
    warmup_seconds: float
    duration_seconds: float
    operation_limit: int | None
    concurrency: int
    timeout_seconds: float
    platform_pid: int | None
    clickhouse_container: str | None
    resource_interval_seconds: float


@dataclass(frozen=True)
class ComponentSample:
    component: str
    latency_ms: float
    status_code: int | None
    ok: bool
    response_bytes: int
    returned_items: int | None = None
    total_results: int | None = None
    error_kind: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class OperationSample:
    request_index: int
    started_at_offset_seconds: float
    latency_ms: float
    ok: bool
    components: tuple[ComponentSample, ...]


@dataclass(frozen=True)
class PhaseResult:
    samples: list[OperationSample]
    elapsed_seconds: float
    peak_active_operations: int


@dataclass(frozen=True)
class ScenarioRequest:
    component: str
    url: str
    params: dict[str, str | int]
    expected_status_code: int = 200


class _ActiveOperations:
    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    def enter(self) -> None:
        self.current += 1
        self.peak = max(self.peak, self.current)

    def exit(self) -> None:
        self.current -= 1


def _scenario_requests(config: ReadConfig) -> tuple[ScenarioRequest, ...]:
    root = f"{config.base_url.rstrip('/')}/apis/intake/v2/workspaces/{WORKSPACE}"
    if config.scenario == "evaluation-overview":
        evaluations_url = f"{root}/evaluations"
        shared = {"filter[experiment_group_id]": config.experiment_group_id or "", "page": 1}
        return (
            ScenarioRequest(
                "evaluations-pinned",
                evaluations_url,
                {**shared, "filter[is_pinned]": "true", "sort": "-pinned_at", "page_size": 100},
            ),
            ScenarioRequest(
                "evaluations-unpinned",
                evaluations_url,
                {**shared, "filter[is_pinned]": "false", "page_size": 50},
            ),
        )
    if config.scenario == "evaluation-sessions":
        return (
            ScenarioRequest(
                "evaluation-sessions",
                f"{root}/evaluations/{config.evaluation_name}/sessions",
                _evaluation_session_params(metric_sort=False),
            ),
        )
    if config.scenario == "evaluation-sessions-metric":
        return (
            ScenarioRequest(
                "evaluation-sessions-metric",
                f"{root}/evaluations/{config.evaluation_name}/sessions",
                _evaluation_session_params(metric_sort=True),
            ),
        )
    if config.scenario == "evaluation-metric-limit-probe":
        return (
            ScenarioRequest(
                "evaluation-metric-limit-probe",
                f"{root}/evaluations/{config.evaluation_name}/sessions",
                _evaluation_session_params(metric_sort=True),
                expected_status_code=413,
            ),
        )
    if config.scenario == "traces-summary":
        return (ScenarioRequest("traces-summary", f"{root}/traces", _trace_list_params("summary")),)
    if config.scenario == "traces-preview":
        return (ScenarioRequest("traces-preview", f"{root}/traces", _trace_list_params("preview")),)
    if config.scenario == "trace-detailed":
        return (ScenarioRequest("trace-detailed", f"{root}/traces/{config.trace_id}", {"mode": "detailed"}),)
    if config.scenario == "trace-spans":
        return (ScenarioRequest("trace-spans", f"{root}/spans", _trace_spans_params(config)),)
    if config.scenario == "trace-annotations":
        return (ScenarioRequest("trace-annotations", f"{root}/annotations", _trace_annotations_params(config)),)
    if config.scenario == "trace-detail-transaction":
        return (
            ScenarioRequest("trace-detailed", f"{root}/traces/{config.trace_id}", {"mode": "detailed"}),
            ScenarioRequest("trace-spans", f"{root}/spans", _trace_spans_params(config)),
            ScenarioRequest("trace-annotations", f"{root}/annotations", _trace_annotations_params(config)),
        )
    raise ValueError(f"Unsupported read scenario: {config.scenario}")


def _trace_list_params(mode: str) -> dict[str, str | int]:
    return {"mode": mode, "sort": "-started_at", "page": 1, "page_size": 50}


def _evaluation_session_params(*, metric_sort: bool) -> dict[str, str | int]:
    params: dict[str, str | int] = {"mode": "preview", "page": 1, "page_size": 50}
    if metric_sort:
        params["sort"] = "-cost_total_usd"
    return params


def _trace_spans_params(config: ReadConfig) -> dict[str, str | int]:
    return {
        "filter[trace_id]": config.trace_id or "",
        "mode": "summary",
        "sort": "started_at",
        "page": 1,
        "page_size": 1000,
    }


def _trace_annotations_params(config: ReadConfig) -> dict[str, str | int]:
    return {
        "filter[session_id]": config.session_id or "",
        "sort": "-created_at",
        "page": 1,
        "page_size": 1000,
    }


async def _send_request(
    client: httpx.AsyncClient,
    *,
    component: str,
    url: str,
    params: dict[str, str | int],
    expected_status_code: int,
) -> ComponentSample:
    started_at = time.perf_counter()
    try:
        response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        return _failed_component(component, started_at, "timeout", type(exc).__name__)
    except httpx.HTTPError as exc:
        return _failed_component(component, started_at, "transport", type(exc).__name__)

    latency_ms = (time.perf_counter() - started_at) * 1000
    response_bytes = len(response.content)
    if response.status_code != expected_status_code:
        return ComponentSample(
            component=component,
            latency_ms=latency_ms,
            status_code=response.status_code,
            ok=False,
            response_bytes=response_bytes,
            error_kind="http_status",
            detail=_response_detail(response),
        )
    try:
        body = response.json()
    except ValueError:
        return ComponentSample(
            component=component,
            latency_ms=latency_ms,
            status_code=response.status_code,
            ok=False,
            response_bytes=response_bytes,
            error_kind="invalid_response",
            detail=_response_detail(response),
        )
    if not isinstance(body, dict):
        return ComponentSample(
            component=component,
            latency_ms=latency_ms,
            status_code=response.status_code,
            ok=False,
            response_bytes=response_bytes,
            error_kind="invalid_response",
            detail=_truncate(json.dumps(body, sort_keys=True)),
        )

    returned_items: int | None = None
    total_results: int | None = None
    if "data" in body:
        data = body.get("data")
        pagination = body.get("pagination")
        if not isinstance(data, list) or not isinstance(pagination, dict):
            return ComponentSample(
                component=component,
                latency_ms=latency_ms,
                status_code=response.status_code,
                ok=False,
                response_bytes=response_bytes,
                error_kind="invalid_response",
                detail=_truncate(json.dumps(body, sort_keys=True)),
            )
        returned_items = len(data)
        raw_total_results = pagination.get("total_results")
        if isinstance(raw_total_results, int):
            total_results = raw_total_results
    return ComponentSample(
        component=component,
        latency_ms=latency_ms,
        status_code=response.status_code,
        ok=True,
        response_bytes=response_bytes,
        returned_items=returned_items,
        total_results=total_results,
    )


async def _run_operation(
    client: httpx.AsyncClient,
    *,
    config: ReadConfig,
    request_index: int,
    phase_started_at: float,
) -> OperationSample:
    started_at_offset = time.perf_counter() - phase_started_at
    started_at = time.perf_counter()
    components = await asyncio.gather(
        *(
            _send_request(
                client,
                component=request.component,
                url=request.url,
                params=request.params,
                expected_status_code=request.expected_status_code,
            )
            for request in _scenario_requests(config)
        )
    )
    return OperationSample(
        request_index=request_index,
        started_at_offset_seconds=started_at_offset,
        latency_ms=(time.perf_counter() - started_at) * 1000,
        ok=all(component.ok for component in components),
        components=tuple(components),
    )


async def run_phase(
    client: httpx.AsyncClient,
    *,
    config: ReadConfig,
    duration_seconds: float,
    request_indexes: Iterator[int],
    operation_limit: int | None = None,
) -> PhaseResult:
    """Run a fixed logical-concurrency phase until its request-start deadline."""

    if duration_seconds <= 0:
        return PhaseResult(samples=[], elapsed_seconds=0.0, peak_active_operations=0)

    samples: list[OperationSample] = []
    active = _ActiveOperations()
    phase_started_at = time.perf_counter()
    request_deadline = phase_started_at + duration_seconds
    start_barrier = asyncio.Event()
    started_operations = 0

    async def worker() -> None:
        nonlocal started_operations
        await start_barrier.wait()
        while time.perf_counter() < request_deadline:
            if operation_limit is not None:
                if started_operations >= operation_limit:
                    return
                started_operations += 1
            active.enter()
            try:
                sample = await _run_operation(
                    client,
                    config=config,
                    request_index=next(request_indexes),
                    phase_started_at=phase_started_at,
                )
            finally:
                active.exit()
            samples.append(sample)

    tasks = [asyncio.create_task(worker()) for _ in range(config.concurrency)]
    start_barrier.set()
    await asyncio.gather(*tasks)
    return PhaseResult(
        samples=samples,
        elapsed_seconds=time.perf_counter() - phase_started_at,
        peak_active_operations=active.peak,
    )


def summarize(
    config: ReadConfig,
    result: PhaseResult,
    resource_samples: Sequence[ResourceSample] = (),
) -> dict[str, Any]:
    """Build a JSON summary for a measured read phase."""

    successes = [sample for sample in result.samples if sample.ok]
    component_samples: defaultdict[str, list[ComponentSample]] = defaultdict(list)
    for sample in result.samples:
        for component in sample.components:
            component_samples[component.component].append(component)

    elapsed = result.elapsed_seconds
    return {
        "scenario": config.scenario,
        "workspace": WORKSPACE,
        "run_id": config.run_id,
        "experiment_group_id": config.experiment_group_id,
        "evaluation_name": config.evaluation_name,
        "trace_id": config.trace_id,
        "session_id": config.session_id,
        "configured_duration_seconds": config.duration_seconds,
        "configured_operation_limit": config.operation_limit,
        "elapsed_seconds": elapsed,
        "concurrency": config.concurrency,
        "peak_active_operations": result.peak_active_operations,
        "operations": len(result.samples),
        "successes": len(successes),
        "failures": len(result.samples) - len(successes),
        "operations_per_second": len(result.samples) / elapsed if elapsed else 0.0,
        "latency_ms": _latency_summary([sample.latency_ms for sample in result.samples]),
        "components": {name: _summarize_component(samples) for name, samples in sorted(component_samples.items())},
        "resources": summarize_resources(resource_samples),
    }


def _summarize_component(samples: Sequence[ComponentSample]) -> dict[str, Any]:
    successes = [sample for sample in samples if sample.ok]
    return {
        "requests": len(samples),
        "successes": len(successes),
        "failures": len(samples) - len(successes),
        "http_status_counts": dict(
            sorted(
                Counter(
                    str(sample.status_code) if sample.status_code is not None else "none" for sample in samples
                ).items()
            )
        ),
        "failure_counts": dict(
            sorted(Counter(sample.error_kind or "unknown" for sample in samples if not sample.ok).items())
        ),
        "response_bytes_mean": statistics.fmean(sample.response_bytes for sample in successes) if successes else 0.0,
        "returned_items": sorted({sample.returned_items for sample in successes if sample.returned_items is not None}),
        "total_results": sorted({sample.total_results for sample in successes if sample.total_results is not None}),
        "latency_ms": _latency_summary([sample.latency_ms for sample in samples]),
    }


def _latency_summary(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {key: 0.0 for key in ("min", "mean", "p50", "p90", "p95", "p99", "max")}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "mean": statistics.fmean(ordered),
        "p50": _percentile(ordered, 0.50),
        "p90": _percentile(ordered, 0.90),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "max": ordered[-1],
    }


def _percentile(ordered: Sequence[float], percentile: float) -> float:
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _failed_component(component: str, started_at: float, error_kind: str, detail: str) -> ComponentSample:
    return ComponentSample(
        component=component,
        latency_ms=(time.perf_counter() - started_at) * 1000,
        status_code=None,
        ok=False,
        response_bytes=0,
        error_kind=error_kind,
        detail=_truncate(detail),
    )


def _response_detail(response: httpx.Response) -> str:
    return _truncate(response.text.replace("\n", " "))


def _truncate(value: str, length: int = 500) -> str:
    return value if len(value) <= length else f"{value[: length - 1]}…"


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{secrets.token_hex(2)}"


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def write_artifacts(
    *,
    output_dir: Path,
    config: ReadConfig,
    result: PhaseResult,
    summary: dict[str, Any],
    resource_samples: Sequence[ResourceSample],
    started_at: datetime,
) -> None:
    """Write read samples and aligned resource samples."""

    output_dir.mkdir(parents=True, exist_ok=False)
    samples_dir = output_dir / "samples"
    samples_dir.mkdir()
    resources_dir = output_dir / "resources"
    resources_dir.mkdir()
    config_payload = {**asdict(config), "workspace": WORKSPACE}
    metadata = {
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
    (output_dir / "config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (samples_dir / "read.jsonl").open("w", encoding="utf-8") as sample_file:
        for sample in result.samples:
            sample_file.write(json.dumps(asdict(sample), sort_keys=True) + "\n")
    with (resources_dir / "usage.jsonl").open("w", encoding="utf-8") as resource_file:
        for sample in resource_samples:
            resource_file.write(json.dumps(asdict(sample), sort_keys=True) + "\n")


async def run(config: ReadConfig, *, output_dir: Path) -> tuple[dict[str, Any], Path]:
    """Run warmup and measurement, then persist samples and summaries."""

    _validate_config(config)
    started_at = datetime.now(timezone.utc)
    request_count = len(_scenario_requests(config))
    connection_count = config.concurrency * request_count
    limits = httpx.Limits(max_connections=connection_count, max_keepalive_connections=connection_count)
    request_indexes = count()
    async with httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(config.timeout_seconds)) as client:
        await ensure_ready(client, config.base_url)
        warmup = await run_phase(
            client,
            config=config,
            duration_seconds=config.warmup_seconds,
            request_indexes=request_indexes,
        )
        warmup_failures = [sample for sample in warmup.samples if not sample.ok]
        if warmup_failures:
            raise RuntimeError(f"warmup had {len(warmup_failures)} failed operation(s)")

        monitor_stop = asyncio.Event()
        monitor_task = asyncio.create_task(
            sample_resources(
                config=ResourceMonitorConfig(
                    platform_pid=config.platform_pid,
                    clickhouse_container=config.clickhouse_container,
                    interval_seconds=config.resource_interval_seconds,
                ),
                stop=monitor_stop,
            )
        )
        try:
            measured = await run_phase(
                client,
                config=config,
                duration_seconds=config.duration_seconds,
                request_indexes=request_indexes,
                operation_limit=config.operation_limit,
            )
        finally:
            monitor_stop.set()
            resource_samples = await monitor_task

    summary = summarize(config, measured, resource_samples)
    write_artifacts(
        output_dir=output_dir,
        config=config,
        result=measured,
        summary=summary,
        resource_samples=resource_samples,
        started_at=started_at,
    )
    return summary, output_dir


def _validate_config(config: ReadConfig) -> None:
    if config.scenario in _EVALUATION_GROUP_SCENARIOS and not config.experiment_group_id:
        raise RuntimeError(f"--experiment-group-id is required for {config.scenario}")
    if config.scenario in _EVALUATION_SCENARIOS and not config.evaluation_name:
        raise RuntimeError(f"--evaluation-name is required for {config.scenario}")
    if config.scenario == "evaluation-metric-limit-probe" and config.operation_limit != 1:
        raise RuntimeError("evaluation-metric-limit-probe requires --operations 1")
    if config.scenario == "evaluation-metric-limit-probe" and config.warmup_seconds != 0:
        raise RuntimeError("evaluation-metric-limit-probe requires --warmup-seconds 0")
    if config.scenario in _TRACE_SCENARIOS and not config.trace_id:
        raise RuntimeError(f"--trace-id is required for {config.scenario}")
    if config.scenario in _SESSION_SCENARIOS and not config.session_id:
        raise RuntimeError(f"--session-id is required for {config.scenario}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load-test Intake reads in the load-testing workspace.")
    parser.add_argument("--base-url", default=os.environ.get("NMP_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--experiment-group-id", default=None)
    parser.add_argument("--evaluation-name", default=None)
    parser.add_argument("--trace-id", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--warmup-seconds", type=_non_negative_float, default=1.0)
    parser.add_argument("--duration-seconds", type=_positive_float, default=10.0)
    parser.add_argument(
        "--operations", type=_positive_int, default=None, help="Stop after exactly this many operations."
    )
    parser.add_argument("--concurrency", type=_positive_int, default=1)
    parser.add_argument("--timeout-seconds", type=_positive_float, default=30.0)
    parser.add_argument("--platform-pid", type=_positive_int, default=None)
    parser.add_argument("--clickhouse-container", default=None)
    parser.add_argument("--resource-interval-seconds", type=_positive_float, default=1.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to services/intake/benchmarks/artifacts/runs/<run-id>.",
    )
    return parser


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


def main() -> None:
    args = build_parser().parse_args()
    run_id = args.run_id or _new_run_id()
    output_dir = args.output_dir or _DEFAULT_ARTIFACTS_ROOT / run_id
    config = ReadConfig(
        base_url=args.base_url,
        run_id=run_id,
        scenario=args.scenario,
        experiment_group_id=args.experiment_group_id,
        evaluation_name=args.evaluation_name,
        trace_id=args.trace_id,
        session_id=args.session_id,
        warmup_seconds=args.warmup_seconds,
        duration_seconds=args.duration_seconds,
        operation_limit=args.operations,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout_seconds,
        platform_pid=args.platform_pid,
        clickhouse_container=args.clickhouse_container,
        resource_interval_seconds=args.resource_interval_seconds,
    )
    try:
        summary, artifact_path = asyncio.run(run(config, output_dir=output_dir))
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        raise SystemExit(f"Intake read load test failed: {exc}") from exc

    latency = summary["latency_ms"]
    print(
        f"{summary['scenario']}-c{summary['concurrency']}: "
        f"{summary['successes']}/{summary['operations']} successful, "
        f"{summary['operations_per_second']:.2f} ops/s, "
        f"p50={latency['p50']:.2f}ms, p95={latency['p95']:.2f}ms, p99={latency['p99']:.2f}ms"
    )
    for component, component_summary in summary["components"].items():
        component_latency = component_summary["latency_ms"]
        print(
            f"  {component}: p50={component_latency['p50']:.2f}ms, "
            f"p95={component_latency['p95']:.2f}ms, p99={component_latency['p99']:.2f}ms, "
            f"mean response={component_summary['response_bytes_mean'] / 1024:.1f} KiB"
        )
    print(f"Artifacts: {artifact_path}")
    resources = summary["resources"]
    if resources:
        peak_cpu = [f"loadgen={resources['loadgen']['cpu_percent_max']:.1f}%"]
        if resources["platform"] is not None:
            peak_cpu.append(f"platform={resources['platform']['cpu_percent_max']:.1f}%")
        if resources["clickhouse"] is not None:
            peak_cpu.append(f"clickhouse={resources['clickhouse']['cpu_percent_max']:.1f}%")
        print(f"Peak CPU: {', '.join(peak_cpu)}")
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
