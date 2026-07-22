# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed the deterministic Evaluation corpus used by Intake load tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from nmp.intake.benchmarks.loadgen import WORKSPACE, ensure_ready, ensure_workspace

WIDE_GROUP_NAME = "load-test-wide-group"
WIDE_EVALUATION_PREFIX = "load-test-wide-evaluation"
DEEP_GROUP_NAME = "load-test-deep-group"
DEEP_EVALUATION_NAME = "load-test-deep-evaluation"
DATASET_NAME = "load-test-dataset"
_INTAKE_SERVICE_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_OUTPUT_DIR = _INTAKE_SERVICE_ROOT / "benchmarks" / "artifacts" / "evaluation-corpus"
_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class SeedConfig:
    base_url: str
    wide_evaluations: int
    wide_sessions: int
    deep_sessions: int
    spans_per_session: int
    pinned_evaluations: int
    concurrency: int
    checkpoint_size: int
    timeout_seconds: float

    @property
    def total_sessions(self) -> int:
        return self.wide_evaluations * self.wide_sessions + self.deep_sessions

    @property
    def total_spans(self) -> int:
        return self.total_sessions * self.spans_per_session

    @property
    def total_evaluator_results(self) -> int:
        return self.total_sessions * 2


@dataclass(frozen=True)
class EvaluationTarget:
    name: str
    sessions: int


@dataclass(frozen=True)
class RequestResult:
    latency_ms: float
    request_bytes: int


def _intake_root(config: SeedConfig) -> str:
    return f"{config.base_url.rstrip('/')}/apis/intake/v2/workspaces/{WORKSPACE}"


def _targets(config: SeedConfig) -> tuple[EvaluationTarget, ...]:
    wide = tuple(
        EvaluationTarget(name=f"{WIDE_EVALUATION_PREFIX}-{index:03d}", sessions=config.wide_sessions)
        for index in range(config.wide_evaluations)
    )
    return (*wide, EvaluationTarget(name=DEEP_EVALUATION_NAME, sessions=config.deep_sessions))


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    expected: frozenset[int] = frozenset({200, 201}),
) -> dict[str, Any]:
    response = await client.request(method, url, json=json_body)
    if response.status_code not in expected:
        detail = response.text.replace("\n", " ")[:500]
        raise RuntimeError(f"{method} {url} failed ({response.status_code}): {detail}")
    if not response.content:
        return {}
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{method} {url} returned a non-object JSON response")
    return payload


async def _ensure_group(client: httpx.AsyncClient, config: SeedConfig, name: str) -> str:
    url = f"{_intake_root(config)}/experiment-groups"
    body = {
        "name": name,
        "description": "Deterministic corpus for Intake load characterization.",
        "metadata": {"seeded_by": "nmp.intake.benchmarks.evaluation_seed"},
    }
    response = await client.post(url, json=body)
    if response.status_code == 409:
        payload = await _request_json(client, "GET", f"{url}/{name}")
    elif response.status_code == 201:
        payload = response.json()
    else:
        detail = response.text.replace("\n", " ")[:500]
        raise RuntimeError(f"POST {url} failed ({response.status_code}): {detail}")
    group_id = payload.get("id")
    if not isinstance(group_id, str) or not group_id:
        raise RuntimeError(f"Experiment group {name} did not return a valid id")
    return group_id


async def _ensure_evaluation(
    client: httpx.AsyncClient,
    config: SeedConfig,
    target: EvaluationTarget,
    *,
    group_id: str,
) -> None:
    url = f"{_intake_root(config)}/evaluations"
    body = {
        "name": target.name,
        "experiment_group_id": group_id,
        "dataset_name": DATASET_NAME,
        "dataset_version": "v1",
        "description": "Deterministic Intake evaluation load-test corpus.",
        "metadata": {"seeded_by": "nmp.intake.benchmarks.evaluation_seed"},
    }
    response = await client.post(url, json=body)
    if response.status_code == 201:
        return
    if response.status_code != 409:
        detail = response.text.replace("\n", " ")[:500]
        raise RuntimeError(f"POST {url} failed ({response.status_code}): {detail}")
    existing = await _request_json(client, "GET", f"{url}/{target.name}")
    if existing.get("experiment_group_id") != group_id or existing.get("dataset_name") != DATASET_NAME:
        raise RuntimeError(f"Existing Evaluation {target.name} does not match the load-test corpus configuration")


