# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for shaping :class:`AgentEvalAttempt` values from runtime artifacts.

These are the runtime-agnostic pieces: the *scorable* status mapping and the
standard evidence-key builder. Platform-specific attempt construction (reading
proprietary artifact layouts, extra evidence keys) composes these in the adapter.
"""

from __future__ import annotations

from pathlib import Path

from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttemptStatus
from nemo_evaluator_sdk.values.evidence import EvidenceDescriptor


def resolve_attempt_status(agent_ok: bool) -> AgentEvalAttemptStatus:
    """Map an agent-phase outcome to a *scorable* attempt status.

    :class:`~nemo_evaluator_sdk.agent_eval.evaluator.AgentEvaluator` excludes
    ``status=="failed"`` from scoring (it short-circuits to a failed metric
    result). An agent that ran but did not succeed must still be scored — e.g. as
    a ``0`` — so pass-rate gating counts it instead of dropping it. We therefore
    use ``"partial"`` for an executed-but-unsuccessful agent and reserve
    ``"failed"`` for genuine attempt-*production* failures (which a runtime
    surfaces by raising, not by emitting an unscorable attempt).
    """
    return "completed" if agent_ok else "partial"


def standard_evidence_descriptors(
    *,
    logs_dir: str | Path,
    final_state_dir: str | Path,
    trace_path: str | Path | None = None,
    initial_state_ref: str | None = None,
    verifier_logs_dir: str | Path | None = None,
    primary_log: str | None = None,
) -> dict[str, EvidenceDescriptor]:
    """Build the documented evidence map for an agent-eval attempt.

    Standard keys: ``initial_state`` (task input filesystem, when staged),
    ``trace`` (trajectory, ATIF-normalized when available), ``logs`` (agent log
    dir), ``final_state`` (workspace), and ``verifier_logs`` (only when present).
    Callers may add their own extension keys to the returned mapping.
    """
    descriptors: dict[str, EvidenceDescriptor] = {}

    if initial_state_ref:
        descriptors["initial_state"] = EvidenceDescriptor(
            kind="filesystem",
            format="dir",
            ref=str(initial_state_ref),
            metadata={"role": "initial_state"},
        )

    if trace_path is not None:
        trace_name = Path(trace_path).name
        descriptors["trace"] = EvidenceDescriptor(
            kind="trace",
            format="atif" if trace_name.startswith("atif") else "json",
            ref=str(trace_path),
        )

    logs_metadata = {"primary_log": primary_log} if primary_log else {}
    descriptors["logs"] = EvidenceDescriptor(
        kind="logs",
        format="dir",
        ref=str(logs_dir),
        metadata=logs_metadata,
    )

    descriptors["final_state"] = EvidenceDescriptor(
        kind="filesystem",
        format="dir",
        ref=str(final_state_dir),
        metadata={"role": "final_state"},
    )

    if verifier_logs_dir is not None and Path(verifier_logs_dir).exists():
        descriptors["verifier_logs"] = EvidenceDescriptor(
            kind="logs",
            format="dir",
            ref=str(verifier_logs_dir),
            metadata={"role": "verifier"},
        )

    return descriptors
