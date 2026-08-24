# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapt one Harbor result directory into an SDK :class:`AgentEvalTrial`.

This module owns the complete Harbor trial-data seam: identity, reward and error
normalization, measurements, and collision-safe evidence discovery. Harbor job
execution and result-file discovery remain in :mod:`harbor_runtime`.
"""

from __future__ import annotations

import contextlib
import logging
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from nemo_evaluator_sdk.agent_eval.trials import (
    UNKNOWN_ERROR_TYPE,
    AgentEvalTrial,
    AgentEvalTrialStatus,
    AgentOutput,
    TrialError,
    standard_evidence_descriptors,
)
from nemo_evaluator_sdk.values.evidence import (
    EVIDENCE_FORMAT_ATIF,
    EVIDENCE_FORMAT_JSON,
    EVIDENCE_FORMAT_OTLP,
    EVIDENCE_FORMAT_TEXT,
    EVIDENCE_TRACE,
    CandidateEvidence,
    EvidenceDescriptor,
    read_atif,
)

logger = logging.getLogger(__name__)

_ATIF_TRACE_SUFFIX = ".atif.json"
_TRIAL_DIR_DESCRIPTION = (
    "Harbor trial output directory for one task attempt. Contains config.json, result.json, "
    "trial.log, agent logs, verifier logs, and collected artifacts."
)
_TRIAL_CONFIG_DESCRIPTION = (
    "Harbor trial configuration snapshot. Records the task, agent, environment, verifier, "
    "artifact collection, and job id used for this attempt."
)
_TRIAL_RESULT_DESCRIPTION = (
    "Harbor trial result JSON. Contains task and trial identifiers, agent info, verifier rewards, "
    "exception info, phase timings, and token or cost usage."
)
_TRIAL_LOG_DESCRIPTIONS = {
    "agent/oracle.txt": "Oracle-agent log captured when Harbor runs the reference solution.",
    "agent/setup/stdout.txt": "Agent setup stdout captured while Harbor uploads the agent and installs dependencies.",
    "exception.txt": "Exception traceback captured by Harbor for a failed trial.",
    "trial.log": (
        "Harbor trial orchestration log covering environment setup, agent execution, verifier execution, "
        "artifact collection, and cleanup."
    ),
    "verifier/reward.json": (
        "Verifier reward JSON written under /logs/verifier. Harbor parses numeric entries from this file "
        "as trial metrics."
    ),
    "verifier/reward.txt": (
        "Verifier scalar reward file written under /logs/verifier. Harbor parses this file as the reward metric."
    ),
    "verifier/test-stderr.txt": "Verifier stderr captured while Harbor runs the task tests from the /tests directory.",
    "verifier/test-stdout.txt": "Verifier stdout captured while Harbor runs the task tests from the /tests directory.",
}
_MAX_TRACEBACK_CHARS = 8192


def _trial_from_harbor_result(
    trial_dir: Path,
    data: Mapping[str, Any],
    *,
    reward_key: str,
    trace_format: Literal["otlp", "atif"] = EVIDENCE_FORMAT_ATIF,
) -> AgentEvalTrial:
    """Normalize one completed Harbor attempt into an SDK trial.

    Args:
        trial_dir: Directory containing the Harbor attempt result and evidence files.
        data: Parsed contents of the attempt's ``result.json`` file.
        reward_key: Verifier reward name to expose as the trial's primary reward.
        trace_format: Trace format whose first discovered artifact should be exposed
            under the standard ``trace`` evidence key.

    Returns:
        The normalized trial, including its identity, reward, error, measurements,
        and evidence descriptors.
    """
    task_id = str(data["task_name"])
    trial_id = str(data.get("trial_name") or trial_dir.name)
    rewards = _rewards_mapping(data)
    reward = _primary_reward(rewards, reward_key)
    error = _trial_error(data.get("exception_info"))

    metadata: dict[str, Any] = {
        "reward": reward,
        "reward_details": dict(rewards),
        "harbor_trial_dir": str(trial_dir),
    }
    metadata.update(_trial_measurements(data))

    # An errored trial (or one with no reward) stays PARTIAL so it is still scored
    # as 0 and counted in the summary; FAILED would exclude it from scoring.
    status = AgentEvalTrialStatus.COMPLETED if error is None and reward is not None else AgentEvalTrialStatus.PARTIAL

    extension_descriptors, selected_trace = _harbor_extension_evidence(trial_dir, trace_format=trace_format)
    descriptors = standard_evidence_descriptors(
        logs_dir=(trial_dir / "agent").resolve(),
        final_state_dir=(trial_dir / "artifacts").resolve(),
        verifier_logs_dir=(trial_dir / "verifier").resolve(),
    )
    descriptors.update(extension_descriptors)
    if selected_trace is not None:
        descriptors[EVIDENCE_TRACE] = selected_trace

    return AgentEvalTrial(
        id=trial_id,
        task_id=task_id,
        status=status,
        output=AgentOutput(metadata={"harbor_trial_dir": str(trial_dir)}),
        evidence=CandidateEvidence(descriptors=descriptors),
        error=error,
        metadata=metadata,
    )


def _description_metadata(description: str, *, trace_format: str | None = None) -> dict[str, str]:
    """Build common evidence metadata.

    Args:
        description: Human-readable explanation of the evidence artifact.
        trace_format: Optional trace encoding to record for trace artifacts.

    Returns:
        Evidence metadata containing the description and, when supplied, the trace
        format.
    """
    metadata = {"description": description}
    if trace_format is not None:
        metadata["trace_format"] = trace_format
    return metadata


def _add_extension_descriptor(
    descriptors: dict[str, EvidenceDescriptor],
    *,
    family: str,
    relative_path: Path,
    descriptor: EvidenceDescriptor,
) -> None:
    """Register an extension descriptor under canonical and compatible keys.

    The canonical key includes the complete trial-relative path, for example
    ``artifact:artifacts/output.txt``. This keeps the mapping injective when a
    trial contains both ``output.txt`` and ``artifacts/output.txt``.

    Older Experimentalist consumers removed the leading ``artifacts/`` directory
    while naming collected artifacts, so they look up the same file through the
    legacy alias ``artifact:output.txt``. The alias is retained during migration
    to avoid breaking those consumers. ``setdefault`` ensures that an alias never
    replaces an exact key belonging to another file.

    Args:
        descriptors: Mutable evidence mapping to update.
        family: Evidence key prefix, such as ``artifact``, ``log``, or ``trace``.
        relative_path: Artifact path relative to the Harbor trial directory.
        descriptor: Descriptor that points to the artifact.

    Returns:
        None. The supplied ``descriptors`` mapping is updated in place.
    """
    descriptors[f"{family}:{relative_path.as_posix()}"] = descriptor
    if relative_path.parts and relative_path.parts[0] == "artifacts" and len(relative_path.parts) > 1:
        legacy_path = Path(*relative_path.parts[1:]).as_posix()
        descriptors.setdefault(f"{family}:{legacy_path}", descriptor)


def _is_trial_log_path(relative_path: str) -> bool:
    """Determine whether a trial-relative path is a known Harbor log.

    Args:
        relative_path: POSIX-style path relative to the Harbor trial directory.

    Returns:
        ``True`` for a known Harbor log or agent command stdout file; otherwise
        ``False``.
    """
    if relative_path in _TRIAL_LOG_DESCRIPTIONS:
        return True
    parts = relative_path.split("/")
    return len(parts) == 3 and parts[0] == "agent" and parts[1].startswith("command-") and parts[2] == "stdout.txt"


def _trace_artifact_format(relative_path: Path) -> Literal["otlp", "atif"] | None:
    """Identify the supported trace format encoded by an artifact path.

    Args:
        relative_path: Artifact path relative to the Harbor trial directory.

    Returns:
        ``"atif"`` or ``"otlp"`` for a supported file below a ``traces``
        directory, or ``None`` when the path is not a recognized trace artifact.
    """
    if "traces" not in relative_path.parts[:-1]:
        return None
    if relative_path.as_posix().endswith(_ATIF_TRACE_SUFFIX):
        return EVIDENCE_FORMAT_ATIF
    if relative_path.suffix == ".jsonl":
        return EVIDENCE_FORMAT_OTLP
    return None


def _display_artifact_path(relative_path: Path) -> Path:
    """Produce the historical display path for a Harbor artifact.

    Args:
        relative_path: Artifact path relative to the Harbor trial directory.

    Returns:
        The path without a leading ``artifacts/`` component when present, or the
        original relative path otherwise.
    """
    if relative_path.parts and relative_path.parts[0] == "artifacts" and len(relative_path.parts) > 1:
        return Path(*relative_path.parts[1:])
    return relative_path


def _harbor_extension_evidence(
    trial_dir: Path,
    *,
    trace_format: Literal["otlp", "atif"],
) -> tuple[dict[str, EvidenceDescriptor], EvidenceDescriptor | None]:
    """Describe every Harbor trial file and select the standard trace.

    Every discovered file remains available through an extension evidence key.
    The first trace matching ``trace_format`` is additionally returned for the
    standard ``trace`` key; ATIF's historical ``agent/trajectory.json`` location
    is used as a fallback for ATIF selection.

    Args:
        trial_dir: Harbor attempt directory to inspect recursively.
        trace_format: Trace encoding to expose through the standard ``trace`` key.

    Returns:
        A pair containing all discovered extension descriptors and the selected
        standard trace descriptor, or ``None`` when no matching trace exists.
    """
    descriptors: dict[str, EvidenceDescriptor] = {
        "trial_dir": EvidenceDescriptor(
            kind="filesystem",
            format="dir",
            ref=str(trial_dir.resolve()),
            metadata=_description_metadata(_TRIAL_DIR_DESCRIPTION),
        )
    }
    collected_traces: dict[str, EvidenceDescriptor | None] = {
        EVIDENCE_FORMAT_OTLP: None,
        EVIDENCE_FORMAT_ATIF: None,
    }
    legacy_atif: EvidenceDescriptor | None = None

    try:
        files = sorted(path for path in trial_dir.rglob("*") if path.is_file())
    except OSError as exc:
        logger.warning("Could not enumerate Harbor trial evidence under %s: %s", trial_dir, exc)
        files = []

    for path in files:
        relative_path = path.relative_to(trial_dir)
        relative_name = relative_path.as_posix()
        try:
            ref = str(path.resolve())
        except OSError as exc:
            logger.warning("Skipping unreadable Harbor trial evidence %s: %s", path, exc)
            continue

        if relative_name == "config.json":
            descriptor = EvidenceDescriptor(
                kind="json",
                format=EVIDENCE_FORMAT_JSON,
                ref=ref,
                metadata=_description_metadata(_TRIAL_CONFIG_DESCRIPTION),
            )
            descriptors["config"] = descriptor
            _add_extension_descriptor(
                descriptors,
                family="json",
                relative_path=relative_path,
                descriptor=descriptor,
            )
            continue
        if relative_name == "result.json":
            descriptor = EvidenceDescriptor(
                kind="json",
                format=EVIDENCE_FORMAT_JSON,
                ref=ref,
                metadata=_description_metadata(_TRIAL_RESULT_DESCRIPTION),
            )
            descriptors["result"] = descriptor
            _add_extension_descriptor(
                descriptors,
                family="json",
                relative_path=relative_path,
                descriptor=descriptor,
            )
            continue

        discovered_format = _trace_artifact_format(relative_path)
        if discovered_format is not None:
            display_path = _display_artifact_path(relative_path).as_posix()
            description = (
                f"Agent execution ATIF trajectory for {display_path}."
                if discovered_format == EVIDENCE_FORMAT_ATIF
                else f"Agent execution trace JSONL for {display_path}."
            )
            descriptor = EvidenceDescriptor(
                kind=EVIDENCE_TRACE,
                format=discovered_format,
                ref=ref,
                metadata=_description_metadata(description, trace_format=discovered_format),
            )
            _add_extension_descriptor(
                descriptors,
                family=EVIDENCE_TRACE,
                relative_path=relative_path,
                descriptor=descriptor,
            )
            if collected_traces[discovered_format] is None:
                collected_traces[discovered_format] = descriptor
            continue

        if relative_name == "agent/trajectory.json" and read_atif(path) is not None:
            descriptor = EvidenceDescriptor(
                kind=EVIDENCE_TRACE,
                format=EVIDENCE_FORMAT_ATIF,
                ref=ref,
                metadata=_description_metadata(
                    "Collected Harbor artifact agent/trajectory.json.",
                    trace_format=EVIDENCE_FORMAT_ATIF,
                ),
            )
            _add_extension_descriptor(
                descriptors,
                family=EVIDENCE_TRACE,
                relative_path=relative_path,
                descriptor=descriptor,
            )
            legacy_atif = descriptor
            continue

        if _is_trial_log_path(relative_name):
            description = _TRIAL_LOG_DESCRIPTIONS.get(relative_name)
            if description is None and relative_name.startswith("agent/command-"):
                description = "Agent command stdout captured while Harbor runs the benchmark agent."
            descriptor = EvidenceDescriptor(
                kind="log",
                format=EVIDENCE_FORMAT_JSON if path.suffix == ".json" else EVIDENCE_FORMAT_TEXT,
                ref=ref,
                metadata=_description_metadata(description or f"Harbor trial log {relative_name}."),
            )
            _add_extension_descriptor(
                descriptors,
                family="log",
                relative_path=relative_path,
                descriptor=descriptor,
            )
            continue

        display_path = _display_artifact_path(relative_path).as_posix()
        description = f"Collected Harbor artifact {display_path}."
        if relative_path.parts[0] == "artifacts" and display_path == "manifest.json":
            description = (
                "Harbor artifact manifest. Lists collected artifact files and the environment paths they were "
                "copied from."
            )
        descriptor = EvidenceDescriptor(
            kind="artifact",
            ref=ref,
            metadata=_description_metadata(description),
        )
        _add_extension_descriptor(
            descriptors,
            family="artifact",
            relative_path=relative_path,
            descriptor=descriptor,
        )

    selected = collected_traces[trace_format]
    if selected is None and trace_format == EVIDENCE_FORMAT_ATIF:
        selected = legacy_atif
    other_format = EVIDENCE_FORMAT_OTLP if trace_format == EVIDENCE_FORMAT_ATIF else EVIDENCE_FORMAT_ATIF
    other = collected_traces[other_format]
    if other is None and other_format == EVIDENCE_FORMAT_ATIF:
        other = legacy_atif
    if selected is None and other is not None:
        logger.warning(
            "Trial %s: configured trace_format='%s' matched no trace artifact, but %s artifacts are present. "
            "This trial will have no trace — set trace_format='%s' if the agent under test emits %s.",
            trial_dir.name,
            trace_format,
            other_format,
            other_format,
            other_format.upper(),
        )
    return descriptors, selected


def _rewards_mapping(data: Mapping[str, Any]) -> dict[str, float]:
    """Normalize Harbor verifier rewards into numeric SDK values.

    Args:
        data: Parsed Harbor ``result.json`` payload.

    Returns:
        A string-keyed mapping of rewards that can be converted to ``float``.
        Missing, malformed, and non-numeric reward entries are omitted.
    """
    verifier_result = data.get("verifier_result")
    if not isinstance(verifier_result, Mapping):
        return {}
    rewards = verifier_result.get("rewards")
    if not isinstance(rewards, Mapping):
        return {}
    out: dict[str, float] = {}
    for key, value in rewards.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _primary_reward(rewards: Mapping[str, float], reward_key: str) -> float | None:
    """Select the configured primary reward.

    Args:
        rewards: Normalized verifier rewards keyed by reward name.
        reward_key: Reward name selected by the runtime configuration.

    Returns:
        The selected reward, or ``None`` when ``reward_key`` is absent. A warning
        is emitted when other rewards exist but none matches the configured key.
    """
    if reward_key in rewards:
        return rewards[reward_key]
    if rewards:
        logger.warning(
            "Harbor trial emitted rewards %s but none matches reward_key=%r; treating the trial as having no reward",
            sorted(rewards),
            reward_key,
        )
    return None


def _trial_error(exception_info: Any) -> TrialError | None:
    """Normalize any Harbor ``exception_info`` shape without raising.

    Args:
        exception_info: Exception payload emitted by Harbor, which may be a
            mapping, scalar value, or ``None``.

    Returns:
        A normalized trial error with a bounded traceback, or ``None`` when Harbor
        reported no exception.
    """
    if exception_info is None:
        return None
    if not isinstance(exception_info, Mapping):
        return TrialError(type=str(exception_info).strip() or UNKNOWN_ERROR_TYPE)

    error_type = ""
    for key in ("exception_type", "type", "name", "class"):
        value = exception_info.get(key)
        if isinstance(value, str) and value.strip():
            error_type = value
            break

    traceback = _first_string(exception_info, ("exception_traceback", "traceback"))
    return TrialError(
        type=error_type or UNKNOWN_ERROR_TYPE,
        message=_first_string(exception_info, ("exception_message", "message")),
        traceback=traceback[:_MAX_TRACEBACK_CHARS] if traceback is not None else None,
        occurred_at=_error_timestamp(exception_info.get("occurred_at")),
    )


def _first_string(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    """Find the first string value among candidate mapping keys.

    Args:
        payload: Mapping to inspect.
        keys: Candidate keys in lookup order.

    Returns:
        The first string value found, including an empty string, or ``None`` when
        no candidate contains a string.
    """
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def _error_timestamp(value: Any) -> datetime | None:
    """Parse an error timestamp without inventing a timezone.

    Args:
        value: Harbor timestamp value, typically a ``datetime`` or ISO-formatted
            string.

    Returns:
        The supplied ``datetime`` or a parsed ISO timestamp. Returns ``None`` for
        unsupported or invalid values and preserves whether the timestamp is
        timezone-aware or naive.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            return datetime.fromisoformat(value)
    return None


