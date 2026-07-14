# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for the host and containerized NeMo Fabric agent-eval runtimes.

:class:`~nemo_evaluator_sdk.agent_eval.runtimes.fabric.runtime.FabricAgentRuntime` (host) and
:class:`~nemo_evaluator_sdk.agent_eval.runtimes.fabric.container_runtime.FabricContainerRuntime`
(sandbox) map a Fabric ``RunResult`` to the *same* trial/evidence contract, so the pieces they share
live here — one definition, so the two runtimes cannot drift apart.

Trajectory capture is built from ``nemo_relay``'s own typed config objects (a hard dependency), so
Relay owns its schema: a breaking Relay change fails construction here rather than silently producing
a malformed profile.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor
from nemo_relay.observability import AtifConfig, AtofConfig, ComponentSpec, ObservabilityConfig

# Trajectory profile identity + the file-exporter output names we choose (Relay accepts these as
# inputs). Shared so both runtimes select/emit the trajectory under identical names.
TRAJECTORY_PROFILE_NAME = "eval_trajectory"
ATIF_FILENAME_TEMPLATE = "trajectory-{session_id}.atif.json"
ATOF_FILENAME = "events.atof.jsonl"
# Fabric telemetry-profile selectors (Relay file exporter, no OTLP endpoint).
TELEMETRY_PROVIDER = "relay"
TELEMETRY_MODE = "sdk"


def safe_path_name(value: str) -> str:
    """Filesystem-safe rendering of an arbitrary id (alnum/``._-`` kept, else ``-``; trimmed to 120)."""
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip(".-")[:120]


def task_subdir_name(index: int, task_id: str) -> str:
    """Deterministic per-task evidence subdir name (``000000-<safe-id>``) shared by both runtimes."""
    safe = safe_path_name(task_id)
    return f"{index:06d}-{safe}" if safe else f"task-{index:06d}"


def extract_output_text(output: object) -> str | None:
    """Pull the user-visible message out of a Fabric output value (already unwrapped from the result).

    Harness outputs vary; adapters commonly nest the final message under ``response`` (the codex-cli
    adapter does). Prefer a string ``response``/``output_text``/``text``/``message``, else stringify.
    """
    if output is None:
        return None
    if isinstance(output, str):
        return output
    if isinstance(output, Mapping):
        for key in ("response", "output_text", "text", "message"):
            value = output.get(key)
            if isinstance(value, str):
                return value
    return json.dumps(output, default=str)


def build_failed_trial(
    task: AgentEvalTask,
    evidence_dir: Path,
    error: Exception | Mapping[str, Any],
    *,
    runtime_name: str,
    trial_id_suffix: str,
    extra_metadata: Mapping[str, Any] | None = None,
) -> AgentEvalTrial:
    """Persist ``error.json`` and build a FAILED trial with the standard error evidence + metadata.

    ``error`` is either a raised exception or a Fabric error mapping (``stage``/``code``/``message``).
    """
    if isinstance(error, Mapping):
        error_type = str(error.get("code") or error.get("stage") or "FabricError")
        error_message = str(error.get("message") or error)
    else:
        error_type = error.__class__.__name__
        error_message = str(error)
    error_path = evidence_dir / "error.json"
    error_path.write_text(json.dumps({"error_type": error_type, "error": error_message}) + "\n", encoding="utf-8")
    return AgentEvalTrial(
        id=f"{task.id}:{trial_id_suffix}",
        task_id=task.id,
        status=AgentEvalTrialStatus.FAILED,
        output=None,
        evidence=CandidateEvidence(
            descriptors={"error": EvidenceDescriptor(kind="error", format="json", ref=str(error_path))},
            metadata={"runtime": runtime_name},
        ),
        metadata={
            **(dict(extra_metadata) if extra_metadata else {}),
            "runtime": runtime_name,
            "error_type": error_type,
            "error": error_message,
            # A failed trial did not complete its agent phase; stamp it explicitly (matching the host
            # Fabric/Codex runtimes) so AgentPhaseSuccessMetric scores it False rather than by omission.
            "agent_ok": False,
        },
    )


def trajectory_telemetry(*, relay_dir: str, agent_name: str, agent_version: str) -> dict[str, Any]:
    """The ``telemetry`` block of a Fabric trajectory profile: Relay's ATIF/ATOF file exporter (mode=sdk).

    Built from ``nemo_relay``'s own typed config so Relay owns its schema — no hand-maintained dict to
    silently drift when Relay changes it. Callers wrap this in a profile with their own name +
    ``runtime``/``environment`` blocks; ``relay_dir`` is where the ``trajectory-*.atif.json`` lands.
    """
    observability = ComponentSpec(
        config=ObservabilityConfig(
            atif=AtifConfig(
                enabled=True,
                output_directory=relay_dir,
                filename_template=ATIF_FILENAME_TEMPLATE,
                agent_name=agent_name,
                agent_version=agent_version,
            ),
            atof=AtofConfig(
                enabled=True,
                output_directory=relay_dir,
                filename=ATOF_FILENAME,
                mode="overwrite",
            ),
        )
    )
    return {
        "enabled": True,
        "provider": TELEMETRY_PROVIDER,
        "mode": TELEMETRY_MODE,
        "output_dir": relay_dir,
        "config": {"version": 1, "components": [observability.to_dict()]},
    }
