# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bounded asynchronous OTLP ingest load generator for Intake."""

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
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any

import httpx
from nmp.intake.benchmarks.payloads import GeneratedPayload, build_otlp_payload
from nmp.intake.benchmarks.resources import (
    ResourceMonitorConfig,
    ResourceSample,
    sample_resources,
    summarize_resources,
)

WORKSPACE = "load-testing"
_INTAKE_SERVICE_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _INTAKE_SERVICE_ROOT.parents[1]
_DEFAULT_ARTIFACTS_ROOT = _INTAKE_SERVICE_ROOT / "benchmarks" / "artifacts" / "runs"


@dataclass(frozen=True)
class IngestConfig:
    base_url: str
    run_id: str
    warmup_seconds: float
    duration_seconds: float
    concurrency: int
    spans_per_request: int
    timeout_seconds: float
    platform_pid: int | None
    clickhouse_container: str | None
    resource_interval_seconds: float

    @property
    def ingest_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/apis/intake/v2/workspaces/{WORKSPACE}/ingest/otlp/v1/traces"


@dataclass(frozen=True)
class RequestSample:
    request_index: int
    session_id: str
    started_at_offset_seconds: float
    latency_ms: float
    status_code: int | None
    ok: bool
    error_kind: str | None = None
    detail: str | None = None
    ingest_errors: int = 0


@dataclass(frozen=True)
class PhaseResult:
    samples: list[RequestSample]
    elapsed_seconds: float
    peak_active_requests: int


class _ActiveRequests:
    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    def enter(self) -> None:
        self.current += 1
        self.peak = max(self.peak, self.current)

    def exit(self) -> None:
        self.current -= 1


async def ensure_ready(client: httpx.AsyncClient, base_url: str) -> None:
    """Fail loudly unless the platform readiness endpoint returns HTTP 200."""

    url = f"{base_url.rstrip('/')}/health/ready"
    response = await client.get(url)
    if response.status_code != 200:
        raise RuntimeError(f"platform readiness failed ({response.status_code}): {_response_detail(response)}")


async def ensure_workspace(client: httpx.AsyncClient, base_url: str) -> None:
    """Create the fixed load-test workspace, accepting an existing workspace."""

    url = f"{base_url.rstrip('/')}/apis/entities/v2/workspaces"
    response = await client.post(url, json={"name": WORKSPACE})
    if response.status_code == 409 or 200 <= response.status_code < 300:
        return
    raise RuntimeError(f"workspace create failed ({response.status_code}): {_response_detail(response)}")


async def send_payload(
    client: httpx.AsyncClient,
    *,
    url: str,
    request_index: int,
    payload: GeneratedPayload,
    phase_started_at: float,
) -> RequestSample:
    """Send one OTLP payload and classify HTTP, transport, and Intake errors."""

    started_at_offset = time.perf_counter() - phase_started_at
    started_at = time.perf_counter()
    try:
        response = await client.post(
            url,
            content=payload.content,
            headers={"Content-Type": "application/x-protobuf"},
        )
    except httpx.TimeoutException as exc:
        return _failed_sample(
            request_index=request_index,
            session_id=payload.session_id,
            started_at_offset=started_at_offset,
            started_at=started_at,
            error_kind="timeout",
            detail=type(exc).__name__,
        )
    except httpx.HTTPError as exc:
        return _failed_sample(
            request_index=request_index,
            session_id=payload.session_id,
            started_at_offset=started_at_offset,
            started_at=started_at,
            error_kind="transport",
            detail=type(exc).__name__,
        )

    latency_ms = (time.perf_counter() - started_at) * 1000
    if not 200 <= response.status_code < 300:
        return RequestSample(
            request_index=request_index,
            session_id=payload.session_id,
            started_at_offset_seconds=started_at_offset,
            latency_ms=latency_ms,
            status_code=response.status_code,
            ok=False,
            error_kind="http_status",
            detail=_response_detail(response),
        )

    try:
        response_body = response.json()
    except ValueError:
        return RequestSample(
            request_index=request_index,
            session_id=payload.session_id,
            started_at_offset_seconds=started_at_offset,
            latency_ms=latency_ms,
            status_code=response.status_code,
            ok=False,
            error_kind="invalid_response",
            detail=_response_detail(response),
        )
    if not isinstance(response_body, dict) or not isinstance(response_body.get("errors"), list):
        return RequestSample(
            request_index=request_index,
            session_id=payload.session_id,
            started_at_offset_seconds=started_at_offset,
            latency_ms=latency_ms,
            status_code=response.status_code,
            ok=False,
            error_kind="invalid_response",
            detail=_truncate(json.dumps(response_body, sort_keys=True)),
        )
    ingest_errors = response_body["errors"]
    if ingest_errors:
        return RequestSample(
            request_index=request_index,
            session_id=payload.session_id,
            started_at_offset_seconds=started_at_offset,
            latency_ms=latency_ms,
            status_code=response.status_code,
            ok=False,
            error_kind="ingest_errors",
            detail=_truncate(json.dumps(ingest_errors)),
            ingest_errors=len(ingest_errors),
        )
    return RequestSample(
        request_index=request_index,
        session_id=payload.session_id,
        started_at_offset_seconds=started_at_offset,
        latency_ms=latency_ms,
        status_code=response.status_code,
        ok=True,
    )


