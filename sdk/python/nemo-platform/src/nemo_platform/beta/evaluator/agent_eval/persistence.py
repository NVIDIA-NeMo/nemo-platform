# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistence helpers for standalone agent-eval result bundles."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalResult
from pydantic import BaseModel


def persist_run(result: AgentEvalResult, output_dir: str | Path) -> AgentEvalResult:
    """Persist a completed run bundle to ``output_dir``."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    _write_json(path / "benchmark.json", result.benchmark)
    _write_jsonl(path / "tasks.jsonl", result.tasks)
    _write_jsonl(path / "trials.jsonl", result.trials)
    _write_jsonl(path / "scores.jsonl", result.scores)
    _write_json(path / "summary.json", result.summary)

    updated = result.model_copy(update={"output_dir": path})
    _write_json(path / "run.json", _run_manifest(updated))
    return updated


def _run_manifest(result: AgentEvalResult) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "output_dir": str(result.output_dir) if result.output_dir is not None else None,
        "dashboard_path": str(result.dashboard_path) if result.dashboard_path is not None else None,
        "artifacts": {
            "benchmark": "benchmark.json",
            "tasks": "tasks.jsonl",
            "trials": "trials.jsonl",
            "scores": "scores.jsonl",
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
    # Stream row-by-row instead of joining the whole payload in memory first.
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")
