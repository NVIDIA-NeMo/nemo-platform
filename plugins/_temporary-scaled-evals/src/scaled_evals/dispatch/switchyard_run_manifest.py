# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Switchyard benchmark-compatible run manifest artifacts.

The Switchyard benchmark launcher writes ``run_manifest.json`` before Harbor
starts and finalizes it after Harbor exits. Scaled-evals owns a different
launch lifecycle, but closed/open-book runs should still leave the same
shareable provenance artifact next to the Switchyard logs and routing profile.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import socket
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scaled_evals.api.redaction import redact_secret_text
from scaled_evals.dispatch.switchyard import SWITCHYARD_ARTIFACT_DIR

RUN_MANIFEST_FILE_NAME = "run_manifest.json"
HARBOR_RESULT_FILE_NAME = "harbor_result.json"
ROUTING_STATS_FILE_NAME = "routing_stats_final.json"
SCHEMA_VERSION = 1

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|auth[_-]?token|token|secret|password|credential|credentials|byok)",
    re.I,
)


def write_switchyard_run_manifest(
    artifact_root: Path | str,
    row: Mapping[str, Any],
    *,
    status: str,
    backend: str | None = None,
    handle: str | None = None,
    harbor_rc: int | None = None,
) -> Path | None:
    """Write or finalize ``switchyard/run_manifest.json`` for one evaluation.

    Returns ``None`` when the evaluation has no Switchyard lease/profile.
    """

    raw_switchyard = _switchyard_raw(row)
    if raw_switchyard is None and not row.get("switchyard_profile_id"):
        return None

    root = Path(artifact_root)
    switchyard_root = root / SWITCHYARD_ARTIFACT_DIR
    switchyard_root.mkdir(parents=True, exist_ok=True)
    path = switchyard_root / RUN_MANIFEST_FILE_NAME
    result_path = _copy_harbor_result(root, switchyard_root)
    routing_stats_path = switchyard_root / ROUTING_STATS_FILE_NAME
    terminal_rc = _terminal_rc(status, harbor_rc)

    manifest = {
        "run": _run_meta(row),
        "server": _server_meta(root, switchyard_root, row, raw_switchyard),
        "harbor": _harbor_meta(root, row),
        "harbor_patch": _redacted_value(row.get("harbor_patch") or {}),
        "closed_book": _closed_book_meta(root, row, raw_switchyard),
        "versions": _versions_meta(switchyard_root, row),
        "provenance": _provenance_meta(root, switchyard_root, row, raw_switchyard),
        "determinism": {
            "PYTHONHASHSEED": "0",
            "LC_ALL": "C.UTF-8",
        },
        "outcomes": {
            "run_dir": str(root.resolve()),
            "log_path": _path_text(root / "job.log"),
            "harbor_result_json": _path_text(result_path),
            "harbor_result_json_status": "present" if result_path.is_file() else "missing",
            "routing_stats_json": _path_text(routing_stats_path),
            "routing_stats_json_status": _routing_stats_status(routing_stats_path, raw_switchyard),
            "harbor_rc": terminal_rc,
            "scaled_evals_status": status,
            "scaled_evals_backend": backend,
            "scaled_evals_handle": handle,
            "summary": _result_summary(result_path),
        },
    }
    if terminal_rc is not None:
        manifest["outcomes"]["completed_at"] = _iso_timestamp()

    path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _run_meta(row: Mapping[str, Any]) -> dict[str, Any]:
    repo = _repo_root(Path(__file__).resolve())
    dirty = _env_bool(_first_env("SCALED_EVALS_GIT_DIRTY", "CI_GIT_DIRTY"))
    if dirty is None:
        dirty = _git_dirty(repo)
    git_tree_kind = _tree_kind(dirty)
    if git_tree_kind == "not-git" and (tree_kind := _first_env("SCALED_EVALS_GIT_TREE_KIND")):
        git_tree_kind = tree_kind
    artifact = _runner_artifact(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": _iso_timestamp(),
        "hostname": socket.gethostname(),
        "git_branch": _first_env("SCALED_EVALS_GIT_BRANCH", "CI_COMMIT_BRANCH", "GIT_BRANCH")
        or _git_value(["branch", "--show-current"], cwd=repo),
        "git_sha": (
            _first_env("SCALED_EVALS_GIT_SHA", "CI_COMMIT_SHA", "GIT_COMMIT", "GIT_SHA")
            or _clean_optional(artifact.get("source_revision"))
            or _git_value(["rev-parse", "HEAD"], cwd=repo)
        ),
        "git_dirty": dirty,
        "git_tree_kind": git_tree_kind,
        "harbor_command": ["scaled-evals-dispatch-worker"],
        "harbor_version": row.get("framework_version"),
        "scaled_evals_version": _package_version("scaled-evals"),
        "control_plane_image": _clean_optional(
            row.get("runner_image_ref") or artifact.get("image_ref") or os.environ.get("API_IMAGE")
        ),
        "control_plane_image_digest": _clean_optional(
            row.get("runner_image_digest") or artifact.get("image_digest") or os.environ.get("API_IMAGE_DIGEST")
        ),
        "ci_pipeline_id": _clean_optional(artifact.get("ci_pipeline_id") or os.environ.get("CI_PIPELINE_ID")),
        "ci_job_id": _clean_optional(artifact.get("ci_job_id") or os.environ.get("CI_JOB_ID")),
        "launcher_argv": ["scaled-evals", "evaluation", "run", str(row.get("id"))],
    }


