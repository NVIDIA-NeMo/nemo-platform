# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Convert captured agent artifacts into AgentEvalAttempt values."""

from __future__ import annotations

from pathlib import Path

from evaluator_agent_eval.artifacts import AgentArtifacts
from evaluator_agent_eval.schemas import (
    AgentAttemptInput,
    AgentAttemptMetadata,
    AgentAttemptOutput,
    AgentAttemptTrace,
    CapturedAgentAttempt,
)
from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalTask, AgentOutput
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

from runtimes.shared.config import AgenticRuntimeName
from runtimes.shared.layout import AgenticRunLayout
from runtimes.shared.usage import extract_usage_metrics


def build_agent_eval_attempt(
    *,
    task: AgentEvalTask,
    layout: AgenticRunLayout,
    runtime_name: AgenticRuntimeName,
    agent_model: str,
    exit_code: int,
    agent_ok: bool,
    run_id: str | None = None,
    repo_revision: str | None = None,
    duration_ms: int | None = None,
) -> AgentEvalAttempt:
    """Build an SDK attempt from on-disk agent artifacts.

    Metadata uses the same canonical keys as :class:`CapturedAgentAttempt`
    (``agent_runtime``, ``agent_model``, ``exit_code``, …) so verify/scoring
    helpers can consume attempts without a second adapter.
    """
    artifacts = AgentArtifacts.from_dir(layout.agent_log_dir, workspace_dir=layout.workspace_dir)
    log_text = _read_agent_log(layout.agent_log_dir)
    usage = extract_usage_metrics(log_text)
    duration = duration_ms if duration_ms is not None else usage.get("duration_ms")

    output_text = artifacts.final_answer.text if artifacts.final_answer.extracted else None
    raw_log_paths = _raw_log_paths(artifacts.agent_log_dir)
    descriptors = _evidence_descriptors(layout, artifacts)

    metadata: dict[str, object] = {
        # Canonical CapturedAgentAttempt fields
        "agent_runtime": runtime_name,
        "agent_model": agent_model,
        "agent_runtime_version": None,
        "repo_revision": repo_revision,
        "run_id": run_id,
        "exit_code": exit_code,
        "duration_ms": duration,
        # SDK / orchestration extensions
        "model_id": agent_model,
        "target_name": agent_model,
        "attempt_id": f"{task.id}:{runtime_name}",
        "agent_ok": agent_ok,
        "agent_log_dir": str(layout.agent_log_dir),
        "workspace_dir": str(layout.workspace_dir),
        "state_dir": str(layout.state_dir),
        "run_dir": str(layout.run_dir),
        "instruction_path": task.metadata.get("instruction_path"),
        "final_answer_extracted": artifacts.final_answer.extracted,
        "final_answer_source": artifacts.final_answer.source,
        "raw_log_paths": raw_log_paths,
        "atif_trajectory_path": str(artifacts.atif_trajectory_path) if artifacts.atif_trajectory_path else None,
        **usage,
    }

    status = "completed"
    if output_text:
        output = AgentOutput(text=output_text)
    elif agent_ok:
        output = AgentOutput(text=log_text.strip() or "")
    else:
        output = AgentOutput(text=log_text.strip() or "(agent phase failed)")

    return AgentEvalAttempt(
        id=f"{task.id}:{runtime_name}",
        task_id=task.id,
        status=status,
        output=output,
        evidence=CandidateEvidence(descriptors=descriptors) if descriptors else None,
        metadata=metadata,
    )


