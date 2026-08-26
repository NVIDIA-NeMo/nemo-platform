#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Measure one ATIF trace against an audit-spec denominator."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _markdown import AuditMarkdownError  # noqa: E402
from _schema import AuditEnvironmentError, AuditSpecError, load_audit_spec  # noqa: E402
from _types import JsonObject, MeasurementMethod, TrajectoryLike  # noqa: E402
from measurements import tool_calls  # noqa: E402

COVERAGE_SCHEMA = "nemo.eval_author.audit_coverage.v1"
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
COVERAGE_SCHEMA_PATH = SCHEMAS_DIR / "audit_coverage.schema.json"
DETAIL_SCHEMA_PATHS = {
    tool_calls.DETAILS_SCHEMA: SCHEMAS_DIR / "audit_tool_calls_details.schema.json",
}
METHODS: dict[str, MeasurementMethod] = {tool_calls.METHOD_NAME: cast(MeasurementMethod, tool_calls)}


class AuditTraceError(ValueError):
    """Raised when the trace input cannot be interpreted."""


class AuditMeasurementError(ValueError):
    """Raised when measurement configuration or output is invalid."""


@dataclass(frozen=True)
class Subject:
    """The trace subject being measured."""

    trace_path: Path
    task_id: str
    run_id: str | None

    def to_json(self) -> JsonObject:
        payload: JsonObject = {
            "trace": str(self.trace_path),
            "trace_format": "atif",
            "task_id": self.task_id,
        }
        if self.run_id is not None:
            payload["run_id"] = self.run_id
        return payload


@dataclass(frozen=True)
class MeasurementReport:
    """In-memory coverage/details output for one measurement method."""

    method_name: str
    coverage: JsonObject
    details: JsonObject


@dataclass(frozen=True)
class WrittenMeasurement:
    """Filesystem paths and aggregation facts written for one method."""

    method_name: str
    item_kind: str
    coverage_path: Path
    details_path: Path
    covered: list[str]

    def to_summary(self) -> JsonObject:
        return {
            "method": self.method_name,
            "item_kind": self.item_kind,
            "coverage": str(self.coverage_path),
            "details": str(self.details_path),
            "covered": self.covered,
            "covered_count": len(self.covered),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True, help="audit.md file to measure against")
    subject = parser.add_mutually_exclusive_group(required=True)
    subject.add_argument("--trace", type=Path, help="ATIF trajectory JSON file")
    subject.add_argument("--trial-dir", type=Path, help="Harbor trial directory containing agent/trajectory.json")
    parser.add_argument("--task-id", help="task id to stamp on the measurement report")
    parser.add_argument("--run-id", help="run id to stamp on the measurement report")
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="directory where <task-id>/<method>/coverage.json and details.json will be written",
    )
    parser.add_argument(
        "--measure",
        action="append",
        help=f"comma-separated measurement methods to run (default: {tool_calls.METHOD_NAME})",
    )
    parser.add_argument("--method", action="append", dest="legacy_measure", help=argparse.SUPPRESS)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    try:
        method_names = _measurement_methods(args.measure, args.legacy_measure)
        audit = load_audit_spec(args.audit)
        subject_info = _subject(args)
        trajectory = _load_harbor_trajectory(subject_info.trace_path)
        reports = _measure_all(
            audit=audit,
            audit_path=args.audit,
            trajectory=trajectory,
            subject=subject_info,
            method_names=method_names,
        )
        _validate_reports(reports)
        written_reports = _write_reports(
            reports, out_dir=args.out_dir, task_id=subject_info.task_id, compact=args.compact
        )
    except AuditEnvironmentError as exc:
        _print({"valid": None, "written": False, "error_type": "environment", "error": str(exc)}, compact=args.compact)
        return 2
    except (AuditMarkdownError, AuditSpecError) as exc:
        _print({"valid": False, "written": False, "error_type": "audit_spec", "error": str(exc)}, compact=args.compact)
        return 1
    except AuditTraceError as exc:
        _print({"valid": True, "written": False, "error_type": "trace", "error": str(exc)}, compact=args.compact)
        return 1
    except AuditMeasurementError as exc:
        _print({"valid": True, "written": False, "error_type": "measurement", "error": str(exc)}, compact=args.compact)
        return 1

    summary: JsonObject = {
        "valid": True,
        "written": True,
        "audit": str(args.audit),
        "trace": str(subject_info.trace_path),
        "task_id": subject_info.task_id,
        "methods": [report.method_name for report in written_reports],
        "measurements": [report.to_summary() for report in written_reports],
    }
    if subject_info.run_id is not None:
        summary["run_id"] = subject_info.run_id
    _print(summary, compact=args.compact)
    return 0