async def _ensure_entities(client: httpx.AsyncClient, config: SeedConfig) -> tuple[str, str]:
    wide_group_id = await _ensure_group(client, config, WIDE_GROUP_NAME)
    deep_group_id = await _ensure_group(client, config, DEEP_GROUP_NAME)
    for index, target in enumerate(_targets(config)):
        group_id = wide_group_id if index < config.wide_evaluations else deep_group_id
        await _ensure_evaluation(client, config, target, group_id=group_id)
        if index < config.pinned_evaluations:
            await _request_json(client, "POST", f"{_intake_root(config)}/evaluations/{target.name}/pin")
    return wide_group_id, deep_group_id


def _session_id(evaluation_name: str, session_index: int) -> str:
    return f"{evaluation_name}-session-{session_index:05d}"


def _atif_body(
    *,
    evaluation_name: str,
    session_index: int,
    spans_per_session: int,
    corpus_started_at: datetime,
) -> dict[str, Any]:
    step_count = spans_per_session - 3
    session_started_at = corpus_started_at + timedelta(milliseconds=session_index)
    steps: list[dict[str, Any]] = []
    for step_offset in range(step_count):
        step_id = step_offset + 1
        source = ("agent", "user", "system")[step_offset % 3]
        step: dict[str, Any] = {
            "step_id": step_id,
            "timestamp": _iso(session_started_at + timedelta(milliseconds=step_offset)),
            "source": source,
            "message": f"load-test-{source}-{step_id}-" + "x" * 128,
        }
        if source == "agent":
            step.update(
                {
                    "model_name": "load-test-provider/load-test-model",
                    "metrics": {
                        "prompt_tokens": 100 + session_index % 101 + step_id,
                        "completion_tokens": 20 + session_index % 31 + step_id,
                        "cached_tokens": session_index % 17,
                        "cost_usd": round(0.0001 + (session_index % 1000) / 10_000_000 + step_id / 100_000_000, 8),
                    },
                }
            )
        if step_offset == 0:
            step["tool_calls"] = [
                {
                    "tool_call_id": "load-test-tool-call",
                    "function_name": "load_test_lookup",
                    "arguments": {"session_index": session_index},
                }
            ]
            step["observation"] = {
                "results": [
                    {
                        "source_call_id": "load-test-tool-call",
                        "content": f"result-{session_index}",
                    }
                ]
            }
        steps.append(step)

    quality = round(0.5 + (session_index % 500) / 1000, 3)
    safety = round(0.7 + (session_index % 300) / 1000, 3)
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": _session_id(evaluation_name, session_index),
        "evaluation_context": {
            "evaluation_id": evaluation_name,
            "test_case_id": f"case-{session_index:05d}",
        },
        "extra": {
            "task_id": f"case-{session_index:05d}",
            "task_name": "intake-load-test",
            "verifier_result": {"rewards": {"quality": quality, "safety": safety}},
        },
        "agent": {
            "name": "intake-load-test-agent",
            "version": "1.0.0",
            "model_name": "load-test-provider/load-test-model",
            "tool_definitions": [{"name": "load_test_lookup"}],
        },
        "steps": steps,
    }


async def _seed_one(
    client: httpx.AsyncClient,
    config: SeedConfig,
    *,
    evaluation_name: str,
    session_index: int,
    corpus_started_at: datetime,
) -> RequestResult:
    body = _atif_body(
        evaluation_name=evaluation_name,
        session_index=session_index,
        spans_per_session=config.spans_per_session,
        corpus_started_at=corpus_started_at,
    )
    encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
    started_at = time.perf_counter()
    response = await client.post(
        f"{_intake_root(config)}/ingest/atif",
        content=encoded,
        headers={"Content-Type": "application/json"},
    )
    latency_ms = (time.perf_counter() - started_at) * 1000
    if response.status_code != 201:
        detail = response.text.replace("\n", " ")[:500]
        raise RuntimeError(
            f"ATIF ingest failed for {evaluation_name} session {session_index} ({response.status_code}): {detail}"
        )
    return RequestResult(latency_ms=latency_ms, request_bytes=len(encoded))