def to_captured_agent_attempt(task: AgentEvalTask, attempt: AgentEvalAttempt) -> CapturedAgentAttempt:
    """Project an SDK attempt onto the portable CapturedAgentAttempt schema."""
    metadata = attempt.metadata
    trace_path = metadata.get("atif_trajectory_path")
    return CapturedAgentAttempt(
        task_id=attempt.task_id,
        input=AgentAttemptInput(
            instruction_text=task.intent,
            instruction_path=str(metadata.get("instruction_path")) if metadata.get("instruction_path") else None,
        ),
        output=AgentAttemptOutput(
            final_text=attempt.output.text if attempt.output is not None else "",
            final_answer_extracted=bool(metadata.get("final_answer_extracted")),
            final_answer_source=str(metadata.get("final_answer_source"))
            if metadata.get("final_answer_source") is not None
            else None,
            raw_log_paths=list(metadata.get("raw_log_paths") or []),
        ),
        metadata=AgentAttemptMetadata(
            agent_runtime=str(metadata.get("agent_runtime", "unknown")),
            agent_model=str(metadata.get("agent_model", "unknown")),
            agent_runtime_version=str(metadata["agent_runtime_version"])
            if metadata.get("agent_runtime_version") is not None
            else None,
            repo_revision=str(metadata["repo_revision"]) if metadata.get("repo_revision") is not None else None,
            run_id=str(metadata["run_id"]) if metadata.get("run_id") is not None else None,
            exit_code=int(metadata["exit_code"]) if isinstance(metadata.get("exit_code"), int) else None,
            duration_ms=int(metadata["duration_ms"]) if isinstance(metadata.get("duration_ms"), int | float) else None,
        ),
        trace=AgentAttemptTrace(atif_path=str(trace_path)) if trace_path else None,
    )


def _evidence_descriptors(layout: AgenticRunLayout, artifacts: AgentArtifacts) -> dict[str, EvidenceDescriptor]:
    """Build the evidence map specified by the agent-eval SDK design doc.

    Keys follow the documented ``nat_runner`` → ``AgentEvalAttempt`` mapping:
    ``final_state`` (workspace), ``trace`` (trajectory, ATIF-normalized),
    ``logs`` (agent log dir), and ``verifier_logs`` (verifier log dir).
    """
    descriptors: dict[str, EvidenceDescriptor] = {}

    # agent/trajectory.json → evidence["trace"], preferably ATIF-normalized.
    if artifacts.atif_trajectory_path is not None:
        descriptors["trace"] = EvidenceDescriptor(
            kind="trace",
            format="atif" if artifacts.atif_trajectory_path.name.startswith("atif") else "json",
            ref=str(artifacts.atif_trajectory_path),
        )

    # agent/ logs → evidence["logs"].
    descriptors["logs"] = EvidenceDescriptor(
        kind="logs",
        format="dir",
        ref=str(layout.agent_log_dir),
        metadata={"primary_log": "nat_agent.log"},
    )

    # workspace/ → evidence["final_state"] filesystem descriptor.
    descriptors["final_state"] = EvidenceDescriptor(
        kind="filesystem",
        format="dir",
        ref=str(layout.workspace_dir),
        metadata={"role": "final_state"},
    )

    # Preserved platform/database state across agent + verifier phases.
    descriptors["state"] = EvidenceDescriptor(
        kind="filesystem",
        format="dir",
        ref=str(layout.state_dir),
        metadata={"role": "platform_state"},
    )

    # verifier/ logs → evidence["verifier_logs"] (present once verify phase runs).
    verifier_log_dir = layout.run_dir / "verifier"
    if verifier_log_dir.exists():
        descriptors["verifier_logs"] = EvidenceDescriptor(
            kind="logs",
            format="dir",
            ref=str(verifier_log_dir),
            metadata={"role": "verifier"},
        )

    return descriptors


def _raw_log_paths(agent_log_dir: Path) -> list[str]:
    if not agent_log_dir.is_dir():
        return []
    return [str(path.relative_to(agent_log_dir)) for path in sorted(agent_log_dir.iterdir()) if path.is_file()]


def _read_agent_log(agent_log_dir: Path) -> str:
    log_path = agent_log_dir / "nat_agent.log"
    if log_path.is_file():
        return log_path.read_text(encoding="utf-8", errors="replace")
    return ""
