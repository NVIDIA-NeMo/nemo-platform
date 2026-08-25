# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Immutable and runtime-observed identity for Gym-backed evaluations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from scaled_evals.api.redaction import redact_secret_text
from scaled_evals.models.execution_snapshot import (
    canonical_sha256,
    snapshot_profile_config,
    validate_execution_snapshot,
)
from scaled_evals.models.gym_profile import GymProfileConfig

GYM_RUNTIME_LANES = {
    "gym_daytona": {"provider": "daytona", "agent_path": "harbor_agent"},
    "gym_sandbox_daytona": {"provider": "daytona", "agent_path": "mini_swe_agent_2"},
    "gym_sandbox_opensandbox": {
        "provider": "opensandbox",
        "agent_path": "mini_swe_agent_2",
    },
}
_GYM_COMMANDS = {"run_and_collect", "ng_e2e_collect_rollouts", "ng_collect_rollouts"}


def snapshot_evaluation(row: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return immutable evaluation inputs, or the row for an explicit legacy run."""
    snapshot = validate_execution_snapshot(row.get("execution_snapshot"))
    if snapshot is None:
        return row
    evaluation = snapshot.get("evaluation")
    if not isinstance(evaluation, Mapping):  # validate_execution_snapshot already guards this
        raise ValueError("execution snapshot evaluation must be an object")
    return evaluation


def is_snapshot_backed(row: Mapping[str, Any]) -> bool:
    return validate_execution_snapshot(row.get("execution_snapshot")) is not None


def gym_run_identity(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return declared Gym identity plus backend observations without reading live env."""
    evaluation = snapshot_evaluation(row)
    runtime = str(evaluation.get("runtime") or row.get("runtime") or "")
    lane = GYM_RUNTIME_LANES.get(runtime)
    if lane is None:
        return None

    metadata = _mapping(evaluation.get("runner_metadata"))
    gym = _mapping(metadata.get("gym"))
    artifact = _mapping(metadata.get("artifact"))
    external_sbom = _mapping(gym.get("external_sbom") or artifact.get("external_sbom"))
    handle = backend_handle_raw(row.get("backend_handle"))
    framework_config = _mapping(row.get("framework_config"))
    snapshot = validate_execution_snapshot(row.get("execution_snapshot"))
    if snapshot is not None:
        framework_config = snapshot_profile_config(snapshot, "framework")
    agent_path = lane["agent_path"]
    if snapshot is not None and framework_config:
        try:
            validated_profile = GymProfileConfig.model_validate(framework_config)
        except ValueError:
            pass
        else:
            agent_path = _clean_public(validated_profile.agent_name) or agent_path

    expected_digest = _clean(evaluation.get("runner_image_digest") or artifact.get("image_digest"))
    expected_source = _clean(artifact.get("source_revision") or gym.get("source_revision"))
    expected_version = _clean(artifact.get("package_version") or gym.get("package_version"))
    observed_digest = _clean(handle.get("observed_runner_image_digest"))
    observed_source = _clean(handle.get("observed_gym_source_revision"))
    observed_version = _clean(handle.get("observed_gym_package_version"))
    completeness = str(
        gym.get("identity_completeness")
        or ("complete" if evaluation.get("runner_image_ref") and expected_digest and expected_source else "incomplete")
    )
    verification = _verification(
        expected_digest=expected_digest,
        observed_digest=observed_digest,
        expected_source=expected_source,
        observed_source=observed_source,
    )
    return {
        "runtime": runtime,
        **lane,
        "agent_path": agent_path,
        "framework": _clean(evaluation.get("framework") or row.get("framework")),
        "profile_id": _clean(evaluation.get("framework_profile_id") or row.get("framework_profile_id")),
        "package_version": expected_version,
        "source_revision": expected_source,
        "runner_image_ref": _clean(evaluation.get("runner_image_ref") or artifact.get("image_ref")),
        "runner_image_digest": expected_digest,
        "observed_runner_image_digest": observed_digest,
        "observed_runner_image_id": _clean(handle.get("observed_runner_image_id")),
        "observed_source_revision": observed_source,
        "observed_package_version": observed_version,
        "identity_completeness": completeness,
        "identity_verification": verification,
        "external_sbom": external_sbom,
        "profile": _profile_provenance(row, snapshot, framework_config, handle),
        "executor": _executor_provenance(row, handle),
        "runtime_settings": _runtime_settings(handle),
    }


def _profile_provenance(
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
    raw_config: Mapping[str, Any],
    handle: Mapping[str, Any],
) -> dict[str, Any]:
    source = "snapshot" if snapshot is not None else "live-legacy"
    if not raw_config:
        return {"source": "absent", "projection": "absent"}

    result: dict[str, Any] = {
        "source": source,
        "projection": "legacy-unparsed",
        "config_sha256": canonical_sha256(raw_config),
    }
    if snapshot is None:
        return result
    try:
        profile = GymProfileConfig.model_validate(raw_config)
    except ValueError:
        return result

    raw_observed_command = _clean(handle.get("command"))
    observed_command = raw_observed_command if raw_observed_command in _GYM_COMMANDS else "unexpected"
    if raw_observed_command is None:
        observed_command = None
    command_verification = (
        "unobserved" if observed_command is None else "matched" if observed_command == profile.command else "mismatch"
    )
    effective_command = observed_command or profile.command
    effective_limit = profile.limit
    effective_samples = profile.num_samples_in_parallel
    if effective_command == "run_and_collect":
        effective_limit = profile.limit or 1
        effective_samples = profile.num_samples_in_parallel or 1
    runtime_settings = _runtime_settings(handle)
    effective_samples = _clean_int(runtime_settings.get("parallelism")) or effective_samples
    control_plane_attempts = _clean_int(runtime_settings.get("n_attempts")) or _clean_int(row.get("n_attempts"))
    return {
        **result,
        "projection": "validated-v1",
        "schema_version": profile.schema_version,
        "requested_command": profile.command,
        "observed_command": observed_command,
        "command_verification": command_verification,
        "config_paths": [redact_secret_text(path) for path in profile.config_paths],
        "requested_input_jsonl_fpath": _clean_public(profile.input_jsonl_fpath),
        "requested_split": _clean_public(profile.split),
        "requested_limit": profile.limit,
        "effective_limit": effective_limit,
        "requested_num_repeats": profile.num_repeats,
        "requested_num_samples_in_parallel": profile.num_samples_in_parallel,
        "effective_num_samples_in_parallel": effective_samples,
        "control_plane_parallelism": _clean_int(runtime_settings.get("parallelism"))
        or _clean_int(row.get("parallelism")),
        "control_plane_attempts": control_plane_attempts,
    }


def _executor_provenance(row: Mapping[str, Any], handle: Mapping[str, Any]) -> dict[str, Any]:
    mode = "process" if handle.get("process") is True else "docker" if handle.get("docker") is True else "unknown"
    pod_name = _clean(handle.get("process_owner_pod"))
    return {
        "mode": mode,
        "dispatch_job_name": _clean(row.get("dispatch_job_name")),
        "dispatch_job_uid": _clean(row.get("dispatch_job_uid")),
        "runner_pod_name": pod_name,
        "runner_pod_name_source": "backend-handle" if pod_name else None,
    }


def _runtime_settings(handle: Mapping[str, Any]) -> dict[str, Any]:
    raw_settings = _mapping(handle.get("effective_runtime_settings"))
    settings: dict[str, Any] = {}
    for key, value in raw_settings.items():
        if value in (None, {}, []):
            continue
        if isinstance(value, str):
            settings[key] = redact_secret_text(value)
        elif isinstance(value, list):
            settings[key] = [redact_secret_text(item) if isinstance(item, str) else item for item in value]
        elif isinstance(value, Mapping):
            settings[key] = {
                str(inner_key): redact_secret_text(inner_value) if isinstance(inner_value, str) else inner_value
                for inner_key, inner_value in value.items()
            }
        else:
            settings[key] = value
    return settings


def _verification(
    *,
    expected_digest: str | None,
    observed_digest: str | None,
    expected_source: str | None,
    observed_source: str | None,
) -> str:
    if observed_digest and expected_digest and observed_digest != expected_digest:
        return "mismatch"
    if observed_source and expected_source and observed_source != expected_source:
        return "mismatch"
    digest_verified = bool(observed_digest and expected_digest == observed_digest)
    source_verified = not expected_source or observed_source == expected_source
    return "runtime-observed" if digest_verified and source_verified else "declared-unverified"


def backend_handle_raw(value: Any) -> Mapping[str, Any]:
    """Return the backend-reported launch details recorded on an evaluation row."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, Mapping):
        return {}
    return _mapping(value.get("raw"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_public(value: Any) -> str | None:
    cleaned = _clean(value)
    return None if cleaned is None else redact_secret_text(cleaned)


def _clean_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