def _token_measurements(agent_result: Any) -> dict[str, int | float]:
    """Extract valid token counts and cost from one Harbor agent result.

    Args:
        agent_result: Harbor agent-result payload to inspect.

    Returns:
        SDK measurement keys for integer token counts and finite numeric cost.
        Missing, malformed, boolean, and non-finite values are omitted.
    """
    if not isinstance(agent_result, Mapping):
        return {}
    mapping = {
        "prompt_tokens": "n_input_tokens",
        "completion_tokens": "n_output_tokens",
        "cache_read_tokens": "n_cache_tokens",
    }
    out: dict[str, int | float] = {}
    for sdk_key, harbor_key in mapping.items():
        value = agent_result.get(harbor_key)
        if isinstance(value, int) and not isinstance(value, bool):
            out[sdk_key] = value
    cost = agent_result.get("cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        try:
            numeric_cost = float(cost)
        except (OverflowError, TypeError, ValueError):
            numeric_cost = None
        if numeric_cost is not None and math.isfinite(numeric_cost):
            out["cost_usd"] = numeric_cost
    return out


def _trial_measurements(data: Mapping[str, Any]) -> dict[str, int | float]:
    """Extract Harbor token and cost metadata from one result source.

    A top-level ``agent_result`` takes precedence. When it is absent, valid
    measurements from step-level agent results are aggregated exactly once.

    Args:
        data: Parsed Harbor ``result.json`` payload.

    Returns:
        SDK measurement keys for token counts and finite cost. Returns an empty
        mapping when neither result source contains valid measurements.
    """
    top_level = data.get("agent_result")
    if isinstance(top_level, Mapping):
        return _token_measurements(top_level)

    step_results = data.get("step_results")
    if not isinstance(step_results, list):
        return {}

    totals: dict[str, int | float] = {}
    costs: list[float] = []
    for step in step_results:
        if not isinstance(step, Mapping):
            continue
        for key, value in _token_measurements(step.get("agent_result")).items():
            if key == "cost_usd":
                costs.append(float(value))
            else:
                totals[key] = int(totals.get(key, 0)) + int(value)
    if costs:
        try:
            total_cost = math.fsum(costs)
        except OverflowError:
            total_cost = None
        if total_cost is not None and math.isfinite(total_cost):
            totals["cost_usd"] = total_cost
    return totals
