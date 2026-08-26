#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Measure one Harbor/ATIF trace against an audit-spec denominator."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _atif import AtifTraceError, AtifTraceFacts, load_atif_trace  # noqa: E402
from _markdown import AuditMarkdownError  # noqa: E402
from _schema import AuditEnvironmentError, AuditSpecError, load_audit_spec  # noqa: E402
from measurements import tool_calls  # noqa: E402

COVERAGE_SCHEMA = "nemo.eval_author.audit_coverage.v1"
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
COVERAGE_SCHEMA_PATH = SCHEMAS_DIR / "audit_coverage.schema.json"
DETAIL_SCHEMA_PATHS = {
    tool_calls.DETAILS_SCHEMA: SCHEMAS_DIR / "audit_tool_calls_details.schema.json",
}
METHODS = {tool_calls.METHOD_NAME: tool_calls}


class AuditMeasurementError(ValueError):
    """Raised when a measurement input cannot be interpreted."""


@dataclass(frozen=True)
class Subject:
    """The trace subject being measured."""

    trace_path: Path
    task_id: str
    trial_id: str | None
    harbor_trial_dir: Path | None
    harbor_result_path: Path | None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trace": str(self.trace_path),
            "trace_format": "atif",
            "task_id": self.task_id,
        }
        if self.trial_id is not None:
            payload["trial_id"] = self.trial_id
        if self.harbor_trial_dir is not None:
            payload["harbor_trial_dir"] = str(self.harbor_trial_dir)
        if self.harbor_result_path is not None:
            payload["harbor_result"] = str(self.harbor_result_path)
        return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True, help="audit.md file to measure against")
    subject = parser.add_mutually_exclusive_group(required=True)
    subject.add_argument("--trace", type=Path, help="ATIF trajectory JSON file")
    subject.add_argument("--trial-dir", type=Path, help="Harbor trial directory containing agent/trajectory.json")
    parser.add_argument("--task-id", help="task id to stamp on the measurement report")
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="directory where <task-id>/<method>/coverage.json and details.json will be written",
    )
    parser.add_argument("--method", choices=sorted(METHODS), default=tool_calls.METHOD_NAME)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    try:
        audit = load_audit_spec(args.audit)
        subject_info = _subject(args)
        trace = load_atif_trace(subject_info.trace_path)
        coverage, details = _measure(
            audit=audit, audit_path=args.audit, trace=trace, subject=subject_info, method_name=args.method
        )
        _validate_report(coverage, schema_path=COVERAGE_SCHEMA_PATH, label="audit coverage")
        _validate_report(
            details,
            schema_path=_details_schema_path(details),
            label=f"{args.method} details",
        )
        method_dir = args.out_dir / subject_info.task_id / args.method
        method_dir.mkdir(parents=True, exist_ok=True)
        coverage_path = method_dir / "coverage.json"
        details_path = method_dir / "details.json"
        coverage_path.write_text(_json(coverage, compact=args.compact) + "\n", encoding="utf-8")
        details_path.write_text(_json(details, compact=args.compact) + "\n", encoding="utf-8")
    except AuditEnvironmentError as exc:
        _print({"valid": None, "written": False, "error_type": "environment", "error": str(exc)}, compact=args.compact)
        return 2
    except (AuditMarkdownError, AuditSpecError) as exc:
        _print({"valid": False, "written": False, "error_type": "audit_spec", "error": str(exc)}, compact=args.compact)
        return 1
    except (AuditMeasurementError, AtifTraceError) as exc:
        _print({"valid": True, "written": False, "error_type": "trace", "error": str(exc)}, compact=args.compact)
        return 1

    _print(
        {
            "valid": True,
            "written": True,
            "coverage": str(coverage_path),
            "details": str(details_path),
            "audit": str(args.audit),
            "trace": str(subject_info.trace_path),
            "task_id": subject_info.task_id,
            "method": args.method,
            "item_kind": coverage["item_kind"],
            "covered": coverage["covered"],
            "covered_count": len(coverage["covered"]),
        },
        compact=args.compact,
    )
    return 0


def _subject(args: argparse.Namespace) -> Subject:
    if args.trial_dir is not None:
        return _subject_from_trial_dir(args.trial_dir, task_id=args.task_id)
    if args.trace is None:
        raise AuditMeasurementError("provide --trace or --trial-dir")
    return _subject_from_trace(args.trace, task_id=args.task_id)