def _server_meta(
    artifact_root: Path,
    switchyard_root: Path,
    row: Mapping[str, Any],
    raw_switchyard: Mapping[str, Any] | None,
) -> dict[str, Any]:
    mode = str((raw_switchyard or {}).get("mode") or "managed")
    render = _read_json(switchyard_root / "k8s-manifest.redacted.json")
    container = _switchyard_container(render)
    server_config = {
        "scaled_evals": {
            "evaluation_id": str(row.get("id")),
            "execution_id": _clean_optional(row.get("execution_id")),
            "execution_number": _clean_int(row.get("execution_number") or row.get("current_execution")),
            "switchyard_topology": _clean_optional(row.get("switchyard_topology")),
            "switchyard_profile_id": _clean_optional(row.get("switchyard_profile_id")),
            "intake_profile_id": _clean_optional(row.get("intake_profile_id")),
            "runtime": _clean_optional(row.get("runtime")),
            "network_policy": _clean_optional(row.get("network_policy")),
            "network_policy_config": _redacted_value(row.get("network_policy_config") or {}),
            "manifest_hash": _clean_optional((raw_switchyard or {}).get("manifest_hash")),
            "config_hash": _clean_optional((raw_switchyard or {}).get("config_hash")),
            "artifact_path": f"{SWITCHYARD_ARTIFACT_DIR}/",
        },
        "switchyard_profile": _redacted_value(row.get("switchyard_config") or {}),
    }
    if container:
        server_config["container"] = {
            "image": container.get("image"),
            "image_pull_policy": container.get("imagePullPolicy"),
            "resources": _redacted_value(container.get("resources") or {}),
        }
    switchyard_image = _switchyard_image_meta(switchyard_root, container)
    if switchyard_image:
        server_config["switchyard_image"] = switchyard_image
    return {
        "preset": f"scaled-evals-{mode}-switchyard",
        "mode": mode,
        "url": _clean_optional((raw_switchyard or {}).get("endpoint")),
        "port": _clean_int((raw_switchyard or {}).get("port")),
        "argv": _server_argv(container),
        "config": server_config,
        "classifier_prompts": {},
        "harbor_server_url": _clean_optional((raw_switchyard or {}).get("endpoint")),
        "harbor_base_url": _clean_optional((raw_switchyard or {}).get("openai_base_url")),
        "upstream_base_url": None,
        "upstream_api_key_env": None,
        "routing_profiles": _path_text(switchyard_root / "routes.yaml"),
        "routing_profiles_digest": path_digest(switchyard_root / "routes.yaml"),
        "routing_profiles_snapshot": _path_text(switchyard_root / "routes.yaml"),
        "routing_profiles_snapshot_digest": path_digest(switchyard_root / "routes.yaml"),
        "route_model": _harbor_model(row, raw_switchyard),
        "log_path": _path_text(switchyard_root / "switchyard.log"),
        "previous_log_path": _path_text(switchyard_root / "switchyard.previous.log"),
        "events_path": _path_text(switchyard_root / "events.json"),
        "status_path": _path_text(switchyard_root / "status.json"),
        "lease_path": _path_text(switchyard_root / "lease.json"),
        "artifact_root": str(artifact_root.resolve()),
    }


