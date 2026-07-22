# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local process and ClickHouse resource sampling for Intake benchmarks."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceMonitorConfig:
    """Components sampled during a measured benchmark phase."""

    platform_pid: int | None
    clickhouse_container: str | None
    interval_seconds: float


@dataclass(frozen=True)
class ResourceSample:
    """One aligned snapshot of load-generator, API, and ClickHouse usage."""

    captured_at_offset_seconds: float
    loadgen_pid: int
    loadgen_cpu_percent: float
    loadgen_rss_bytes: int
    platform_pid: int | None = None
    platform_cpu_percent: float | None = None
    platform_rss_bytes: int | None = None
    clickhouse_container: str | None = None
    clickhouse_cpu_percent: float | None = None
    clickhouse_memory_percent: float | None = None
    clickhouse_memory_used_bytes: int | None = None
    clickhouse_memory_limit_bytes: int | None = None
    clickhouse_network_io: str | None = None
    clickhouse_network_receive_bytes: int | None = None
    clickhouse_network_transmit_bytes: int | None = None
    clickhouse_block_io: str | None = None
    clickhouse_block_read_bytes: int | None = None
    clickhouse_block_write_bytes: int | None = None
    clickhouse_pids: int | None = None


async def sample_resources(
    *,
    config: ResourceMonitorConfig,
    stop: asyncio.Event,
) -> list[ResourceSample]:
    """Sample configured resources until ``stop`` is set."""

    samples: list[ResourceSample] = []
    started_at = time.perf_counter()
    while True:
        sample = await asyncio.to_thread(
            _capture_sample,
            config=config,
            started_at=started_at,
        )
        samples.append(sample)
        try:
            await asyncio.wait_for(stop.wait(), timeout=config.interval_seconds)
        except TimeoutError:
            continue
        return samples


def summarize_resources(samples: Sequence[ResourceSample]) -> dict[str, Any]:
    """Summarize resource samples without hiding missing components."""

    if not samples:
        return {}
    return {
        "sample_count": len(samples),
        "loadgen": _summarize_process(
            cpu_values=[sample.loadgen_cpu_percent for sample in samples],
            rss_values=[sample.loadgen_rss_bytes for sample in samples],
        ),
        "platform": _summarize_optional_process(
            cpu_values=[sample.platform_cpu_percent for sample in samples],
            rss_values=[sample.platform_rss_bytes for sample in samples],
        ),
        "clickhouse": _summarize_clickhouse(samples),
    }


def _capture_sample(*, config: ResourceMonitorConfig, started_at: float) -> ResourceSample:
    loadgen_pid = os.getpid()
    loadgen_cpu, loadgen_rss = _process_usage(loadgen_pid)
    platform_cpu: float | None = None
    platform_rss: int | None = None
    if config.platform_pid is not None:
        platform_cpu, platform_rss = _process_usage(config.platform_pid)

    clickhouse: dict[str, Any] = {}
    if config.clickhouse_container is not None:
        clickhouse = _clickhouse_usage(config.clickhouse_container)

    return ResourceSample(
        captured_at_offset_seconds=time.perf_counter() - started_at,
        loadgen_pid=loadgen_pid,
        loadgen_cpu_percent=loadgen_cpu,
        loadgen_rss_bytes=loadgen_rss,
        platform_pid=config.platform_pid,
        platform_cpu_percent=platform_cpu,
        platform_rss_bytes=platform_rss,
        clickhouse_container=config.clickhouse_container,
        clickhouse_cpu_percent=clickhouse.get("cpu_percent"),
        clickhouse_memory_percent=clickhouse.get("memory_percent"),
        clickhouse_memory_used_bytes=clickhouse.get("memory_used_bytes"),
        clickhouse_memory_limit_bytes=clickhouse.get("memory_limit_bytes"),
        clickhouse_network_io=clickhouse.get("network_io"),
        clickhouse_network_receive_bytes=clickhouse.get("network_receive_bytes"),
        clickhouse_network_transmit_bytes=clickhouse.get("network_transmit_bytes"),
        clickhouse_block_io=clickhouse.get("block_io"),
        clickhouse_block_read_bytes=clickhouse.get("block_read_bytes"),
        clickhouse_block_write_bytes=clickhouse.get("block_write_bytes"),
        clickhouse_pids=clickhouse.get("pids"),
    )


