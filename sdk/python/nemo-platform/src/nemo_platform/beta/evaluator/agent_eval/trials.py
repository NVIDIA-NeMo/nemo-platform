# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trial artifacts, the runtime/serde interfaces that produce them, and the
runtime-agnostic helpers for shaping trials from artifacts (status mapping +
the standard evidence-key builder)."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.values import Agent, Model
from nemo_platform.beta.evaluator.values.evidence import (
    EVIDENCE_FINAL_STATE,
    EVIDENCE_FORMAT_ATIF,
    EVIDENCE_FORMAT_JSON,
    EVIDENCE_INITIAL_STATE,
    EVIDENCE_LOGS,
    EVIDENCE_TRACE,
    EVIDENCE_VERIFIER_LOGS,
    CandidateEvidence,
    EvidenceDescriptor,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class AgentEvalTrialStatus(str, Enum):
    """Lifecycle status for a trial: completed, failed, or partial."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentOutput(BaseModel):
    """Captured final output from the evaluated agent, model, or imported baseline for a trial."""

    model_config = ConfigDict(extra="forbid")

    output_text: str | None = Field(
        default=None,
        description="User-visible final text produced by the agent, if any.",
    )
    response: JsonValue | None = Field(
        default=None,
        description="Final response payload produced by the agent, if any. Any JSON value — a "
        "structured object, or a raw JSON string/array for agents that don't return an object.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the agent output.",
    )


class AgentEvalTrial(BaseModel):
    """Durable trial artifact for one task: output, evidence, status, and metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for this trial.")
    task_id: str = Field(description="Identifier of the AgentEvalTask this trial was produced for.")
    status: AgentEvalTrialStatus = Field(description="Lifecycle status of the trial.")
    output: AgentOutput | None = Field(
        default=None,
        description="Final agent output captured for the trial; required when status is completed.",
    )
    evidence: CandidateEvidence | None = Field(
        default=None,
        description="Named evidence descriptors (final state, traces, logs, ...) captured for the trial.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the trial.",
    )

    @field_validator("id", "task_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("trial id and task_id must not be empty")
        return value

    @model_validator(mode="after")
    def _completed_trial_requires_output(self) -> AgentEvalTrial:
        if self.status == AgentEvalTrialStatus.COMPLETED and self.output is None:
            raise ValueError("completed trial requires output")
        return self


@runtime_checkable
class AgentTaskRunner(Protocol):
    """Online execution interface that runs tasks and produces trials."""

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalTrial]: ...


@runtime_checkable
class AgentTrialSerde(Protocol):
    """Read/write a single stored trial artifact as an :class:`AgentEvalTrial`.

    The offline counterpart to :class:`AgentTaskRunner`: instead of *executing* an
    agent it adapts a stored artifact (a run dir/file) to and from a trial, so prior
    runs can be re-scored. The SDK ships only the protocol; concrete codecs (which
    know a particular on-disk layout) live with their producers.
    """

    def read(self) -> AgentEvalTrial: ...

    def write(self, trial: AgentEvalTrial) -> None: ...


AgentEvalTarget = Model | Agent | AgentTaskRunner


def resolve_trial_status(agent_ok: bool) -> AgentEvalTrialStatus:
    """Map an agent-phase outcome to a *scorable* trial status.

    ``AgentEvaluator`` excludes ``FAILED`` trials from scoring, so an
    executed-but-unsuccessful agent uses ``PARTIAL`` (still scored as ``0`` for
    pass-rate gating); ``FAILED`` is reserved for trial-*production* failures,
    which a runtime surfaces by raising rather than emitting an unscorable trial.
    """
    return AgentEvalTrialStatus.COMPLETED if agent_ok else AgentEvalTrialStatus.PARTIAL


def standard_evidence_descriptors(
    *,
    logs_dir: str | Path,
    final_state_dir: str | Path,
    trace_path: str | Path | None = None,
    initial_state_ref: str | None = None,
    verifier_logs_dir: str | Path | None = None,
    primary_log: str | None = None,
) -> dict[str, EvidenceDescriptor]:
    """Build the documented evidence map for an agent-eval trial.

    Standard keys: ``initial_state`` (task input filesystem, when staged),
    ``trace`` (trajectory, ATIF-normalized when available), ``logs`` (agent log
    dir), ``final_state`` (workspace), and ``verifier_logs`` (only when present).
    Callers may add their own extension keys to the returned mapping.
    """
    descriptors: dict[str, EvidenceDescriptor] = {}

    if initial_state_ref:
        descriptors[EVIDENCE_INITIAL_STATE] = EvidenceDescriptor(
            kind="filesystem",
            format="dir",
            ref=str(initial_state_ref),
            metadata={"role": EVIDENCE_INITIAL_STATE},
        )

    if trace_path is not None:
        trace_name = Path(trace_path).name.lower()
        is_atif = trace_name.startswith("atif") or ".atif." in trace_name
        descriptors[EVIDENCE_TRACE] = EvidenceDescriptor(
            kind=EVIDENCE_TRACE,
            format=EVIDENCE_FORMAT_ATIF if is_atif else EVIDENCE_FORMAT_JSON,
            ref=str(trace_path),
        )

    logs_metadata = {"primary_log": primary_log} if primary_log else {}
    descriptors[EVIDENCE_LOGS] = EvidenceDescriptor(
        kind="logs",
        format="dir",
        ref=str(logs_dir),
        metadata=logs_metadata,
    )

    descriptors[EVIDENCE_FINAL_STATE] = EvidenceDescriptor(
        kind="filesystem",
        format="dir",
        ref=str(final_state_dir),
        metadata={"role": EVIDENCE_FINAL_STATE},
    )

    if verifier_logs_dir is not None and Path(verifier_logs_dir).exists():
        descriptors[EVIDENCE_VERIFIER_LOGS] = EvidenceDescriptor(
            kind="logs",
            format="dir",
            ref=str(verifier_logs_dir),
            metadata={"role": "verifier"},
        )

    return descriptors
