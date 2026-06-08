#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Custom ACES grader for the standalone Evaluator SDK agent-target task."""

from __future__ import annotations

import json
import math
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from evaluator_agent_eval.artifacts import AgentArtifacts  # noqa: E402
from evaluator_agent_eval.factory import (  # noqa: E402
    AgentRunMetadata,
    build_evaluator_scoring_row,
    capture_agent_attempt,
)
from evaluator_agent_eval.runner import score_evaluator_rows  # noqa: E402
from evaluator_agent_eval.task_config import load_agentic_use_task_config  # noqa: E402
from task_metrics import AgentTargetConfigurationMetric  # noqa: E402

AGENT_LOG_DIR = Path(os.environ.get("HARBOR_AGENT_LOGS_DIR", "/logs/agent"))
VERIFIER_LOG_DIR = Path(os.environ.get("HARBOR_VERIFIER_DIR", "/logs/verifier"))
REWARD_JSON = VERIFIER_LOG_DIR / "reward.json"
TASK_DIR = Path(os.environ.get("AGENTIC_USE_TASK_DIR", str(TESTS_DIR)))
WORKSPACE_DIR = Path(os.environ.get("AGENTIC_USE_WORKSPACE_DIR", "/workspace"))

TASK_METRIC = AgentTargetConfigurationMetric()
TASK_METRIC_CUSTOM_PREFIX = "evaluator_agent_target"
TASK_METRIC_REASON = "agent-target task metric"


def main() -> None:
    task_config = load_agentic_use_task_config(TASK_DIR)
    artifacts = AgentArtifacts.from_dir(AGENT_LOG_DIR, workspace_dir=_workspace_dir())
    attempt = capture_agent_attempt(
        task_dir=TASK_DIR,
        artifacts=artifacts,
        metadata=AgentRunMetadata(
            agent_runtime=os.environ.get("NAT_AGENT_BACKEND", os.environ.get("HARBOR_AGENT_NAME", "unknown")),
            agent_model=os.environ.get("NAT_AGENT_MODEL", os.environ.get("HARBOR_AGENT_MODEL", "unknown")),
        ),
    )
    attempt = attempt.model_copy(update={"task_id": _task_id(TASK_DIR)})
    scoring_row = build_evaluator_scoring_row(
        task_dir=TASK_DIR,
        attempt=attempt,
        artifacts=artifacts,
        task_config=task_config,
    )
    scored = score_evaluator_rows([scoring_row], additional_metrics=[TASK_METRIC])
    aggregate_scores = _aggregate_scores(scored)
    metric_scores = _custom_metrics(aggregate_scores)
    overall = _overall_score(metric_scores)
    details = {
        "evaluator_agent_eval": {
            "reason": _reason(metric_scores),
            "aggregate_scores": aggregate_scores,
            "row_scores": scored.model_dump(mode="json").get("row_scores", []),
        },
    }
    VERIFIER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    (VERIFIER_LOG_DIR / "evaluator_scores.json").write_text(
        json.dumps(scored.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    REWARD_JSON.write_text(
        json.dumps({"overall": overall, "custom_metrics": metric_scores, "details": details}, indent=2),
        encoding="utf-8",
    )


def _workspace_dir() -> Path:
    if WORKSPACE_DIR.exists():
        return WORKSPACE_DIR
    for candidate in (Path("/workspace"), Path("/solution"), Path("/app/workspace")):
        if candidate.exists():
            return candidate
    return Path("/workspace")


def _task_id(task_dir: Path) -> str:
    task_toml = task_dir / "task.toml"
    if not task_toml.is_file():
        return task_dir.name
    try:
        data = tomllib.loads(task_toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return task_dir.name
    metadata = data.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("entry_id"), str):
        return metadata["entry_id"]
    return task_dir.name


def _aggregate_scores(scored: Any) -> dict[str, float]:
    scores: dict[str, float] = {}
    for score in scored.aggregate_scores.scores:
        if score.mean is None:
            continue
        value = float(score.mean)
        if math.isnan(value):
            continue
        scores[str(score.name)] = value
    return scores


def _custom_metrics(aggregate_scores: dict[str, float]) -> dict[str, float]:
    custom: dict[str, float] = {}
    promoted_metrics = {
        "agent_eval/surface_adherence.surface_adherence": "evaluator_agent_eval_surface_adherence",
        "agent_eval/legacy_surface_avoidance.legacy_surface_avoidance": "evaluator_agent_eval_legacy_surface_avoidance",
        "agent_eval/trajectory_evidence.trajectory_present": "evaluator_agent_eval_trajectory_present",
    }
    promoted_metrics.update(
        {
            f"{TASK_METRIC.type}.{score_name}": f"{TASK_METRIC_CUSTOM_PREFIX}_{score_name}"
            for score_name in TASK_METRIC.score_names()
        }
    )
    for source_name, custom_name in promoted_metrics.items():
        value = aggregate_scores.get(source_name)
        custom[custom_name] = 0.0 if value is None else max(0.0, min(1.0, value))
    return custom


def _overall_score(metric_scores: dict[str, float]) -> float:
    return metric_scores.get(f"{TASK_METRIC_CUSTOM_PREFIX}_task_success", 0.0)


def _reason(metric_scores: dict[str, float]) -> str:
    failed = sorted(name for name, value in metric_scores.items() if value < 1.0)
    if not failed:
        return f"All shared Evaluator agent-eval metrics and the {TASK_METRIC_REASON} passed."
    return f"One or more Evaluator agent-eval metrics failed or were unavailable: {', '.join(failed)}."


if __name__ == "__main__":
    main()
