# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapt ``nat_runner`` ``result.json`` records into ``AgentEvalAttempt`` values.

This bridges the existing ``nat_runner`` output contract (see
``nat_runner._write_result``) onto the agent-eval SDK so a run that already
produced ``result.json`` can be imported as an attempt without re-executing the
agent. Per the design doc, ``result.json`` carries the attempt *status*,
*measurements* (reward + token/cost), and *provenance*.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluator_agent_eval.artifacts import AgentArtifacts
from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalTask, AgentOutput
from nemo_evaluator_sdk.values.evidence import CandidateEvidence

from runtimes.shared.artifacts import _evidence_descriptors  # reuse documented evidence map
from runtimes.shared.layout import AgenticRunLayout

# Token/cost measurement keys carried in result.json["metrics"].
_METRIC_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "n_assistant_messages",
    "cost_usd",
    "num_turns",
    "duration_ms",
    "token_metrics_status",
    "token_metrics_note",
)


def attempt_from_result_dir(output_dir: str | Path, *, task: AgentEvalTask | None = None) -> AgentEvalAttempt:
    """Load ``<output_dir>/result.json`` and build an attempt from it."""
    output_dir = Path(output_dir)
    result_path = output_dir / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError(f"result.json not found in {output_dir}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    return attempt_from_result(result, output_dir=output_dir, task=task)


def attempt_from_result(
    result: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    task: AgentEvalTask | None = None,
) -> AgentEvalAttempt:
    """Project a ``result.json`` dict onto :class:`AgentEvalAttempt`.

    The attempt ``status`` reflects whether the agent produced a usable
    response (``agent`` phase outcome). Pass/fail from the verifier is recorded
    as a *measurement* in metadata (``reward``/``passed``) so scoring metrics —
    not the runtime — remain the source of truth.
    """
    task_id = str(result.get("task") or (task.id if task is not None else "unknown"))
    backend = str(result.get("agent_backend") or "unknown")
    resolved_dir = Path(output_dir) if output_dir is not None else Path(str(result.get("output_dir") or "."))
    layout = _layout_from_result_dir(resolved_dir)

    agent_phase = str(result.get("agent") or "")
    status = "completed" if agent_phase in {"ok", "skipped"} else "failed"

    output_text, final_extracted, final_source = _resolve_output_text(layout)
    if not output_text:
        output_text = "(agent phase failed)" if status == "failed" else ""

    descriptors = _evidence_descriptors(
        layout, AgentArtifacts.from_dir(layout.agent_log_dir, workspace_dir=layout.workspace_dir)
    )

    metrics = dict(result.get("metrics") or {})
    metadata: dict[str, Any] = {
        # Canonical CapturedAgentAttempt-style provenance fields.
        "agent_runtime": backend,
        "agent_model": result.get("agent_model"),
        "run_id": (result.get("provenance") or {}).get("run_id"),
        "exit_code": 0 if agent_phase in {"ok", "skipped"} else 1,
        "duration_ms": metrics.get("duration_ms"),
        # Phase outcomes from result.json.
        "agent_ok": agent_phase in {"ok", "skipped"},
        "build_status": result.get("build"),
        "agent_status": result.get("agent"),
        "verify_status": result.get("verify"),
        # Measurements (verifier reward is a measurement, not attempt status).
        "passed": result.get("passed"),
        "reward": result.get("reward"),
        "runtime_sec": result.get("runtime_sec"),
        "verifier_scores": result.get("verifier_scores"),
        # Provenance + candidate identity.
        "provenance": result.get("provenance"),
        "candidate_id": result.get("candidate_id"),
        "candidate_params": result.get("candidate_params"),
        "image": result.get("image"),
        "output_dir": str(resolved_dir),
        # Artifact discovery helpers.
        "agent_log_dir": str(layout.agent_log_dir),
        "workspace_dir": str(layout.workspace_dir),
        "state_dir": str(layout.state_dir),
        "final_answer_extracted": final_extracted,
        "final_answer_source": final_source,
    }
    metadata.update({key: metrics.get(key) for key in _METRIC_KEYS})

    return AgentEvalAttempt(
        id=f"{task_id}:{backend}",
        task_id=task_id,
        status=status,
        output=AgentOutput(text=output_text),
        evidence=CandidateEvidence(descriptors=descriptors) if descriptors else None,
        metadata=metadata,
    )


def _layout_from_result_dir(output_dir: Path) -> AgenticRunLayout:
    agent_log_dir = output_dir / "agent"
    return AgenticRunLayout(
        run_dir=output_dir,
        agent_log_dir=agent_log_dir,
        workspace_dir=output_dir / "workspace",
        state_dir=output_dir / "state",
        instruction_path=agent_log_dir / "instruction.md",
    )


def _resolve_output_text(layout: AgenticRunLayout) -> tuple[str, bool, str | None]:
    if not layout.agent_log_dir.is_dir():
        return "", False, None
    artifacts = AgentArtifacts.from_dir(layout.agent_log_dir, workspace_dir=layout.workspace_dir)
    if artifacts.final_answer.extracted and artifacts.final_answer.text:
        return artifacts.final_answer.text, True, artifacts.final_answer.source
    log_path = layout.agent_log_dir / "nat_agent.log"
    if log_path.is_file():
        return log_path.read_text(encoding="utf-8", errors="replace").strip(), False, None
    return "", False, None