def _harbor_meta(artifact_root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    harbor_config = _mapping(row.get("harbor_config"))
    task_selector = {
        "task_id": row.get("task_id"),
        "task_revision": row.get("task_revision"),
        "task_slug": row.get("task_slug"),
        "tarball_object_key": row.get("tarball_object_key"),
    }
    return {
        "dataset": _clean_optional(row.get("task_slug") or row.get("task_id")),
        "path": None,
        "path_digest": None,
        "dataset_fingerprint": _value_hash(task_selector),
        "agent": _agent_name(row),
        "model": _harbor_model(row, _switchyard_raw(row)),
        "reasoning_effort": _clean_optional(harbor_config.get("reasoning_effort") or harbor_config.get("reasoning")),
        "n_concurrent": _clean_int(row.get("parallelism")),
        "max_retries": _clean_int(harbor_config.get("max_retries")),
        "agent_timeout_multiplier": _clean_optional(harbor_config.get("agent_timeout_multiplier")),
        "n_tasks": 1,
        "task_id": (
            f"{row.get('task_id')}:{row.get('task_revision')}"
            if row.get("task_id") and row.get("task_revision") is not None
            else _clean_optional(row.get("task_id"))
        ),
        "task_list_file": None,
        "task_list_digest": None,
        "codex_model_catalog": None,
        "codex_model_catalog_digest": None,
        "extra_args": _redacted_value(harbor_config.get("extra_args") or []),
        "config": _redacted_value(harbor_config),
        "task_image_ref": _clean_optional(row.get("image_ref")),
        "task_image_digest": _clean_optional(row.get("image_digest")),
        "task_slug": _clean_optional(row.get("task_slug")),
        "tarball_sha256": _clean_optional(row.get("tarball_sha256")),
        "tarball_object_key": _clean_optional(row.get("tarball_object_key")),
        "scaled_evals_result_json": _path_text(artifact_root / "result.json"),
    }


def _versions_meta(switchyard_root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    runner_metadata = _mapping(row.get("runner_metadata"))
    qualification = _mapping(runner_metadata.get("qualification"))
    switchyard_image = _switchyard_image_meta(
        switchyard_root,
        _switchyard_container(_read_json(switchyard_root / "k8s-manifest.redacted.json")),
    )
    return _redacted_value(
        {
            "scaled_evals": {
                "package_version": _package_version("scaled-evals"),
                "git_sha": _first_env(
                    "SCALED_EVALS_GIT_SHA",
                    "CI_COMMIT_SHA",
                    "GIT_COMMIT",
                    "GIT_SHA",
                )
                or _clean_optional(_runner_artifact(row).get("source_revision")),
                "image_ref": _clean_optional(row.get("runner_image_ref"))
                or _clean_optional(_runner_artifact(row).get("image_ref")),
                "image_digest": _clean_optional(row.get("runner_image_digest"))
                or _clean_optional(_runner_artifact(row).get("image_digest")),
            },
            "harbor": {
                "version": row.get("framework_version"),
                "release": qualification.get("release"),
            },
            "adapter": {
                "version": row.get("framework_adapter_version"),
                "metadata": qualification.get("adapter"),
            },
            "sandbox_k8s": {
                "version": row.get("sandbox_k8s_version"),
                "metadata": qualification.get("sandbox_k8s"),
            },
            "agent_bundle": _agent_bundle(row) or None,
            "switchyard": switchyard_image or None,
            "runner_artifact": _runner_artifact(row) or None,
            "validation": qualification.get("validation"),
        }
    )


def _provenance_meta(
    artifact_root: Path,
    switchyard_root: Path,
    row: Mapping[str, Any],
    raw_switchyard: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "scaled-evals-switchyard-run-manifest-v1",
        "evaluation": {
            "id": row.get("id"),
            "name": row.get("name"),
            "framework": row.get("framework"),
            "runtime": row.get("runtime"),
            "network_policy": row.get("network_policy"),
            "network_policy_config": row.get("network_policy_config") or {},
            "parallelism": row.get("parallelism"),
            "n_attempts": row.get("n_attempts"),
            "benchmark_run_id": row.get("benchmark_run_id"),
        },
        "task": {
            "id": row.get("task_id"),
            "revision": row.get("task_revision"),
            "slug": row.get("task_slug"),
            "image_ref": row.get("image_ref"),
            "image_digest": row.get("image_digest"),
            "tarball_sha256": row.get("tarball_sha256"),
            "tarball_object_key": row.get("tarball_object_key"),
            "extra_skill_object_keys": row.get("extra_skill_object_keys") or [],
        },
        "profiles": {
            "framework_profile_id": row.get("framework_profile_id"),
            "harbor_profile_id": row.get("harbor_profile_id"),
            "switchyard_profile_id": row.get("switchyard_profile_id"),
            "intake_profile_id": row.get("intake_profile_id"),
            "harbor_config_hash": _value_hash(row.get("harbor_config") or {}),
            "switchyard_config_hash": _value_hash(row.get("switchyard_config") or {}),
            "intake_config_hash": _value_hash(row.get("intake_config") or {}),
        },
        "credentials": [],
        "runner_metadata": row.get("runner_metadata") or {},
        "switchyard": raw_switchyard or {},
        "artifacts": {
            "root": str(artifact_root.resolve()),
            "switchyard_dir": str(switchyard_root.resolve()),
            "routes": _path_text(switchyard_root / "routes.yaml"),
            "k8s_manifest": _path_text(switchyard_root / "k8s-manifest.redacted.json"),
            "lease": _path_text(switchyard_root / "lease.json"),
            "status": _path_text(switchyard_root / "status.json"),
            "log": _path_text(switchyard_root / "switchyard.log"),
            "previous_log": _path_text(switchyard_root / "switchyard.previous.log"),
            "events": _path_text(switchyard_root / "events.json"),
            "scaled_evals_provenance": _path_text(artifact_root / "scaled-evals-provenance.json"),
        },
    }
    redacted = _redacted_value(payload)
    if isinstance(redacted, dict):
        redacted["credentials"] = _credential_refs(row.get("credentials") or {})
        return redacted
    return {"credentials": _credential_refs(row.get("credentials") or {})}


def _closed_book_meta(
    artifact_root: Path,
    row: Mapping[str, Any],
    raw_switchyard: Mapping[str, Any] | None,
) -> dict[str, Any]:
    book_mode = _book_mode(row, raw_switchyard)
    strip_log = artifact_root / SWITCHYARD_ARTIFACT_DIR / "proxy_strip_log.jsonl"
    rendered_manifest = artifact_root / SWITCHYARD_ARTIFACT_DIR / "k8s-manifest.redacted.json"
    return {
        "mode": book_mode,
        "declarations": {
            "book_mode": book_mode,
            "gateway_configured": raw_switchyard is not None,
            "hosted_tools_policy": "profile-defined",
        },
        "evidence": {
            "rendered_manifest": _path_text(rendered_manifest),
            "rendered_manifest_status": ("present" if rendered_manifest.is_file() else "missing"),
            # Rendered resources establish desired configuration, not effective
            # CNI isolation or process-level hosted-tool behavior.
            "effective_gateway_enforcement": "unknown",
            "effective_hosted_tools_disabled": "unknown",
            "effective_verifier_egress": "unknown",
        },
        "proxy_strip_artifact": None,
        "proxy_strip_log": _path_text(strip_log),
        "proxy_strip_log_status": "present" if strip_log.is_file() else "not-requested",
        "agent_versions": _agent_versions(row),
        "dataset_manifest_snapshot": None,
        "dataset_manifest_snapshot_digest": None,
    }


def _copy_harbor_result(artifact_root: Path, switchyard_root: Path) -> Path:
    dest = switchyard_root / HARBOR_RESULT_FILE_NAME
    source = _find_result_json(artifact_root)
    if source is None:
        return dest
    try:
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
    except OSError:
        return dest
    return dest


def _find_result_json(artifact_root: Path) -> Path | None:
    direct = artifact_root / "result.json"
    if direct.is_file():
        return direct
    candidates = sorted(
        (path for path in artifact_root.rglob("result.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def _result_summary(result_path: Path) -> dict[str, Any] | None:
    result = _read_json(result_path)
    if not result:
        return None
    stats = _mapping(result.get("stats"))
    evals = _mapping(stats.get("evals"))
    rewards: dict[str, list[str]] = {}
    for eval_result in evals.values():
        if not isinstance(eval_result, Mapping):
            continue
        reward_stats = _mapping(eval_result.get("reward_stats"))
        reward_values = _mapping(reward_stats.get("reward"))
        for reward, trials in reward_values.items():
            if isinstance(trials, list):
                rewards[str(reward)] = [str(trial) for trial in trials]
    return {
        "result_id": result.get("id"),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "n_total_trials": result.get("n_total_trials"),
        "n_completed_trials": stats.get("n_completed_trials"),
        "n_errored_trials": stats.get("n_errored_trials"),
        "n_failed_solve": stats.get("n_failed_solve"),
        "n_input_tokens": stats.get("n_input_tokens"),
        "n_cache_tokens": stats.get("n_cache_tokens"),
        "n_output_tokens": stats.get("n_output_tokens"),
        "cost_usd": stats.get("cost_usd"),
        "rewards": rewards,
        "evals": sorted(str(name) for name in evals),
    }


def _routing_stats_status(path: Path, raw_switchyard: Mapping[str, Any] | None) -> str:
    if path.is_file():
        return "present"
    if raw_switchyard is not None:
        return "missing"
    return "not-requested"


def _terminal_rc(status: str, harbor_rc: int | None) -> int | None:
    if harbor_rc is not None:
        return harbor_rc
    if status == "succeeded":
        return 0
    if status in {"failed", "cancelled", "blocked"}:
        return 1
    return None


def _switchyard_image_meta(
    switchyard_root: Path,
    container: Mapping[str, Any],
) -> dict[str, Any]:
    image = _clean_optional(container.get("image"))
    status = _read_json(switchyard_root / "status.json")
    image_id = None
    for item in _status_items(status):
        statuses = _mapping(item.get("status")).get("containerStatuses")
        if not isinstance(statuses, list):
            continue
        for container_status in statuses:
            if not isinstance(container_status, Mapping):
                continue
            if container_status.get("name") != "switchyard":
                continue
            image = image or _clean_optional(container_status.get("image"))
            image_id = _clean_optional(container_status.get("imageID"))
            break
        if image_id:
            break
    meta = {
        "image": image,
        "image_id": image_id,
        "image_pull_policy": _clean_optional(container.get("imagePullPolicy")),
    }
    return {key: value for key, value in meta.items() if value is not None}


def _status_items(status: Mapping[str, Any]) -> list[dict[str, Any]]:
    for section in ("pods", "resources"):
        data = _mapping(_mapping(status.get(section)).get("data"))
        items = data.get("items")
        if isinstance(items, list):
            return [dict(item) for item in items if isinstance(item, Mapping)]
    return []


def _server_argv(container: Mapping[str, Any]) -> list[str]:
    command = container.get("command")
    args = container.get("args")
    values: list[str] = []
    if isinstance(command, list):
        values.extend(str(item) for item in command)
    if isinstance(args, list):
        values.extend(str(item) for item in args)
    return values


def _switchyard_container(render: Mapping[str, Any]) -> dict[str, Any]:
    for item in render.get("items", []) if isinstance(render.get("items"), list) else []:
        if not isinstance(item, Mapping) or item.get("kind") != "Deployment":
            continue
        containers = _mapping(item.get("spec")).get("template", {}).get("spec", {}).get("containers", [])
        if isinstance(containers, list) and containers:
            first = containers[0]
            return dict(first) if isinstance(first, Mapping) else {}
    return {}


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str] | None:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode, result.stdout.strip()


def _repo_root(path: Path) -> Path:
    cwd = path if path.is_dir() else path.parent
    result = _run(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if result is None or result[0] != 0 or not result[1]:
        return cwd
    return Path(result[1])


def _git_value(args: list[str], cwd: Path) -> str | None:
    result = _run(["git", *args], cwd=cwd)
    if result is None or result[0] != 0:
        return None
    return result[1] or None


def _git_dirty(cwd: Path) -> bool | None:
    result = _run(["git", "status", "--porcelain"], cwd=cwd)
    if result is None or result[0] != 0:
        return None
    return bool(result[1])


def _tree_kind(dirty: bool | None) -> str:
    if dirty is None:
        return "not-git"
    return "git-dirty" if dirty else "git-clean"


def _env_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _first_env(*keys: str) -> str | None:
    for key in keys:
        if value := os.environ.get(key):
            return value
    return None


def _package_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def path_digest(path: Path) -> str:
    """Return a deterministic sha256 digest for a file or directory."""

    try:
        resolved = path.resolve()
        hasher = hashlib.sha256()
        if resolved.is_file():
            hasher.update(resolved.name.encode())
            with resolved.open("rb") as handle:
                hasher.update(hashlib.file_digest(handle, "sha256").digest())
            return f"sha256:{hasher.hexdigest()}"
        if resolved.is_dir():
            for item in sorted(path for path in resolved.rglob("*") if path.is_file()):
                rel = item.relative_to(resolved).as_posix()
                with item.open("rb") as handle:
                    file_hash = hashlib.file_digest(handle, "sha256").hexdigest()
                hasher.update(f"{rel}\n{file_hash}\n".encode())
            return f"sha256:{hasher.hexdigest()}"
    except OSError:
        return "sha256:unknown"
    return "sha256:missing"


def _switchyard_raw(row: Mapping[str, Any]) -> dict[str, Any] | None:
    resource = _mapping(row.get("switchyard_resource"))
    for value in (
        row.get("switchyard"),
        row.get("switchyard_lease"),
        resource.get("metadata"),
    ):
        if value is None:
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                continue
        if isinstance(value, Mapping):
            return dict(value)
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json", exclude_none=True)
            return dict(dumped) if isinstance(dumped, Mapping) else None
    return None


def _book_mode(row: Mapping[str, Any], raw_switchyard: Mapping[str, Any] | None) -> str:
    raw_value = (raw_switchyard or {}).get("book_mode")
    config_value = _mapping(row.get("switchyard_config")).get("book_mode")
    value = raw_value or config_value
    return str(value) if value in {"closed", "open"} else "profile-defined"


def _agent_name(row: Mapping[str, Any]) -> str | None:
    harbor_config = _mapping(row.get("harbor_config"))
    if harbor_config.get("agent"):
        return str(harbor_config["agent"])
    bundle = _agent_bundle(row)
    for key in ("agent_name", "bundle_name", "name", "agent"):
        if bundle.get(key):
            return str(bundle[key])
    return None


def _agent_versions(row: Mapping[str, Any]) -> dict[str, Any]:
    bundle = _agent_bundle(row)
    versions = {
        "framework_version": row.get("framework_version"),
        "framework_adapter_version": row.get("framework_adapter_version"),
        "sandbox_k8s_version": row.get("sandbox_k8s_version"),
    }
    for key in (
        "bundle_id",
        "bundle_name",
        "agent_name",
        "agent_version",
        "fingerprint",
        "image_ref",
        "image_digest",
        "source_lock_digest",
    ):
        if bundle.get(key):
            versions[key] = bundle[key]
    return _redacted_value({key: value for key, value in versions.items() if value})


def _agent_bundle(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _mapping(row.get("runner_metadata"))
    bundle = metadata.get("agent_bundle")
    return dict(bundle) if isinstance(bundle, Mapping) else {}


def _runner_artifact(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _mapping(row.get("runner_metadata"))
    artifact = metadata.get("artifact")
    return dict(artifact) if isinstance(artifact, Mapping) else {}


def _credential_refs(credentials: Mapping[str, Any]) -> list[dict[str, str]]:
    refs = []
    for role, credential_id in sorted(credentials.items()):
        credential_id_text = str(credential_id)
        refs.append(
            {
                "role": str(role),
                "credential_id": credential_id_text,
                "fingerprint": _short_fingerprint(credential_id_text),
            }
        )
    return refs


def _short_fingerprint(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def _harbor_model(row: Mapping[str, Any], raw_switchyard: Mapping[str, Any] | None) -> str | None:
    harbor_config = _mapping(row.get("harbor_config"))
    for key in ("model", "harbor_model", "route_model"):
        if harbor_config.get(key):
            return str(harbor_config[key])
    routes = _mapping(row.get("switchyard_config")).get("routing_profiles")
    if isinstance(routes, Mapping):
        routes_obj = routes.get("routes")
        if isinstance(routes_obj, Mapping) and routes_obj:
            return next(iter(routes_obj))
    if raw_switchyard is not None:
        return "switchyard"
    return None


def _value_hash(value: Any) -> str:
    encoded = json.dumps(_redacted_value(value), sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _redacted_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                redacted[key_text] = "<redacted>"
            else:
                redacted[key_text] = _redacted_value(item)
        return redacted
    if isinstance(value, list):
        return [_redacted_value(item) for item in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _clean_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _path_text(path: Path) -> str:
    return str(path.resolve())


def _iso_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