def _load_or_create_manifest(output_dir: Path, config: SeedConfig) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "seed-manifest.json"
    expected_config = asdict(config)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != _MANIFEST_VERSION:
            raise RuntimeError(f"Unsupported seed manifest version in {path}")
        if payload.get("config") != expected_config:
            raise RuntimeError(f"Seed configuration does not match existing manifest at {path}")
        return payload
    now = datetime.now(timezone.utc)
    payload = {
        "version": _MANIFEST_VERSION,
        "config": expected_config,
        "corpus_started_at": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "next_session": {target.name: 0 for target in _targets(config)},
        "request_count": 0,
        "request_bytes": 0,
        "request_latency_ms": [],
        "complete": False,
    }
    _write_manifest(path, payload)
    return payload


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".json.next")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


async def _seed_targets(
    client: httpx.AsyncClient,
    config: SeedConfig,
    *,
    output_dir: Path,
    manifest: dict[str, Any],
) -> None:
    manifest_path = output_dir / "seed-manifest.json"
    corpus_started_at = datetime.fromisoformat(manifest["corpus_started_at"])
    for target in _targets(config):
        next_session = int(manifest["next_session"][target.name])
        while next_session < target.sessions:
            stop = min(next_session + config.checkpoint_size, target.sessions)
            semaphore = asyncio.Semaphore(config.concurrency)

            async def bounded_seed(session_index: int) -> RequestResult:
                async with semaphore:
                    return await _seed_one(
                        client,
                        config,
                        evaluation_name=target.name,
                        session_index=session_index,
                        corpus_started_at=corpus_started_at,
                    )

            results = await asyncio.gather(*(bounded_seed(index) for index in range(next_session, stop)))
            manifest["next_session"][target.name] = stop
            manifest["request_count"] += len(results)
            manifest["request_bytes"] += sum(result.request_bytes for result in results)
            manifest["request_latency_ms"].extend(result.latency_ms for result in results)
            _write_manifest(manifest_path, manifest)
            next_session = stop
            print(f"seeded {target.name}: {next_session}/{target.sessions} sessions", flush=True)


async def _repair_sessions(
    client: httpx.AsyncClient,
    config: SeedConfig,
    *,
    manifest: dict[str, Any],
    repair_sessions: tuple[tuple[str, int], ...],
) -> None:
    if not repair_sessions:
        return
    target_sessions = {target.name: target.sessions for target in _targets(config)}
    corpus_started_at = datetime.fromisoformat(manifest["corpus_started_at"])
    for evaluation_name, session_index in repair_sessions:
        session_count = target_sessions.get(evaluation_name)
        if session_count is None:
            raise RuntimeError(f"Cannot repair unknown Evaluation {evaluation_name}")
        if session_index >= session_count:
            raise RuntimeError(
                f"Cannot repair session {session_index} for {evaluation_name}; nominal count is {session_count}"
            )
        await _seed_one(
            client,
            config,
            evaluation_name=evaluation_name,
            session_index=session_index,
            corpus_started_at=corpus_started_at,
        )
        print(f"repaired {_session_id(evaluation_name, session_index)}", flush=True)


async def _wait_for_rollups(
    client: httpx.AsyncClient,
    config: SeedConfig,
    *,
    wide_group_id: str,
    allowed_deep_session_counts: frozenset[int],
) -> dict[str, Any]:
    list_url = f"{_intake_root(config)}/evaluations"
    params = {
        "filter[experiment_group_id]": wide_group_id,
        "page": 1,
        "page_size": config.wide_evaluations,
    }
    last_wide: dict[str, Any] = {}
    last_deep: dict[str, Any] = {}
    for _ in range(60):
        wide_response = await client.get(list_url, params=params)
        if wide_response.status_code != 200:
            raise RuntimeError(
                f"Wide Evaluation verification failed ({wide_response.status_code}): {wide_response.text[:500]}"
            )
        deep_response = await client.get(f"{list_url}/{DEEP_EVALUATION_NAME}")
        if deep_response.status_code != 200:
            raise RuntimeError(
                f"Deep Evaluation verification failed ({deep_response.status_code}): {deep_response.text[:500]}"
            )
        last_wide = wide_response.json()
        last_deep = deep_response.json()
        wide_rows = last_wide.get("data", [])
        wide_ready = len(wide_rows) == config.wide_evaluations and all(
            row.get("run_count") == config.wide_sessions
            and (row.get("aggregate_scores") or {}).get("quality", {}).get("count") == config.wide_sessions
            and (row.get("aggregate_scores") or {}).get("safety", {}).get("count") == config.wide_sessions
            for row in wide_rows
        )
        deep_run_count = last_deep.get("run_count")
        deep_ready = deep_run_count in allowed_deep_session_counts and all(
            (last_deep.get("aggregate_scores") or {}).get(name, {}).get("count") == deep_run_count
            for name in ("quality", "safety")
        )
        if wide_ready and deep_ready:
            return {"wide": last_wide, "deep": last_deep}
        await asyncio.sleep(0.5)
    raise RuntimeError(
        "Evaluation rollups did not converge: "
        f"wide_rows={len(last_wide.get('data', []))}, deep_run_count={last_deep.get('run_count')}"
    )


