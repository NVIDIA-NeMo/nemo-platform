#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Select actionable audit gaps, scaffold Harbor drafts, and verify closure."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

_ACTIONABLE_REASON = "not_covered_by_any_input_report"
_DRAFT_PARTS = (".eval-author", "task-drafts")


class PipelineError(ValueError):
    """A user-correctable pipeline input error."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PipelineError(f"expected a JSON object: {path}")
    return payload


def _actionable_tools(report: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = []
    for item in report.get("uncovered_items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "tool" or item.get("reason") != _ACTIONABLE_REASON:
            continue
        generation = item.get("generation") or {}
        gaps.append(
            {
                "name": item.get("name"),
                "kind": "tool",
                "reason": item.get("reason"),
                "description": item.get("description"),
                "focus": generation.get("focus"),
                "needed_tools": generation.get("needed_tools") or [],
                "evidence_required": generation.get("evidence_required") or [],
            }
        )
    return sorted(gaps, key=lambda gap: str(gap["name"]))


def _select(report_path: Path, target: str | None) -> dict[str, Any]:
    gaps = _actionable_tools(_read_json(report_path))
    if target is not None:
        gaps = [gap for gap in gaps if gap["name"] == target]
        if not gaps:
            raise PipelineError(f"{target!r} is not an actionable uncovered tool in {report_path}")
    return {
        "schema": "nemo.eval_author.task_gap_selection.v1",
        "report": str(report_path),
        "actionable_count": len(gaps),
        "actionable_tools": gaps,
        "valid": True,
    }


def _require_draft_destination(path: Path) -> None:
    parts = path.resolve().parts
    for index in range(len(parts) - 1):
        if parts[index : index + 2] == _DRAFT_PARTS:
            return
    raise PipelineError("draft output must be under .eval-author/task-drafts/")


def _scaffold(
    *,
    report_path: Path,
    target: str,
    output: Path,
    task_name: str,
    description: str,
    author: str,
    instruction_file: Path,
) -> dict[str, Any]:
    _select(report_path, target)
    _require_draft_destination(output)
    if output.exists():
        raise PipelineError(f"draft output already exists: {output}")
    if Path(task_name).name != output.name:
        raise PipelineError("draft directory name must match the final component of --task-name")
    try:
        instruction = instruction_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"cannot read instruction {instruction_file}: {exc}") from exc
    if not instruction.strip():
        raise PipelineError("instruction file is empty")
    harbor = shutil.which("harbor")
    if harbor is None:
        raise PipelineError("harbor executable is not available")

    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            harbor,
            "task",
            "init",
            task_name,
            "--tasks-dir",
            str(output.parent),
            "--description",
            description,
            "--author",
            author,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PipelineError(f"harbor task init failed: {result.stderr or result.stdout}")
    if not output.is_dir():
        raise PipelineError(f"harbor did not create the expected draft: {output}")
    (output / "instruction.md").write_text(instruction, encoding="utf-8")
    return {
        "schema": "nemo.eval_author.harbor_task_draft.v1",
        "target_tool": target,
        "draft": str(output),
        "task_name": task_name,
        "scaffolder": "harbor task init",
        "valid": True,
        "written": True,
    }


def _verify(before_path: Path, after_paths: list[Path], target: str) -> tuple[int, dict[str, Any]]:
    before = _read_json(before_path)
    before_uncovered = set(before.get("uncovered") or [])
    if target not in before_uncovered:
        raise PipelineError(f"{target!r} was not uncovered in the before report")
    if not after_paths:
        raise PipelineError("at least one --after report is required")

    runs = []
    all_covered = True
    for path in after_paths:
        report = _read_json(path)
        covered = target in set(report.get("covered") or [])
        still_uncovered = target in set(report.get("uncovered") or [])
        passed = covered and not still_uncovered
        all_covered = all_covered and passed
        runs.append({"report": str(path), "covered": covered, "passed": passed})

    payload = {
        "schema": "nemo.eval_author.task_gap_verification.v1",
        "target_tool": target,
        "before": str(before_path),
        "repeat_count": len(runs),
        "runs": runs,
        "accepted": all_covered,
        "valid": True,
    }
    return (0 if all_covered else 1), payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    select = subparsers.add_parser("select", help="list actionable uncovered tool gaps")
    select.add_argument("--report", type=Path, required=True)
    select.add_argument("--target")

    scaffold = subparsers.add_parser("scaffold", help="initialize a Harbor-native task draft")
    scaffold.add_argument("--report", type=Path, required=True)
    scaffold.add_argument("--target", required=True)
    scaffold.add_argument("--out", type=Path, required=True)
    scaffold.add_argument("--task-name", required=True)
    scaffold.add_argument("--description", required=True)
    scaffold.add_argument("--author", required=True)
    scaffold.add_argument("--instruction-file", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="require every repeat to close one gap")
    verify.add_argument("--before", type=Path, required=True)
    verify.add_argument("--after", type=Path, action="append", required=True)
    verify.add_argument("--target", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "select":
            payload = _select(args.report, args.target)
            exit_code = 0
        elif args.command == "scaffold":
            payload = _scaffold(
                report_path=args.report,
                target=args.target,
                output=args.out,
                task_name=args.task_name,
                description=args.description,
                author=args.author,
                instruction_file=args.instruction_file,
            )
            exit_code = 0
        else:
            exit_code, payload = _verify(args.before, args.after, args.target)
    except PipelineError as exc:
        payload = {"valid": False, "error": str(exc)}
        exit_code = 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