async def run_phase(
    client: httpx.AsyncClient,
    *,
    config: IngestConfig,
    duration_seconds: float,
    request_indexes: Iterator[int],
) -> PhaseResult:
    """Run a fixed-concurrency phase until its request-start deadline."""

    if duration_seconds <= 0:
        return PhaseResult(samples=[], elapsed_seconds=0.0, peak_active_requests=0)

    samples: list[RequestSample] = []
    active = _ActiveRequests()
    phase_started_at = time.perf_counter()
    request_deadline = phase_started_at + duration_seconds
    start_barrier = asyncio.Event()

    async def worker() -> None:
        await start_barrier.wait()
        while time.perf_counter() < request_deadline:
            request_index = next(request_indexes)
            payload = build_otlp_payload(
                run_id=config.run_id,
                request_index=request_index,
                spans_per_request=config.spans_per_request,
            )
            active.enter()
            try:
                sample = await send_payload(
                    client,
                    url=config.ingest_url,
                    request_index=request_index,
                    payload=payload,
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
        peak_active_requests=active.peak,
    )


async def verify_session(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    session_id: str,
    timeout_seconds: float = 10.0,
) -> None:
    """Verify one successfully submitted session through the public span API."""

    url = f"{base_url.rstrip('/')}/apis/intake/v2/workspaces/{WORKSPACE}/spans"
    deadline = time.monotonic() + timeout_seconds
    last_detail = "no response"
    while time.monotonic() < deadline:
        response = await client.get(
            url,
            params={
                "filter[session_id]": session_id,
                "mode": "summary",
                "page": 1,
                "page_size": 1,
            },
        )
        last_detail = f"HTTP {response.status_code}: {_response_detail(response)}"
        if response.status_code == 200:
            body = response.json()
            if any(row.get("session_id") == session_id for row in body.get("data", [])):
                return
        await asyncio.sleep(0.25)
    raise RuntimeError(f"verification failed for session {session_id}: {last_detail}")