def _process_usage(pid: int) -> tuple[float, int]:
    result = subprocess.run(
        ["ps", "-o", "pid=,%cpu=,rss=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        detail = result.stderr.strip() or "process not found"
        raise RuntimeError(f"resource sampling failed for PID {pid}: {detail}")
    fields = result.stdout.split()
    if len(fields) != 3 or int(fields[0]) != pid:
        raise RuntimeError(f"unexpected ps output for PID {pid}: {result.stdout.strip()}")
    return float(fields[1]), int(fields[2]) * 1024


def _clickhouse_usage(container: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", container],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        detail = result.stderr.strip() or "container not found"
        raise RuntimeError(f"resource sampling failed for container {container}: {detail}")
    try:
        payload = json.loads(result.stdout)
        memory_used, memory_limit = (_parse_size(value) for value in payload["MemUsage"].split(" / ", 1))
        network_receive, network_transmit = _parse_io_pair(payload["NetIO"])
        block_read, block_write = _parse_io_pair(payload["BlockIO"])
        return {
            "cpu_percent": _parse_percent(payload["CPUPerc"]),
            "memory_percent": _parse_percent(payload["MemPerc"]),
            "memory_used_bytes": memory_used,
            "memory_limit_bytes": memory_limit,
            "network_io": payload["NetIO"],
            "network_receive_bytes": network_receive,
            "network_transmit_bytes": network_transmit,
            "block_io": payload["BlockIO"],
            "block_read_bytes": block_read,
            "block_write_bytes": block_write,
            "pids": int(payload["PIDs"]),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unexpected docker stats output for {container}: {result.stdout.strip()}") from exc


def _parse_percent(value: str) -> float:
    return float(value.removesuffix("%"))


def _parse_size(value: str) -> int:
    units = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "KiB": 1024,
        "MB": 1000**2,
        "MiB": 1024**2,
        "GB": 1000**3,
        "GiB": 1024**3,
    }
    stripped = value.strip()
    for unit in sorted(units, key=len, reverse=True):
        if stripped.endswith(unit):
            return round(float(stripped[: -len(unit)]) * units[unit])
    raise ValueError(f"unknown size unit: {value}")


def _parse_io_pair(value: str) -> tuple[int, int]:
    first, second = value.split(" / ", 1)
    return _parse_size(first), _parse_size(second)


def _summarize_process(*, cpu_values: Sequence[float], rss_values: Sequence[int]) -> dict[str, float | int]:
    return {
        "cpu_percent_mean": sum(cpu_values) / len(cpu_values),
        "cpu_percent_max": max(cpu_values),
        "rss_bytes_max": max(rss_values),
    }


def _summarize_optional_process(
    *,
    cpu_values: Sequence[float | None],
    rss_values: Sequence[int | None],
) -> dict[str, float | int] | None:
    present_cpu = [value for value in cpu_values if value is not None]
    present_rss = [value for value in rss_values if value is not None]
    if not present_cpu or not present_rss:
        return None
    return _summarize_process(cpu_values=present_cpu, rss_values=present_rss)


def _summarize_clickhouse(samples: Sequence[ResourceSample]) -> dict[str, float | int] | None:
    cpu_values = [sample.clickhouse_cpu_percent for sample in samples if sample.clickhouse_cpu_percent is not None]
    memory_values = [
        sample.clickhouse_memory_used_bytes for sample in samples if sample.clickhouse_memory_used_bytes is not None
    ]
    pid_values = [sample.clickhouse_pids for sample in samples if sample.clickhouse_pids is not None]
    if not cpu_values or not memory_values or not pid_values:
        return None
    summary: dict[str, float | int] = {
        "cpu_percent_mean": sum(cpu_values) / len(cpu_values),
        "cpu_percent_max": max(cpu_values),
        "memory_used_bytes_max": max(memory_values),
        "pids_max": max(pid_values),
    }
    elapsed = samples[-1].captured_at_offset_seconds - samples[0].captured_at_offset_seconds
    if elapsed > 0:
        summary.update(
            _io_rates(
                samples,
                elapsed=elapsed,
                fields=(
                    "clickhouse_network_receive_bytes",
                    "clickhouse_network_transmit_bytes",
                    "clickhouse_block_read_bytes",
                    "clickhouse_block_write_bytes",
                ),
            )
        )
    return summary


def _io_rates(
    samples: Sequence[ResourceSample],
    *,
    elapsed: float,
    fields: Sequence[str],
) -> dict[str, float]:
    rates: dict[str, float] = {}
    for field in fields:
        first = getattr(samples[0], field)
        last = getattr(samples[-1], field)
        if first is None or last is None:
            continue
        rates[f"{field.removeprefix('clickhouse_')}_per_second"] = max(0, last - first) / elapsed
    return rates
