# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistence helpers for standalone agent-eval result bundles."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunResult


def persist_run(result: AgentEvalRunResult, output_dir: str | Path) -> AgentEvalRunResult:
    """Persist a completed run bundle to ``output_dir``."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    _write_json(path / "benchmark.json", result.benchmark)
    _write_jsonl(path / "tasks.jsonl", result.tasks)
    _write_jsonl(path / "attempts.jsonl", result.attempts)
    _write_jsonl(path / "results.jsonl", result.results)
    _write_json(path / "summary.json", result.summary)

    updated = result.model_copy(update={"output_dir": path})
    _write_json(path / "run.json", _run_manifest(updated))
    return updated


def _run_manifest(result: AgentEvalRunResult) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "output_dir": str(result.output_dir) if result.output_dir is not None else None,
        "dashboard_path": str(result.dashboard_path) if result.dashboard_path is not None else None,
        "artifacts": {
            "benchmark": "benchmark.json",
            "tasks": "tasks.jsonl",
            "attempts": "attempts.jsonl",
            "results": "results.jsonl",
            "summary": "summary.json",
        },
    }


def _write_json(path: Path, value: BaseModel | dict[str, Any]) -> None:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[BaseModel]) -> None:
    payload = "\n".join(json.dumps(row.model_dump(mode="json"), sort_keys=True) for row in rows)
    path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")