def summarize(
    config: IngestConfig,
    result: PhaseResult,
    resource_samples: Sequence[ResourceSample] = (),
) -> dict[str, Any]:
    """Build the stable JSON summary for a measured ingest phase."""

    successes = [sample for sample in result.samples if sample.ok]
    failures = [sample for sample in result.samples if not sample.ok]
    latency_values = [sample.latency_ms for sample in result.samples]
    elapsed = result.elapsed_seconds
    status_counts = Counter(
        str(sample.status_code) if sample.status_code is not None else "none" for sample in result.samples
    )
    failure_counts = Counter(sample.error_kind or "unknown" for sample in failures)
    operations_per_second = len(result.samples) / elapsed if elapsed else 0.0
    successful_spans_per_second = len(successes) * config.spans_per_request / elapsed if elapsed else 0.0
    return {
        "scenario": f"ingest-{config.spans_per_request}-c{config.concurrency}",
        "workspace": WORKSPACE,
        "run_id": config.run_id,
        "configured_duration_seconds": config.duration_seconds,
        "elapsed_seconds": elapsed,
        "concurrency": config.concurrency,
        "peak_active_requests": result.peak_active_requests,
        "spans_per_request": config.spans_per_request,
        "operations": len(result.samples),
        "successes": len(successes),
        "failures": len(failures),
        "http_status_counts": dict(sorted(status_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
        "requests_per_second": operations_per_second,
        "successful_spans_per_second": successful_spans_per_second,
        "latency_ms": _latency_summary(latency_values),
        "resources": summarize_resources(resource_samples),
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
    if not ordered:
        return 0.0
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _failed_sample(
    *,
    request_index: int,
    session_id: str,
    started_at_offset: float,
    started_at: float,
    error_kind: str,
    detail: str,
) -> RequestSample:
    return RequestSample(
        request_index=request_index,
        session_id=session_id,
        started_at_offset_seconds=started_at_offset,
        latency_ms=(time.perf_counter() - started_at) * 1000,
        status_code=None,
        ok=False,
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
    config: IngestConfig,
    result: PhaseResult,
    summary: dict[str, Any],
    resource_samples: Sequence[ResourceSample],
    started_at: datetime,
) -> None:
    """Write reproducible configuration, metadata, samples, and summary."""

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
    with (samples_dir / "ingest.jsonl").open("w", encoding="utf-8") as sample_file:
        for sample in result.samples:
            sample_file.write(json.dumps(asdict(sample), sort_keys=True) + "\n")
    with (resources_dir / "usage.jsonl").open("w", encoding="utf-8") as resource_file:
        for sample in resource_samples:
            resource_file.write(json.dumps(asdict(sample), sort_keys=True) + "\n")


async def run(config: IngestConfig, *, output_dir: Path) -> tuple[dict[str, Any], Path]:
    """Provision the workspace, run warmup and measurement, verify, and persist."""

    started_at = datetime.now(timezone.utc)
    limits = httpx.Limits(
        max_connections=config.concurrency,
        max_keepalive_connections=config.concurrency,
    )
    timeout = httpx.Timeout(config.timeout_seconds)
    request_indexes = count()
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        await ensure_ready(client, config.base_url)
        await ensure_workspace(client, config.base_url)
        warmup = await run_phase(
            client,
            config=config,
            duration_seconds=config.warmup_seconds,
            request_indexes=request_indexes,
        )
        warmup_failures = [sample for sample in warmup.samples if not sample.ok]
        if warmup_failures:
            kinds = Counter(sample.error_kind or "unknown" for sample in warmup_failures)
            raise RuntimeError(f"warmup had {len(warmup_failures)} failed request(s): {dict(kinds)}")
        resource_samples: list[ResourceSample] = []
        monitor_config = ResourceMonitorConfig(
            platform_pid=config.platform_pid,
            clickhouse_container=config.clickhouse_container,
            interval_seconds=config.resource_interval_seconds,
        )
        monitor_stop = asyncio.Event()
        monitor_task = asyncio.create_task(sample_resources(config=monitor_config, stop=monitor_stop))
        try:
            measured = await run_phase(
                client,
                config=config,
                duration_seconds=config.duration_seconds,
                request_indexes=request_indexes,
            )
        finally:
            monitor_stop.set()
            resource_samples = await monitor_task
        successful = next((sample for sample in reversed(measured.samples) if sample.ok), None)
        if successful is not None:
            await verify_session(client, base_url=config.base_url, session_id=successful.session_id)

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load-test Intake OTLP ingest in the load-testing workspace.")
    parser.add_argument("--base-url", default=os.environ.get("NMP_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--warmup-seconds", type=_non_negative_float, default=1.0)
    parser.add_argument("--duration-seconds", type=_positive_float, default=10.0)
    parser.add_argument("--concurrency", type=_positive_int, default=1)
    parser.add_argument("--spans-per-request", type=_positive_int, default=10)
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
    config = IngestConfig(
        base_url=args.base_url,
        run_id=run_id,
        warmup_seconds=args.warmup_seconds,
        duration_seconds=args.duration_seconds,
        concurrency=args.concurrency,
        spans_per_request=args.spans_per_request,
        timeout_seconds=args.timeout_seconds,
        platform_pid=args.platform_pid,
        clickhouse_container=args.clickhouse_container,
        resource_interval_seconds=args.resource_interval_seconds,
    )
    try:
        summary, artifact_path = asyncio.run(run(config, output_dir=output_dir))
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        raise SystemExit(f"Intake load test failed: {exc}") from exc

    latency = summary["latency_ms"]
    print(
        f"{summary['scenario']}: {summary['successes']}/{summary['operations']} successful, "
        f"{summary['requests_per_second']:.2f} req/s, "
        f"{summary['successful_spans_per_second']:.2f} spans/s, "
        f"p50={latency['p50']:.2f}ms, p95={latency['p95']:.2f}ms, p99={latency['p99']:.2f}ms"
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
        clickhouse = resources["clickhouse"]
        if clickhouse is not None:
            memory_mib = clickhouse["memory_used_bytes_max"] / 1024**2
            block_read_mib = clickhouse.get("block_read_bytes_per_second", 0.0) / 1024**2
            block_write_mib = clickhouse.get("block_write_bytes_per_second", 0.0) / 1024**2
            print(
                f"ClickHouse: memory={memory_mib:.1f} MiB max, "
                f"block read={block_read_mib:.2f} MiB/s, block write={block_write_mib:.2f} MiB/s"
            )
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