# Resolve the requested trace and provider-neutral subject identifiers before parsing ATIF.
def _subject(args: argparse.Namespace) -> Subject:
    if args.trial_dir is not None:
        return _subject_from_trial_dir(args.trial_dir, task_id=args.task_id, run_id=args.run_id)
    if args.trace is None:
        raise AuditTraceError("provide --trace or --trial-dir")
    return _subject_from_trace(args.trace, task_id=args.task_id, run_id=args.run_id)


# Derive task/run identity from Harbor metadata when a trial directory is supplied.
def _subject_from_trial_dir(trial_dir: Path, *, task_id: str | None, run_id: str | None) -> Subject:
    if not trial_dir.is_dir():
        raise AuditTraceError(f"Harbor trial directory does not exist: {trial_dir}")
    trace_path = trial_dir / "agent" / "trajectory.json"
    if not trace_path.exists():
        raise AuditTraceError(
            f"Harbor trial did not emit an ATIF trace at {trace_path}; agents without SUPPORTS_ATIF may omit it"
        )
    result_path = trial_dir / "result.json"
    result = _load_harbor_result(result_path)
    return Subject(
        trace_path=trace_path,
        task_id=task_id or _string(result.get("task_name")) or trial_dir.name,
        run_id=run_id or _string(result.get("trial_name")) or trial_dir.name,
    )


# Derive task/run identity from a direct trace path, honoring explicit CLI stamps first.
def _subject_from_trace(trace_path: Path, *, task_id: str | None, run_id: str | None) -> Subject:
    trial_dir = _harbor_trial_dir_for_trace(trace_path)
    result_path = trial_dir / "result.json" if trial_dir is not None else None
    result = _load_harbor_result(result_path) if result_path is not None else {}
    return Subject(
        trace_path=trace_path,
        task_id=task_id or _string(result.get("task_name")) or trace_path.stem,
        run_id=run_id or _string(result.get("trial_name")) or (trial_dir.name if trial_dir is not None else None),
    )


# Recognize the common Harbor trial layout without putting Harbor fields in report schemas.
def _harbor_trial_dir_for_trace(trace_path: Path) -> Path | None:
    if trace_path.name == "trajectory.json" and trace_path.parent.name == "agent":
        return trace_path.parent.parent
    return None


