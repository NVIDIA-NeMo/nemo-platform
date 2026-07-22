# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run the bounded mixed Intake ingest/read workload in ``load-testing``."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from nmp.intake.benchmarks.loadgen import IngestConfig
from nmp.intake.benchmarks.loadgen import run as run_ingest
from nmp.intake.benchmarks.readgen import ReadConfig
from nmp.intake.benchmarks.readgen import run as run_read

_INTAKE_SERVICE_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_ARTIFACTS_ROOT = _INTAKE_SERVICE_ROOT / "benchmarks" / "artifacts" / "runs"


async def run(
    *,
    base_url: str,
    run_id: str,
    experiment_group_id: str,
    evaluation_name: str,
    trace_id: str,
    session_id: str,
    warmup_seconds: float,
    duration_seconds: float,
    timeout_seconds: float,
    platform_pid: int | None,
    clickhouse_container: str | None,
    resource_interval_seconds: float,
    output_dir: Path,
) -> dict[str, Any]:
    """Start five independent clients concurrently and preserve per-path results."""

    output_dir.mkdir(parents=True, exist_ok=False)
    ingest_config = IngestConfig(
        base_url=base_url,
        run_id=f"{run_id}-ingest",
        warmup_seconds=warmup_seconds,
        duration_seconds=duration_seconds,
        concurrency=10,
        spans_per_request=10,
        timeout_seconds=timeout_seconds,
        platform_pid=platform_pid,
        clickhouse_container=clickhouse_container,
        resource_interval_seconds=resource_interval_seconds,
    )
    read_configs = (
        ReadConfig(
            base_url=base_url,
            run_id=f"{run_id}-evaluation-overview",
            scenario="evaluation-overview",
            experiment_group_id=experiment_group_id,
            evaluation_name=None,
            trace_id=None,
            session_id=None,
            warmup_seconds=warmup_seconds,
            duration_seconds=duration_seconds,
            operation_limit=None,
            concurrency=2,
            timeout_seconds=timeout_seconds,
            platform_pid=None,
            clickhouse_container=None,
            resource_interval_seconds=resource_interval_seconds,
        ),
        ReadConfig(
            base_url=base_url,
            run_id=f"{run_id}-evaluation-sessions",
            scenario="evaluation-sessions",
            experiment_group_id=None,
            evaluation_name=evaluation_name,
            trace_id=None,
            session_id=None,
            warmup_seconds=warmup_seconds,
            duration_seconds=duration_seconds,
            operation_limit=None,
            concurrency=2,
            timeout_seconds=timeout_seconds,
            platform_pid=None,
            clickhouse_container=None,
            resource_interval_seconds=resource_interval_seconds,
        ),
        ReadConfig(
            base_url=base_url,
            run_id=f"{run_id}-trace-browse",
            scenario="traces-preview",
            experiment_group_id=None,
            evaluation_name=None,
            trace_id=None,
            session_id=None,
            warmup_seconds=warmup_seconds,
            duration_seconds=duration_seconds,
            operation_limit=None,
            concurrency=2,
            timeout_seconds=timeout_seconds,
            platform_pid=None,
            clickhouse_container=None,
            resource_interval_seconds=resource_interval_seconds,
        ),
        ReadConfig(
            base_url=base_url,
            run_id=f"{run_id}-trace-detail",
            scenario="trace-detail-transaction",
            experiment_group_id=None,
            evaluation_name=None,
            trace_id=trace_id,
            session_id=session_id,
            warmup_seconds=warmup_seconds,
            duration_seconds=duration_seconds,
            operation_limit=None,
            concurrency=1,
            timeout_seconds=timeout_seconds,
            platform_pid=None,
            clickhouse_container=None,
            resource_interval_seconds=resource_interval_seconds,
        ),
    )

    started_at = datetime.now(timezone.utc)
    ingest_task = asyncio.create_task(run_ingest(ingest_config, output_dir=output_dir / "ingest"))
    read_tasks = [
        asyncio.create_task(run_read(config, output_dir=output_dir / config.scenario)) for config in read_configs
    ]
    ingest_result, *read_results = await asyncio.gather(ingest_task, *read_tasks)
    ingest_summary, _ingest_path = ingest_result
    read_summaries = [summary for summary, _path in read_results]
    summary = {
        "scenario": "mixed",
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "configured_warmup_seconds": warmup_seconds,
        "configured_duration_seconds": duration_seconds,
        "ingest": ingest_summary,
        "reads": {item["scenario"]: item for item in read_summaries},
        "resources": ingest_summary["resources"],
    }
    (output_dir / "mixed-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NMP_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--experiment-group-id", required=True)
    parser.add_argument("--evaluation-name", default="load-test-deep-evaluation")
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--warmup-seconds", type=_non_negative_float, default=10.0)
    parser.add_argument("--duration-seconds", type=_positive_float, default=300.0)
    parser.add_argument("--timeout-seconds", type=_positive_float, default=60.0)
    parser.add_argument("--platform-pid", type=_positive_int, default=None)
    parser.add_argument("--clickhouse-container", default=None)
    parser.add_argument("--resource-interval-seconds", type=_positive_float, default=1.0)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-mixed-{secrets.token_hex(2)}"


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
    try:
        summary = asyncio.run(
            run(
                base_url=args.base_url,
                run_id=run_id,
                experiment_group_id=args.experiment_group_id,
                evaluation_name=args.evaluation_name,
                trace_id=args.trace_id,
                session_id=args.session_id,
                warmup_seconds=args.warmup_seconds,
                duration_seconds=args.duration_seconds,
                timeout_seconds=args.timeout_seconds,
                platform_pid=args.platform_pid,
                clickhouse_container=args.clickhouse_container,
                resource_interval_seconds=args.resource_interval_seconds,
                output_dir=output_dir,
            )
        )
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        raise SystemExit(f"Intake mixed load test failed: {exc}") from exc

    ingest = summary["ingest"]
    print(
        f"mixed ingest: {ingest['successes']}/{ingest['operations']} successful, "
        f"{ingest['successful_spans_per_second']:.2f} spans/s, p95={ingest['latency_ms']['p95']:.2f}ms"
    )
    for scenario, read in summary["reads"].items():
        print(
            f"mixed {scenario}: {read['successes']}/{read['operations']} successful, "
            f"{read['operations_per_second']:.2f} ops/s, p95={read['latency_ms']['p95']:.2f}ms"
        )
    print(f"Artifacts: {output_dir}")
    if ingest["failures"] or any(read["failures"] for read in summary["reads"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