async def _add_limit_probe_session(
    client: httpx.AsyncClient,
    config: SeedConfig,
    *,
    corpus_started_at: datetime,
    output_dir: Path,
) -> None:
    result = await _seed_one(
        client,
        config,
        evaluation_name=DEEP_EVALUATION_NAME,
        session_index=config.deep_sessions,
        corpus_started_at=corpus_started_at,
    )
    url = f"{_intake_root(config)}/evaluations/{DEEP_EVALUATION_NAME}"
    last_run_count: int | None = None
    for _ in range(60):
        payload = await _request_json(client, "GET", url)
        raw_run_count = payload.get("run_count")
        last_run_count = raw_run_count if isinstance(raw_run_count, int) else None
        score_counts = {
            name: aggregate.get("count")
            for name, aggregate in (payload.get("aggregate_scores") or {}).items()
            if isinstance(aggregate, dict)
        }
        if last_run_count == config.deep_sessions + 1 and score_counts == {
            "quality": config.deep_sessions + 1,
            "safety": config.deep_sessions + 1,
        }:
            (output_dir / "limit-probe-seed.json").write_text(
                json.dumps(
                    {
                        "evaluation_name": DEEP_EVALUATION_NAME,
                        "session_id": _session_id(DEEP_EVALUATION_NAME, config.deep_sessions),
                        "session_count": last_run_count,
                        "spans_added": config.spans_per_session,
                        "evaluator_results_added": 2,
                        "request_latency_ms": result.latency_ms,
                        "request_bytes": result.request_bytes,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return
        await asyncio.sleep(0.5)
    raise RuntimeError(f"10,001-session probe row did not become visible; last run_count={last_run_count}")


def _summary(config: SeedConfig, manifest: dict[str, Any], rollups: dict[str, Any]) -> dict[str, Any]:
    latencies = [float(value) for value in manifest["request_latency_ms"]]
    return {
        "workspace": WORKSPACE,
        "wide_group": WIDE_GROUP_NAME,
        "wide_group_id": rollups["wide"]["data"][0]["experiment_group_id"],
        "wide_evaluations": config.wide_evaluations,
        "wide_sessions_per_evaluation": config.wide_sessions,
        "deep_group": DEEP_GROUP_NAME,
        "deep_evaluation": DEEP_EVALUATION_NAME,
        "deep_sessions": config.deep_sessions,
        "spans_per_session": config.spans_per_session,
        "expected_sessions": config.total_sessions,
        "expected_spans": config.total_spans,
        "expected_evaluator_results": config.total_evaluator_results,
        "successful_requests": manifest["request_count"],
        "request_bytes": manifest["request_bytes"],
        "request_latency_ms": {
            "mean": statistics.fmean(latencies) if latencies else 0.0,
            "max": max(latencies, default=0.0),
        },
        "verification": {
            "wide_evaluation_count": len(rollups["wide"]["data"]),
            "wide_run_counts": sorted({row["run_count"] for row in rollups["wide"]["data"]}),
            "deep_run_count": rollups["deep"]["run_count"],
            "deep_score_counts": {
                name: aggregate["count"]
                for name, aggregate in sorted((rollups["deep"].get("aggregate_scores") or {}).items())
            },
        },
    }


async def run(
    config: SeedConfig,
    *,
    output_dir: Path,
    add_limit_probe_session: bool,
    repair_sessions: tuple[tuple[str, int], ...],
) -> dict[str, Any]:
    if config.spans_per_session < 4:
        raise RuntimeError("--spans-per-session must be at least 4")
    if config.pinned_evaluations > config.wide_evaluations:
        raise RuntimeError("--pinned-evaluations cannot exceed --wide-evaluations")
    manifest = _load_or_create_manifest(output_dir, config)
    limits = httpx.Limits(max_connections=config.concurrency, max_keepalive_connections=config.concurrency)
    async with httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(config.timeout_seconds)) as client:
        await ensure_ready(client, config.base_url)
        await ensure_workspace(client, config.base_url)
        wide_group_id, _deep_group_id = await _ensure_entities(client, config)
        await _seed_targets(client, config, output_dir=output_dir, manifest=manifest)
        await _repair_sessions(
            client,
            config,
            manifest=manifest,
            repair_sessions=repair_sessions,
        )
        allowed_deep_session_counts = (
            frozenset({config.deep_sessions, config.deep_sessions + 1})
            if add_limit_probe_session
            else frozenset({config.deep_sessions})
        )
        rollups = await _wait_for_rollups(
            client,
            config,
            wide_group_id=wide_group_id,
            allowed_deep_session_counts=allowed_deep_session_counts,
        )
        if add_limit_probe_session:
            await _add_limit_probe_session(
                client,
                config,
                corpus_started_at=datetime.fromisoformat(manifest["corpus_started_at"]),
                output_dir=output_dir,
            )
    summary = _summary(config, manifest, rollups)
    manifest["complete"] = True
    _write_manifest(output_dir / "seed-manifest.json", manifest)
    (output_dir / "seed-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NMP_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--wide-evaluations", type=_positive_int, default=100)
    parser.add_argument("--wide-sessions", type=_positive_int, default=100)
    parser.add_argument("--deep-sessions", type=_positive_int, default=10_000)
    parser.add_argument("--spans-per-session", type=_positive_int, default=20)
    parser.add_argument("--pinned-evaluations", type=_non_negative_int, default=20)
    parser.add_argument("--concurrency", type=_positive_int, default=32)
    parser.add_argument("--checkpoint-size", type=_positive_int, default=100)
    parser.add_argument("--timeout-seconds", type=_positive_float, default=60.0)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--add-limit-probe-session",
        action="store_true",
        help="After nominal verification, add session 10,001 for the metric-sort 413 probe.",
    )
    parser.add_argument(
        "--repair-session",
        action="append",
        type=_repair_session,
        default=[],
        metavar="EVALUATION:INDEX",
        help="Regenerate one nominal session from the persisted corpus timestamp; may be repeated.",
    )
    return parser


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _repair_session(value: str) -> tuple[str, int]:
    evaluation_name, separator, raw_index = value.rpartition(":")
    if not separator or not evaluation_name:
        raise argparse.ArgumentTypeError("repair session must be EVALUATION:INDEX")
    try:
        session_index = int(raw_index)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("repair session index must be an integer") from exc
    if session_index < 0:
        raise argparse.ArgumentTypeError("repair session index must be at least 0")
    return evaluation_name, session_index


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def main() -> None:
    args = build_parser().parse_args()
    config = SeedConfig(
        base_url=args.base_url,
        wide_evaluations=args.wide_evaluations,
        wide_sessions=args.wide_sessions,
        deep_sessions=args.deep_sessions,
        spans_per_session=args.spans_per_session,
        pinned_evaluations=args.pinned_evaluations,
        concurrency=args.concurrency,
        checkpoint_size=args.checkpoint_size,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        summary = asyncio.run(
            run(
                config,
                output_dir=args.output_dir,
                add_limit_probe_session=args.add_limit_probe_session,
                repair_sessions=tuple(args.repair_session),
            )
        )
    except (OSError, RuntimeError, httpx.HTTPError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Evaluation corpus seed failed: {exc}") from exc
    print(
        f"Evaluation corpus ready: {summary['expected_sessions']} sessions, "
        f"{summary['expected_spans']} spans, {summary['expected_evaluator_results']} evaluator results"
    )
    print(f"Artifacts: {args.output_dir}")


if __name__ == "__main__":
    main()