def _subject_from_trial_dir(trial_dir: Path, *, task_id: str | None) -> Subject:
    if not trial_dir.is_dir():
        raise AuditMeasurementError(f"Harbor trial directory does not exist: {trial_dir}")
    trace_path = trial_dir / "agent" / "trajectory.json"
    if not trace_path.exists():
        raise AuditMeasurementError(
            f"Harbor trial did not emit an ATIF trace at {trace_path}; agents without SUPPORTS_ATIF may omit it"
        )
    result_path = trial_dir / "result.json"
    result = _load_harbor_result(result_path)
    return Subject(
        trace_path=trace_path,
        task_id=task_id or _string(result.get("task_name")) or trial_dir.name,
        trial_id=_string(result.get("trial_name")) or trial_dir.name,
        harbor_trial_dir=trial_dir,
        harbor_result_path=result_path if result_path.exists() else None,
    )


def _subject_from_trace(trace_path: Path, *, task_id: str | None) -> Subject:
    trial_dir = _harbor_trial_dir_for_trace(trace_path)
    result_path = trial_dir / "result.json" if trial_dir is not None else None
    result = _load_harbor_result(result_path) if result_path is not None else {}
    return Subject(
        trace_path=trace_path,
        task_id=task_id or _string(result.get("task_name")) or trace_path.stem,
        trial_id=_string(result.get("trial_name")) or (trial_dir.name if trial_dir is not None else None),
        harbor_trial_dir=trial_dir,
        harbor_result_path=result_path if result_path is not None and result_path.exists() else None,
    )


def _harbor_trial_dir_for_trace(trace_path: Path) -> Path | None:
    if trace_path.name == "trajectory.json" and trace_path.parent.name == "agent":
        return trace_path.parent.parent
    return None


def _load_harbor_result(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditMeasurementError(f"could not read Harbor result metadata at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditMeasurementError(f"Harbor result metadata at {path} must be a JSON object")
    return payload


def _measure(
    *,
    audit: dict[str, Any],
    audit_path: Path,
    trace: AtifTraceFacts,
    subject: Subject,
    method_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    method = METHODS[method_name]
    measurement = method.measure(audit, trace)
    audit_info = _audit_info(audit, audit_path)
    subject_info = subject.to_json()
    method_info = {"name": method.METHOD_NAME}
    coverage = {
        "schema": COVERAGE_SCHEMA,
        "audit": audit_info,
        "subject": subject_info,
        "method": method_info,
        "item_kind": measurement["item_kind"],
        "covered": measurement["covered"],
    }
    details = {
        **measurement["details"],
        "audit": audit_info,
        "subject": subject_info,
        "method": method_info,
    }
    return coverage, details


def _audit_info(audit: dict[str, Any], audit_path: Path) -> dict[str, Any]:
    return {
        "path": str(audit_path),
        "schema": audit["schema"],
        "agent": audit["agent"],
        "status": audit["status"],
        "item_count": len(audit["items"]),
    }


def _details_schema_path(details: dict[str, Any]) -> Path:
    schema = details.get("schema")
    if not isinstance(schema, str) or schema not in DETAIL_SCHEMA_PATHS:
        raise AuditMeasurementError(f"no details JSON Schema is registered for {schema!r}")
    return DETAIL_SCHEMA_PATHS[schema]


def _validate_report(report: dict[str, Any], *, schema_path: Path, label: str) -> None:
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError as exc:
        raise AuditEnvironmentError(f"jsonschema is required to validate {label} reports") from exc

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditEnvironmentError(f"could not load {label} JSON Schema from {schema_path}: {exc}") from exc

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise AuditEnvironmentError(f"bundled {label} JSON Schema is invalid: {exc.message}") from exc
    errors = sorted(
        Draft202012Validator(schema).iter_errors(report),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        raise AuditMeasurementError(
            f"generated {label} report failed its JSON Schema: "
            + "\n".join(f"{list(error.absolute_path)}: {error.message}" for error in errors)
        )


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _json(payload: dict[str, Any], *, compact: bool) -> str:
    kwargs = {"separators": (",", ":")} if compact else {"indent": 2}
    return json.dumps(payload, sort_keys=True, **kwargs)


def _print(payload: dict[str, Any], *, compact: bool) -> None:
    print(_json(payload, compact=compact))


if __name__ == "__main__":
    raise SystemExit(main())
