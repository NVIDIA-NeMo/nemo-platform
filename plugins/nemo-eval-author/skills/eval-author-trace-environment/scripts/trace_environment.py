# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare private, text-only ATIF evidence for one generated evaluation environment."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "nemo.eval_author.trace_environment_summary.v1"
CANDIDATE_SCHEMA = "nemo.eval_author.trace_environment_candidate.v1"
VALIDATION_SCHEMA = "nemo.eval_author.trace_environment_validation.v1"
MAX_SOURCE_BYTES = 25 * 1024 * 1024
TASK_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ATIF_VERSION = re.compile(r"ATIF-v1\.[0-7]")

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d(). -]{6,}\d)(?!\w)")
_HOME_PATH = re.compile(r"(?<![\w/])/(?:home|Users)/[^/\s]+")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_SECRET_KEY = re.compile(r"(?i)(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|authorization)")
_IDENTIFIER_KEYS = frozenset(
    {
        "parent_span_id",
        "session_id",
        "source_call_id",
        "span_id",
        "tool_call_id",
        "trace_id",
        "trajectory_id",
    }
)
_SUMMARY_KEYS = frozenset(
    {
        "schema",
        "task_id",
        "status",
        "source",
        "privacy",
        "candidate",
        "environment",
        "worked_well",
        "did_not_work",
        "reasons",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "schema",
        "status",
        "instruction",
        "requirements",
        "verification_mode",
        "evidence_steps",
        "uncertainties",
        "reason_codes",
        "ground_truth",
        "software_requirements",
    }
)
_GROUND_TRUTH_KEYS = frozenset({"availability", "artifacts", "absence_reason"})
_GROUND_TRUTH_ARTIFACT_KEYS = frozenset({"kind", "path", "sha256", "evidence_steps", "notes"})
_SOFTWARE_REQUIREMENT_KEYS = frozenset(
    {
        "name",
        "category",
        "required",
        "version",
        "license",
        "availability",
        "redistributable",
        "evidence_steps",
        "notes",
    }
)
_SOURCE_KEYS = frozenset({"kind", "private_path", "private_sha256", "safe_path", "safe_sha256"})
_PRIVACY_KEYS = frozenset(
    {
        "path",
        "deterministic_redactions",
        "images_omitted",
        "manual_review_required",
        "manual_review_complete",
        "blocking_reasons",
    }
)
_ENVIRONMENT_KEYS = frozenset({"path", "status", "validation"})
_TASK_README_SECTIONS = (
    "Difficulty explanation",
    "Environment and software requirements",
    "Ground-truth provenance",
    "Solution explanation",
    "Verification explanation",
    "Relevant experience",
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ContractError(ValueError):
    """A source or generated artifact violates the skill contract."""


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _chmod_private(path: Path, *, directory: bool = False) -> None:
    if os.name == "posix":
        path.chmod(0o700 if directory else 0o600)


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _chmod_private(path, directory=True)


def _write_bytes_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    _chmod_private(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        _chmod_private(temporary)
        os.replace(temporary, path)
        _chmod_private(path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json(path: Path, *, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"{label} must be a regular file: {path}")
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ContractError(f"{label} exceeds the {MAX_SOURCE_BYTES}-byte limit")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"could not read {label} as UTF-8 JSON: {error}") from error


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = _load_json(path, label=label)
    if not isinstance(payload, dict):
        raise ContractError(f"{label} must contain one JSON object")
    return payload


def _summary_path(task_dir: Path) -> Path:
    return task_dir / "summary.json"


def _load_summary(task_dir: Path) -> dict[str, Any]:
    summary = _load_object(_summary_path(task_dir), label="summary")
    if set(summary) != _SUMMARY_KEYS:
        raise ContractError("summary fields do not match the versioned contract")
    if summary.get("schema") != SCHEMA:
        raise ContractError(f"summary.schema must be {SCHEMA!r}")
    if summary.get("task_id") != task_dir.name:
        raise ContractError("summary task_id does not match its directory")
    if summary.get("status") not in {"pending", "candidate", "no_candidate"}:
        raise ContractError("summary status is not recognized")
    for name in ("worked_well", "did_not_work", "reasons"):
        value = summary.get(name)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ContractError(f"summary.{name} must be a list of strings")
    source = summary.get("source")
    if source is not None and (
        not isinstance(source, dict)
        or set(source) != _SOURCE_KEYS
        or source.get("kind") not in {"atif", "intake", "mlflow", "otel"}
        or source.get("private_path") != "private/source.atif.json"
        or source.get("safe_path") != "safe/trace.atif.json"
        or not isinstance(source.get("private_sha256"), str)
        or _DIGEST.fullmatch(source["private_sha256"]) is None
        or not isinstance(source.get("safe_sha256"), str)
        or _DIGEST.fullmatch(source["safe_sha256"]) is None
    ):
        raise ContractError("summary source does not match the versioned task workspace contract")
    privacy = summary.get("privacy")
    if privacy is not None and (
        not isinstance(privacy, dict)
        or set(privacy) != _PRIVACY_KEYS
        or privacy.get("path") != "safe/privacy.json"
        or not isinstance(privacy.get("deterministic_redactions"), dict)
        or not isinstance(privacy.get("images_omitted"), int)
        or privacy.get("manual_review_required") is not True
        or not isinstance(privacy.get("manual_review_complete"), bool)
        or not isinstance(privacy.get("blocking_reasons"), list)
    ):
        raise ContractError("summary privacy data does not match the versioned task workspace contract")
    environment = summary.get("environment")
    if (
        not isinstance(environment, dict)
        or set(environment) != _ENVIRONMENT_KEYS
        or environment.get("path") != "task"
        or environment.get("status") not in {"ready", "failed", "unproven", "not_attempted"}
        or environment.get("validation") not in {None, "validation.json"}
    ):
        raise ContractError("summary environment does not match the versioned task workspace contract")
    return summary


def _validate_task_id(value: str) -> str:
    if len(value) > 80 or TASK_ID.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("task id must be at most 80 lowercase kebab-case characters")
    return value


def _ensure_task_dir(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ContractError(f"task directory must be a regular directory: {path}")
    if TASK_ID.fullmatch(path.name) is None:
        raise ContractError("task directory name must be lowercase kebab-case")
    return path


def _init(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    if ".eval-author" not in root.parts:
        raise ContractError("task workspace root must stay under a .eval-author directory")
    _mkdir_private(root)
    ignore = root / ".gitignore"
    ignore_text = "*\n!.gitignore\n"
    if ignore.exists():
        if ignore.is_symlink() or ignore.read_text(encoding="utf-8") != ignore_text:
            raise ContractError(f"refusing to replace unexpected ignore rules at {ignore}")
    else:
        _write_text(ignore, ignore_text)

    task_dir = root / args.task_id
    if task_dir.exists():
        raise ContractError(f"task workspace already exists: {task_dir}")
    _mkdir_private(task_dir)
    _mkdir_private(task_dir / "private")
    _mkdir_private(task_dir / "safe")

    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "task_id": args.task_id,
        "status": "pending",
        "source": None,
        "privacy": None,
        "candidate": None,
        "environment": {"path": "task", "status": "not_attempted", "validation": None},
        "worked_well": [],
        "did_not_work": [],
        "reasons": [],
    }
    _write_json(_summary_path(task_dir), summary)
    return {"task_dir": str(task_dir), "status": "pending", "gitignored": True}


def _validate_message(message: Any, *, location: str) -> tuple[int, bool]:
    if isinstance(message, str):
        return 0, bool(message.strip())
    if not isinstance(message, list):
        raise ContractError(f"{location} must be text or a list of ATIF content parts")
    image_count = 0
    has_text = False
    for index, part in enumerate(message):
        if not isinstance(part, dict):
            raise ContractError(f"{location}[{index}] must be an object")
        part_type = part.get("type")
        text = part.get("text")
        if part_type == "text" and isinstance(text, str):
            has_text = has_text or bool(text.strip())
        elif part_type == "image" and isinstance(part.get("source"), dict):
            image_count += 1
        else:
            raise ContractError(f"{location}[{index}] is not a supported text or image content part")
    return image_count, has_text


def _validate_trajectory(payload: Any, *, location: str = "trajectory", depth: int = 0) -> dict[str, Any]:
    if depth > 8:
        raise ContractError("embedded ATIF trajectories exceed the depth limit of 8")
    if not isinstance(payload, dict):
        raise ContractError(f"{location} must be an object")
    version = payload.get("schema_version")
    if not isinstance(version, str) or ATIF_VERSION.fullmatch(version) is None:
        raise ContractError(f"{location}.schema_version must identify ATIF v1.x")
    agent = payload.get("agent")
    if not isinstance(agent, dict) or not isinstance(agent.get("name"), str) or not agent["name"].strip():
        raise ContractError(f"{location}.agent.name must be nonempty text")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ContractError(f"{location}.steps must be a nonempty list")

    image_count = 0
    image_only_user_steps: list[int] = []
    user_step_count = 0
    for index, step in enumerate(steps, start=1):
        step_location = f"{location}.steps[{index - 1}]"
        if not isinstance(step, dict):
            raise ContractError(f"{step_location} must be an object")
        if step.get("step_id") != index:
            raise ContractError(f"{step_location}.step_id must be sequential from 1")
        source = step.get("source")
        if source not in {"user", "agent", "system"}:
            raise ContractError(f"{step_location}.source must be user, agent, or system")
        if source == "user":
            user_step_count += 1
        step_images, has_text = _validate_message(step.get("message", ""), location=f"{step_location}.message")
        image_count += step_images
        if source == "user" and step_images and not has_text:
            image_only_user_steps.append(index)

        calls = step.get("tool_calls") or []
        if not isinstance(calls, list):
            raise ContractError(f"{step_location}.tool_calls must be a list")
        call_ids: set[str] = set()
        for call_index, call in enumerate(calls):
            if not isinstance(call, dict):
                raise ContractError(f"{step_location}.tool_calls[{call_index}] must be an object")
            call_id = call.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id or call_id in call_ids:
                raise ContractError(f"{step_location} has a missing or duplicate tool_call_id")
            call_ids.add(call_id)
        observation = step.get("observation")
        if observation is not None:
            if not isinstance(observation, dict):
                raise ContractError(f"{step_location}.observation.results must be a list")
            results = observation.get("results", [])
            if not isinstance(results, list):
                raise ContractError(f"{step_location}.observation.results must be a list")
            for result in results:
                if not isinstance(result, dict):
                    raise ContractError(f"{step_location}.observation results must be objects")
                source_call_id = result.get("source_call_id")
                if source_call_id is not None and source_call_id not in call_ids:
                    raise ContractError(f"{step_location} observation references unknown tool call {source_call_id!r}")
                result_images, _ = _validate_message(result.get("content", ""), location="observation content")
                image_count += result_images

    subagents = payload.get("subagent_trajectories") or []
    if not isinstance(subagents, list):
        raise ContractError(f"{location}.subagent_trajectories must be a list")
    for index, subagent in enumerate(subagents):
        child = _validate_trajectory(subagent, location=f"{location}.subagent_trajectories[{index}]", depth=depth + 1)
        image_count += child["image_count"]
        image_only_user_steps.extend(child["image_only_user_steps"])
    if depth == 0 and user_step_count == 0:
        raise ContractError("trajectory must contain at least one root user step")
    return {"image_count": image_count, "image_only_user_steps": image_only_user_steps}


def _replace(pattern: re.Pattern[str], value: str, marker: str, counts: dict[str, int], kind: str) -> str:
    replaced, count = pattern.subn(marker, value)
    counts[kind] = counts.get(kind, 0) + count
    return replaced


def _redact_ipv4(value: str, counts: dict[str, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            ipaddress.ip_address(match.group(0))
        except ValueError:
            return match.group(0)
        counts["ipv4"] = counts.get("ipv4", 0) + 1
        return "<redacted:ipv4>"

    return _IPV4.sub(replace, value)


def _redact_phone(value: str, counts: dict[str, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        candidate = match.group(0)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
            return candidate
        digits = sum(character.isdigit() for character in candidate)
        if not 7 <= digits <= 15:
            return candidate
        counts["phone"] = counts.get("phone", 0) + 1
        return "<redacted:phone>"

    return _PHONE.sub(replace, value)


def _redact_text(value: str, counts: dict[str, int]) -> str:
    value = _replace(_PRIVATE_KEY, value, "<redacted:private-key>", counts, "private_key")
    value = _replace(_BEARER, value, "<redacted:bearer-token>", counts, "bearer_token")
    value = _replace(_EMAIL, value, "<redacted:email>", counts, "email")
    value = _replace(_SSN, value, "<redacted:ssn>", counts, "ssn")
    value = _replace(_HOME_PATH, value, "/home/<redacted:user>", counts, "home_path")
    value = _redact_ipv4(value, counts)
    return _redact_phone(value, counts)


def _scrub(value: Any, counts: dict[str, int], *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        if value.get("type") == "image" and isinstance(value.get("source"), dict):
            counts["image"] = counts.get("image", 0) + 1
            return {"type": "text", "text": "[image omitted from text-only evidence]"}
        return {name: _scrub(item, counts, key=name) for name, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, counts, key=key) for item in value]
    if isinstance(value, str):
        if key in _IDENTIFIER_KEYS and value:
            counts["identifier"] = counts.get("identifier", 0) + 1
            return f"anon-{hashlib.sha256(value.encode()).hexdigest()[:16]}"
        if key is not None and _SECRET_KEY.search(key):
            if value:
                counts["secret_field"] = counts.get("secret_field", 0) + 1
                return "<redacted:secret>"
            return value
        return _redact_text(value, counts)
    return value


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    task_dir = _ensure_task_dir(args.task_dir.resolve())
    summary = _load_summary(task_dir)
    if summary["source"] is not None:
        raise ContractError("this task workspace already has prepared source evidence")

    source_path = args.atif.resolve()
    if source_path.is_symlink() or not source_path.is_file():
        raise ContractError(f"ATIF source must be a regular file: {source_path}")
    source_bytes = source_path.read_bytes()
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise ContractError(f"ATIF source exceeds the {MAX_SOURCE_BYTES}-byte limit")
    try:
        payload = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"could not read ATIF source as UTF-8 JSON: {error}") from error
    validation = _validate_trajectory(payload)

    private_path = task_dir / "private" / "source.atif.json"
    safe_path = task_dir / "safe" / "trace.atif.json"
    privacy_path = task_dir / "safe" / "privacy.json"
    if any(path.exists() for path in (private_path, safe_path, privacy_path)):
        raise ContractError("refusing to replace an existing prepared artifact")
    counts: dict[str, int] = {}
    scrubbed = _scrub(payload, counts)
    _validate_trajectory(scrubbed)
    safe_bytes = (json.dumps(scrubbed, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    blocking_reasons = [
        f"image_only_user_instruction:step-{step_id}" for step_id in validation["image_only_user_steps"]
    ]
    privacy = {
        "deterministic_redactions": dict(sorted(counts.items())),
        "images_omitted": counts.get("image", 0),
        "manual_review_required": True,
        "manual_review_complete": False,
        "blocking_reasons": blocking_reasons,
    }
    summary["source"] = {
        "kind": args.source_kind,
        "private_path": "private/source.atif.json",
        "private_sha256": _sha256(source_bytes),
        "safe_path": "safe/trace.atif.json",
        "safe_sha256": _sha256(safe_bytes),
    }
    summary["privacy"] = {"path": "safe/privacy.json", **privacy}
    privacy_bytes = (json.dumps(privacy, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    written: list[Path] = []
    try:
        _write_bytes_once(private_path, source_bytes)
        written.append(private_path)
        _write_bytes_once(safe_path, safe_bytes)
        written.append(safe_path)
        _write_bytes_once(privacy_path, privacy_bytes)
        written.append(privacy_path)
        _write_json(_summary_path(task_dir), summary)
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {
        "task_dir": str(task_dir),
        "status": "prepared",
        "redaction_count": sum(counts.values()),
        "images_omitted": privacy["images_omitted"],
        "blocking_reason_count": len(blocking_reasons),
    }


def _string_list(payload: dict[str, Any], name: str, *, nonempty: bool = False) -> list[str]:
    value = payload.get(name)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ContractError(f"candidate.{name} must be a list of nonempty strings")
    if nonempty and not value:
        raise ContractError(f"candidate.{name} must not be empty")
    return value


def _evidence_steps(value: Any, step_ids: set[int], *, label: str) -> list[int]:
    if (
        not isinstance(value, list)
        or not value
        or any(type(item) is not int for item in value)
        or len(value) != len(set(value))
    ):
        raise ContractError(f"{label} must be a nonempty list of unique integer ATIF step IDs")
    unknown_steps = sorted(set(value) - step_ids)
    if unknown_steps:
        raise ContractError(f"{label} references unknown evidence steps: {unknown_steps}")
    return value


def _validate_ground_truth(task_dir: Path, value: Any, step_ids: set[int]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _GROUND_TRUTH_KEYS:
        raise ContractError("candidate.ground_truth fields do not match the versioned contract")
    availability = value.get("availability")
    if availability not in {"available", "partial", "absent", "unknown"}:
        raise ContractError("candidate.ground_truth.availability is not recognized")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise ContractError("candidate.ground_truth.artifacts must be a list")
    absence_reason = value.get("absence_reason")
    if absence_reason is not None and (not isinstance(absence_reason, str) or not absence_reason.strip()):
        raise ContractError("candidate.ground_truth.absence_reason must be null or nonempty text")
    if availability in {"available", "partial"} and not artifacts:
        raise ContractError("available or partial ground truth must name at least one artifact")
    if availability in {"absent", "unknown"} and (artifacts or absence_reason is None):
        raise ContractError("absent or unknown ground truth needs no artifacts and a reason")
    if availability == "available" and absence_reason is not None:
        raise ContractError("available ground truth must set absence_reason to null")
    if availability == "partial" and absence_reason is None:
        raise ContractError("partial ground truth must explain what is missing")

    allowed_kinds = {
        "reference_trace",
        "expected_output",
        "dataset",
        "fixture",
        "verifier",
        "human_feedback",
        "other",
    }
    for index, artifact in enumerate(artifacts):
        label = f"candidate.ground_truth.artifacts[{index}]"
        if not isinstance(artifact, dict) or set(artifact) != _GROUND_TRUTH_ARTIFACT_KEYS:
            raise ContractError(f"{label} fields do not match the versioned contract")
        if artifact.get("kind") not in allowed_kinds:
            raise ContractError(f"{label}.kind is not recognized")
        relative_path = artifact.get("path")
        if not isinstance(relative_path, str) or not relative_path.startswith("private/ground-truth/"):
            raise ContractError(f"{label}.path must stay under private/ground-truth/")
        artifact_path = task_dir / relative_path
        ground_truth_dir = (task_dir / "private" / "ground-truth").resolve()
        if not artifact_path.resolve().is_relative_to(ground_truth_dir):
            raise ContractError(f"{label}.path escapes private/ground-truth/")
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise ContractError(f"{label}.path must name a retained regular file")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ContractError(f"{label}.sha256 must be a SHA-256 digest")
        if _sha256(artifact_path.read_bytes()) != digest:
            raise ContractError(f"{label}.sha256 does not match the retained artifact")
        if os.name == "posix" and stat.S_IMODE(artifact_path.stat().st_mode) & 0o077:
            raise ContractError(f"{label}.path is not owner-private")
        _evidence_steps(artifact.get("evidence_steps"), step_ids, label=f"{label}.evidence_steps")
        notes = artifact.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise ContractError(f"{label}.notes must be nonempty text")
    return value


def _validate_software_requirements(value: Any, step_ids: set[int]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ContractError("candidate.software_requirements must be a list")
    names: set[str] = set()
    allowed_categories = {"library", "cli", "desktop_application", "service", "hardware", "other"}
    allowed_licenses = {"open_source", "proprietary", "commercial", "unknown", "not_applicable"}
    allowed_availability = {"available", "installable", "unavailable", "unknown"}
    for index, requirement in enumerate(value):
        label = f"candidate.software_requirements[{index}]"
        if not isinstance(requirement, dict) or set(requirement) != _SOFTWARE_REQUIREMENT_KEYS:
            raise ContractError(f"{label} fields do not match the versioned contract")
        name = requirement.get("name")
        if not isinstance(name, str) or not name.strip() or name.casefold() in names:
            raise ContractError(f"{label}.name must be nonempty and unique")
        names.add(name.casefold())
        if requirement.get("category") not in allowed_categories:
            raise ContractError(f"{label}.category is not recognized")
        if type(requirement.get("required")) is not bool:
            raise ContractError(f"{label}.required must be a boolean")
        version = requirement.get("version")
        if version is not None and (not isinstance(version, str) or not version.strip()):
            raise ContractError(f"{label}.version must be null or nonempty text")
        if requirement.get("license") not in allowed_licenses:
            raise ContractError(f"{label}.license is not recognized")
        if requirement.get("availability") not in allowed_availability:
            raise ContractError(f"{label}.availability is not recognized")
        redistributable = requirement.get("redistributable")
        if redistributable is not None and type(redistributable) is not bool:
            raise ContractError(f"{label}.redistributable must be true, false, or null")
        _evidence_steps(requirement.get("evidence_steps"), step_ids, label=f"{label}.evidence_steps")
        notes = requirement.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise ContractError(f"{label}.notes must be nonempty text")
    return value


def _validate_candidate(task_dir: Path, status: str, step_ids: set[int]) -> dict[str, Any]:
    candidate = _load_object(task_dir / "candidate.json", label="candidate")
    if set(candidate) != _CANDIDATE_KEYS:
        raise ContractError("candidate fields do not match the versioned contract")
    if candidate.get("schema") != CANDIDATE_SCHEMA:
        raise ContractError(f"candidate.schema must be {CANDIDATE_SCHEMA!r}")
    if candidate.get("status") != status:
        raise ContractError("candidate status does not match the requested summary status")
    _evidence_steps(candidate.get("evidence_steps"), step_ids, label="candidate.evidence_steps")
    _string_list(candidate, "uncertainties")
    _string_list(candidate, "reason_codes", nonempty=status == "no_candidate")
    _validate_ground_truth(task_dir, candidate.get("ground_truth"), step_ids)
    software_requirements = _validate_software_requirements(candidate.get("software_requirements"), step_ids)
    if status == "candidate":
        if not isinstance(candidate.get("instruction"), str) or not candidate["instruction"].strip():
            raise ContractError("candidate.instruction must be nonempty text")
        _string_list(candidate, "requirements", nonempty=True)
        if candidate.get("verification_mode") != "execution":
            raise ContractError("the basic flow accepts only deterministic execution candidates")
        unavailable = [
            requirement["name"]
            for requirement in software_requirements
            if requirement["required"] and requirement["availability"] == "unavailable"
        ]
        if unavailable:
            raise ContractError(f"candidate requires unavailable software: {', '.join(unavailable)}")
    else:
        if any(candidate.get(name) is not None for name in ("instruction", "verification_mode")):
            raise ContractError("no_candidate records must set instruction and verification_mode to null")
        if candidate.get("requirements") != []:
            raise ContractError("no_candidate records must set requirements to an empty list")
    return candidate


def _validate_environment(task_dir: Path) -> dict[str, Any]:
    environment = task_dir / "task"
    required_files = (
        environment / "README.md",
        environment / "task.toml",
        environment / "instruction.md",
        environment / "tests" / "test.sh",
        environment / "solution" / "solve.sh",
    )
    required_directories = (environment / "environment",)
    missing = [
        str(path.relative_to(task_dir))
        for path in required_files
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0
    ] + [str(path.relative_to(task_dir)) for path in required_directories if path.is_symlink() or not path.is_dir()]
    if missing:
        raise ContractError(f"candidate environment is missing: {', '.join(missing)}")
    readme_path = environment / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("task/README.md must be UTF-8 text") from error
    if re.search(r"(?m)^#\s+\S", readme) is None:
        raise ContractError("task/README.md must have a level-one title")
    headings = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", readme))
    sections = {
        match.group(1): readme[match.end() : headings[index + 1].start() if index + 1 < len(headings) else None].strip()
        for index, match in enumerate(headings)
    }
    missing_sections = [section for section in _TASK_README_SECTIONS if not sections.get(section)]
    if missing_sections:
        raise ContractError(f"task/README.md is missing substantive sections: {', '.join(missing_sections)}")
    validation = _load_object(task_dir / "validation.json", label="environment validation")
    if set(validation) != {"schema", "nop", "oracle"}:
        raise ContractError("validation fields do not match the versioned contract")
    if validation.get("schema") != VALIDATION_SCHEMA:
        raise ContractError(f"validation.schema must be {VALIDATION_SCHEMA!r}")
    for arm, reward in (("nop", 0), ("oracle", 1)):
        result = validation.get(arm)
        if not isinstance(result, dict) or set(result) != {"reward", "exception", "job_dir"}:
            raise ContractError(f"validation.{arm} must be an object")
        if result.get("reward") != reward or result.get("exception") is not None:
            raise ContractError(f"validation.{arm} must have reward {reward} and no exception")
        job_dir = result.get("job_dir")
        if not isinstance(job_dir, str) or not job_dir.strip():
            raise ContractError(f"validation.{arm}.job_dir must name the Harbor evidence directory")
        job_path = task_dir / job_dir
        resolved_job_path = job_path.resolve()
        if not resolved_job_path.is_relative_to(task_dir.resolve()):
            raise ContractError(f"validation.{arm}.job_dir must stay inside the task workspace")
        if job_path.is_symlink() or not job_path.is_dir():
            raise ContractError(f"validation.{arm}.job_dir does not exist as a regular directory")
    return validation


def _summary_markdown(summary: dict[str, Any]) -> str:
    def bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values) if values else "- None recorded."

    candidate = summary["candidate"] or {}
    ground_truth = candidate.get("ground_truth") or {"availability": "unrecorded", "artifacts": []}
    software = candidate.get("software_requirements") or []
    software_lines = [
        (
            f"- {item['name']} ({item['category']}): required={str(item['required']).lower()}, "
            f"version={item['version'] or 'unknown'}, license={item['license']}, "
            f"availability={item['availability']}, "
            f"redistributable={str(item['redistributable']).lower()}"
        )
        for item in software
    ]
    return (
        f"# Trace environment: {summary['task_id']}\n\n"
        f"## Status\n\n`{summary['status']}`\n\n"
        f"## Evidence\n\n"
        f"- Safe ATIF: `{summary['source']['safe_path']}`\n"
        f"- Evidence steps: {candidate.get('evidence_steps', [])}\n"
        f"- Environment: `{summary['environment']['status']}`\n\n"
        f"## Ground truth\n\n"
        f"- Availability: `{ground_truth['availability']}`\n"
        f"- Retained artifacts: {len(ground_truth['artifacts'])}\n"
        f"- Absence or uncertainty: {ground_truth.get('absence_reason') or 'None'}\n\n"
        f"## Software requirements\n\n"
        f"{chr(10).join(software_lines) if software_lines else '- None recorded.'}\n\n"
        f"## What worked well\n\n{bullets(summary['worked_well'])}\n\n"
        f"## What did not work\n\n{bullets(summary['did_not_work'])}\n\n"
        f"## Reasons\n\n{bullets(summary['reasons'])}\n"
    )


def _finalize(args: argparse.Namespace) -> dict[str, Any]:
    task_dir = _ensure_task_dir(args.task_dir.resolve())
    summary = _load_summary(task_dir)
    if summary["source"] is None or summary["privacy"] is None:
        raise ContractError("prepare canonical ATIF evidence before finalizing")
    if summary["status"] != "pending":
        raise ContractError("this task workspace has already been finalized")

    safe_path = task_dir / summary["source"]["safe_path"]
    safe_payload = _load_object(safe_path, label="safe ATIF")
    _validate_trajectory(safe_payload)
    step_ids = {step["step_id"] for step in safe_payload["steps"]}
    candidate = _validate_candidate(task_dir, args.status, step_ids)

    privacy = summary["privacy"]
    privacy_review_complete = privacy["manual_review_complete"] or args.privacy_reviewed
    if args.status == "candidate" and not privacy_review_complete:
        raise ContractError("candidate finalization requires --privacy-reviewed after contextual review")
    if args.status == "candidate" and privacy["blocking_reasons"]:
        raise ContractError("candidate finalization is blocked by unresolved non-text evidence")

    validation: dict[str, Any] | None = None
    environment_status = args.environment_status
    if args.status == "no_candidate":
        if environment_status != "not_attempted":
            raise ContractError("no_candidate must use environment status not_attempted")
    elif environment_status == "ready":
        validation = _validate_environment(task_dir)

    if args.privacy_reviewed:
        privacy["manual_review_complete"] = True
        privacy_payload = _load_object(task_dir / privacy["path"], label="privacy report")
        privacy_payload["manual_review_complete"] = True
        _write_json(task_dir / privacy["path"], privacy_payload)

    reasons = list(args.reason)
    if args.status == "no_candidate" and not reasons:
        reasons = list(candidate["reason_codes"])
    summary.update(
        {
            "status": args.status,
            "candidate": {"path": "candidate.json", **candidate},
            "environment": {
                "path": "task",
                "status": environment_status,
                "validation": "validation.json" if validation is not None else None,
            },
            "worked_well": list(args.worked_well),
            "did_not_work": list(args.did_not_work),
            "reasons": reasons,
        }
    )
    _write_json(_summary_path(task_dir), summary)
    _write_text(task_dir / "summary.md", _summary_markdown(summary))
    return {
        "task_dir": str(task_dir),
        "status": args.status,
        "environment_status": environment_status,
        "summary": str(task_dir / "summary.md"),
    }


def _check(args: argparse.Namespace) -> dict[str, Any]:
    task_dir = _ensure_task_dir(args.task_dir.resolve())
    summary = _load_summary(task_dir)
    errors: list[str] = []
    source = summary.get("source")
    if isinstance(source, dict):
        for path_key, digest_key in (("private_path", "private_sha256"), ("safe_path", "safe_sha256")):
            path = task_dir / source[path_key]
            if not path.is_file() or _sha256(path.read_bytes()) != source[digest_key]:
                errors.append(f"{path_key} is missing or its digest changed")
            elif os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
                errors.append(f"{path_key} is not owner-private")
    else:
        errors.append("source has not been prepared")
    privacy = summary.get("privacy")
    if isinstance(privacy, dict):
        try:
            privacy_payload = _load_object(task_dir / "safe" / "privacy.json", label="privacy report")
            if privacy != {"path": "safe/privacy.json", **privacy_payload}:
                errors.append("privacy report does not match the summary")
        except ContractError as error:
            errors.append(str(error))
    elif source is not None:
        errors.append("privacy report has not been prepared")
    if summary.get("status") in {"candidate", "no_candidate"} and isinstance(source, dict):
        safe = _load_object(task_dir / source["safe_path"], label="safe ATIF")
        step_ids = {step["step_id"] for step in safe.get("steps", []) if isinstance(step, dict) and "step_id" in step}
        try:
            candidate = _validate_candidate(task_dir, summary["status"], step_ids)
            if summary.get("candidate") != {"path": "candidate.json", **candidate}:
                errors.append("candidate record does not match the summary")
            if summary.get("environment", {}).get("status") == "ready":
                _validate_environment(task_dir)
            markdown_path = task_dir / "summary.md"
            if not markdown_path.is_file() or markdown_path.read_text(encoding="utf-8") != _summary_markdown(summary):
                errors.append("summary.md is missing or does not match summary.json")
        except ContractError as error:
            errors.append(str(error))
    return {"task_dir": str(task_dir), "valid": not errors, "errors": errors}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create one private, gitignored task workspace")
    init.add_argument("--root", type=Path, default=Path(".eval-author/trace-environments"))
    init.add_argument("--task-id", required=True, type=_validate_task_id)
    init.set_defaults(run=_init)

    prepare = subparsers.add_parser("prepare", help="validate and scrub one canonical ATIF trajectory")
    prepare.add_argument("--task-dir", required=True, type=Path)
    prepare.add_argument("--atif", required=True, type=Path)
    prepare.add_argument("--source-kind", choices=("atif", "intake", "mlflow", "otel"), required=True)
    prepare.set_defaults(run=_prepare)

    finalize = subparsers.add_parser("finalize", help="write the candidate decision and task summary")
    finalize.add_argument("--task-dir", required=True, type=Path)
    finalize.add_argument("--status", choices=("candidate", "no_candidate"), required=True)
    finalize.add_argument(
        "--environment-status",
        choices=("ready", "failed", "unproven", "not_attempted"),
        default="not_attempted",
    )
    finalize.add_argument("--privacy-reviewed", action="store_true")
    finalize.add_argument("--worked-well", action="append", default=[])
    finalize.add_argument("--did-not-work", action="append", default=[])
    finalize.add_argument("--reason", action="append", default=[])
    finalize.set_defaults(run=_finalize)

    check = subparsers.add_parser("check", help="verify recorded digests and generated artifacts")
    check.add_argument("--task-dir", required=True, type=Path)
    check.set_defaults(run=_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        result = args.run(args)
    except (ContractError, OSError) as error:
        print(json.dumps({"error": str(error), "error_type": "contract"}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("valid", True) else 1


if __name__ == "__main__":
    sys.exit(main())