# Read optional Harbor result metadata only to infer provider-neutral task/run ids.
def _load_harbor_result(path: Path) -> JsonObject:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditTraceError(f"could not read Harbor result metadata at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditTraceError(f"Harbor result metadata at {path} must be a JSON object")
    return payload


# Read ATIF through Harbor once; downstream methods receive the typed trajectory object.
def _load_harbor_trajectory(path: Path) -> TrajectoryLike:
    try:
        from harbor.models.trajectories import Trajectory  # ty: ignore[unresolved-import]
    except ImportError as exc:
        raise AuditEnvironmentError(
            "harbor is required to read ATIF traces; install the skill dependencies from requirements.txt"
        ) from exc

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AuditTraceError(f"could not read Harbor ATIF trajectory at {path}: {exc}") from exc
    try:
        return Trajectory.model_validate_json(text)
    except ValueError as exc:
        raise AuditTraceError(f"{path} is not an ATIF trajectory accepted by Harbor: {exc}") from exc


# Parse comma-separated method selections and de-duplicate them in request order.
def _measurement_methods(measure_values: list[str] | None, legacy_values: list[str] | None) -> list[str]:
    """Return selected measurement methods from comma-separated CLI values."""
    values = (measure_values or []) + (legacy_values or [])
    if not values:
        values = [tool_calls.METHOD_NAME]

    method_names: list[str] = []
    for value in values:
        method_names.extend(name.strip() for name in value.split(",") if name.strip())
    if not method_names:
        raise AuditMeasurementError("--measure must name at least one measurement method")

    unknown = sorted({name for name in method_names if name not in METHODS})
    if unknown:
        available = ", ".join(sorted(METHODS))
        raise AuditMeasurementError(f"unknown measurement method(s): {', '.join(unknown)}; available: {available}")

    return list(dict.fromkeys(method_names))


# Fan the shared trajectory into each selected measurement method.
def _measure_all(
    *,
    audit: JsonObject,
    audit_path: Path,
    trajectory: TrajectoryLike,
    subject: Subject,
    method_names: list[str],
) -> list[MeasurementReport]:
    return [
        _measure(audit=audit, audit_path=audit_path, trajectory=trajectory, subject=subject, method_name=method_name)
        for method_name in method_names
    ]


# Wrap one method's raw result in the shared coverage/details envelope.
def _measure(
    *,
    audit: JsonObject,
    audit_path: Path,
    trajectory: TrajectoryLike,
    subject: Subject,
    method_name: str,
) -> MeasurementReport:
    method = METHODS[method_name]
    measurement = method.measure(audit, trajectory)
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
    return MeasurementReport(method_name=method.METHOD_NAME, coverage=coverage, details=details)


# Validate every generated report before any files are written.
def _validate_reports(reports: list[MeasurementReport]) -> None:
    for report in reports:
        _validate_report(report.coverage, schema_path=COVERAGE_SCHEMA_PATH, label=f"{report.method_name} coverage")
        _validate_report(
            report.details,
            schema_path=_details_schema_path(report.details),
            label=f"{report.method_name} details",
        )


# Write one coverage/details file pair per selected measurement method.
def _write_reports(
    reports: list[MeasurementReport],
    *,
    out_dir: Path,
    task_id: str,
    compact: bool,
) -> list[WrittenMeasurement]:
    written_reports: list[WrittenMeasurement] = []
    for report in reports:
        method_dir = out_dir / task_id / report.method_name
        method_dir.mkdir(parents=True, exist_ok=True)
        coverage_path = method_dir / "coverage.json"
        details_path = method_dir / "details.json"
        coverage_path.write_text(_json(report.coverage, compact=compact) + "\n", encoding="utf-8")
        details_path.write_text(_json(report.details, compact=compact) + "\n", encoding="utf-8")
        written_reports.append(
            WrittenMeasurement(
                method_name=report.method_name,
                item_kind=report.coverage["item_kind"],
                coverage_path=coverage_path,
                details_path=details_path,
                covered=report.coverage["covered"],
            )
        )
    return written_reports


# Record only denominator identity, not the audit items themselves.
def _audit_info(audit: JsonObject, audit_path: Path) -> JsonObject:
    return {
        "path": str(audit_path),
        "schema": audit["schema"],
        "agent": audit["agent"],
        "status": audit["status"],
        "item_count": len(audit["items"]),
    }


# Resolve the JSON Schema for a method-specific details payload.
def _details_schema_path(details: JsonObject) -> Path:
    schema = details.get("schema")
    if not isinstance(schema, str) or schema not in DETAIL_SCHEMA_PATHS:
        raise AuditMeasurementError(f"no details JSON Schema is registered for {schema!r}")
    return DETAIL_SCHEMA_PATHS[schema]


# Validate generated JSON against the schema committed with the skill.
def _validate_report(report: JsonObject, *, schema_path: Path, label: str) -> None:
    try:
        from jsonschema import Draft202012Validator  # ty: ignore[unresolved-import]
        from jsonschema.exceptions import SchemaError  # ty: ignore[unresolved-import]
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


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _json(payload: JsonObject, *, compact: bool) -> str:
    if compact:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return json.dumps(payload, sort_keys=True, indent=2)


def _print(payload: JsonObject, *, compact: bool) -> None:
    print(_json(payload, compact=compact))


if __name__ == "__main__":
    raise SystemExit(main())
