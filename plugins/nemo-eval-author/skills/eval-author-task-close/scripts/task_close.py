#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Inspect generated Harbor task drafts and classify coverage closure evidence."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

_ACTIONABLE_REASON = "not_covered_by_any_input_report"
_DRAFT_PARTS = (".eval-author", "task-drafts")
_CLOSURE_PARTS = (".eval-author", "task-closures")
_REQUIRED_TASK_FILES = (
    "instruction.md",
    "task.toml",
    "environment/Dockerfile",
    "tests/test.sh",
    "solution/solve.sh",
)
_MIN_AFTER_REPORTS = 2
_REWARD_THRESHOLD = 1.0


class CloseError(ValueError):
    """A user-correctable task-close input error."""


def _read_text(path: Path) -> str:
    """Read UTF-8 text from ``path`` or raise ``CloseError``."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CloseError(f"cannot read {path}: {exc}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    """Load one JSON object from ``path`` or raise ``CloseError``."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CloseError(f"expected a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` under the task-closure work area."""
    _require_parts(path, _CLOSURE_PARTS, "output must be under .eval-author/task-closures/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_parts(path: Path, parts: tuple[str, str], message: str) -> None:
    """Require ``path`` to live under a named ``.eval-author`` subdirectory."""
    resolved_parts = path.resolve().parts
    for index in range(len(resolved_parts) - 1):
        if resolved_parts[index : index + 2] == parts:
            return
    raise CloseError(message)


def _check(name: str, passed: bool, message: str, *, severity: str = "required") -> dict[str, Any]:
    """Build one draft inspection check."""
    return {
        "name": name,
        "passed": passed,
        "severity": severity,
        "message": message,
    }


def _preflight(*, require_docker: bool) -> tuple[int, dict[str, Any]]:
    """Check local tools needed for task closure without starting a task."""
    checks: list[dict[str, Any]] = []
    harbor = shutil.which("harbor")
    checks.append(_check("harbor:available", harbor is not None, "harbor executable is available"))
    harbor_compatible = False
    if harbor is not None:
        result = subprocess.run(
            [harbor, "trial", "start", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        harbor_compatible = result.returncode == 0
        checks.append(
            _check(
                "harbor:trial_start",
                harbor_compatible,
                "harbor exposes `trial start` for single-task Oracle and real-agent runs",
            )
        )

    docker_ready = None
    if require_docker:
        docker = shutil.which("docker")
        checks.append(_check("docker:available", docker is not None, "docker executable is available"))
        if docker is not None:
            result = subprocess.run(
                [docker, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                check=False,
            )
            docker_ready = result.returncode == 0
            checks.append(_check("docker:daemon", docker_ready, "docker daemon is reachable"))

    required_failed = [check for check in checks if check["severity"] == "required" and not check["passed"]]
    if harbor is None:
        status = "blocked_no_harbor"
        next_step = "Install or expose a Harbor CLI compatible with `harbor trial start`."
    elif not harbor_compatible:
        status = "blocked_incompatible_harbor"
        next_step = "Use a Harbor CLI version that exposes `harbor trial start`."
    elif docker_ready is False or (require_docker and docker_ready is None):
        status = "blocked_no_docker"
        next_step = "Start Docker or use a supported non-Docker Harbor environment before Oracle proof."
    else:
        status = "ready"
        next_step = "Run draft inspection or Harbor Oracle."

    payload = {
        "schema": "nemo.eval_author.task_close_preflight.v1",
        "status": status,
        "valid": not required_failed,
        "checks": checks,
        "next_step": next_step,
    }
    return (0 if payload["valid"] else 1), payload


def _contains_placeholder(text: str) -> bool:
    """Return whether ``text`` still looks like unfilled scaffold content."""
    return bool(re.search(r"\b(TODO|FIXME|TBD|placeholder|replace me|your solution)\b", text, re.IGNORECASE))


def _looks_like_unconditional_reward(text: str) -> bool:
    """Return whether a verifier appears to award reward 1 without a failure path."""
    writes_reward_one = bool(
        re.search(r"\breward\s*=\s*1\b", text) or re.search(r"\b(?:echo|printf)\b[^\n]*\b1\b[^\n]*reward\.txt", text)
    )
    has_failure_path = bool(
        re.search(r"\breward\s*=\s*0\b", text)
        or re.search(r"\b(?:echo|printf)\b[^\n]*\b0\b[^\n]*reward\.txt", text)
        or re.search(r"\bif\b|\bcase\b", text)
    )
    return writes_reward_one and not has_failure_path


def _load_task_toml(path: Path) -> dict[str, Any]:
    """Load ``task.toml`` as TOML or raise ``CloseError``."""
    try:
        with path.open("rb") as stream:
            payload = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CloseError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CloseError(f"expected TOML table in {path}")
    return payload


def _target_is_actionable(before: dict[str, Any], target: str) -> bool:
    """Return whether ``target`` is an actionable uncovered tool in a before report."""
    for item in before.get("uncovered_items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("name") == target and item.get("kind") == "tool" and item.get("reason") == _ACTIONABLE_REASON:
            return True
    return False


def _inspect_draft(draft: Path, *, target: str, before_report: Path | None = None) -> dict[str, Any]:
    """Inspect one generated Harbor task draft without running it."""
    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "draft_under_eval_author",
            _path_has_parts(draft, _DRAFT_PARTS),
            "draft path must live under .eval-author/task-drafts/",
        )
    )
    checks.append(_check("draft_exists", draft.is_dir(), "draft directory exists"))

    for relative in _REQUIRED_TASK_FILES:
        path = draft / relative
        exists = path.is_file()
        checks.append(_check(f"{relative}:exists", exists, f"{relative} exists"))
        if exists:
            text = _read_text(path)
            checks.append(_check(f"{relative}:nonempty", bool(text.strip()), f"{relative} is not empty"))
            checks.append(
                _check(
                    f"{relative}:no_placeholder",
                    not _contains_placeholder(text),
                    f"{relative} has no obvious scaffold placeholders",
                )
            )

    task_toml = draft / "task.toml"
    if task_toml.is_file():
        try:
            task_config = _load_task_toml(task_toml)
        except CloseError as exc:
            checks.append(_check("task_toml:parse", False, str(exc)))
        else:
            task = task_config.get("task")
            keywords = task.get("keywords") if isinstance(task, dict) else None
            if keywords is None:
                keywords = task_config.get("metadata", {}).get("keywords")
            checks.append(_check("task_toml:task_name", bool(task and task.get("name")), "task.toml names the task"))
            checks.append(
                _check(
                    "task_toml:keywords",
                    isinstance(keywords, list) and bool(keywords),
                    "task.toml carries nonempty keywords or metadata keywords",
                )
            )

    dockerfile = draft / "environment" / "Dockerfile"
    if dockerfile.is_file():
        text = _read_text(dockerfile)
        checks.append(
            _check(
                "dockerfile:from", bool(re.search(r"^\s*FROM\s+\S+", text, re.MULTILINE)), "Dockerfile has a base image"
            )
        )

    verifier = draft / "tests" / "test.sh"
    if verifier.is_file():
        text = _read_text(verifier)
        checks.append(
            _check(
                "verifier:writes_reward",
                "/logs/verifier/reward.txt" in text,
                "verifier writes /logs/verifier/reward.txt",
            )
        )
        checks.append(
            _check(
                "verifier:has_failure_path",
                bool(re.search(r"\breward\s*=\s*0\b", text) or re.search(r"\bif\b|\bcase\b", text)),
                "verifier has an observable failure path",
            )
        )
        checks.append(
            _check(
                "verifier:not_unconditional_reward",
                not _looks_like_unconditional_reward(text),
                "verifier does not appear to award reward 1 unconditionally",
            )
        )

    solution = draft / "solution" / "solve.sh"
    if solution.is_file():
        text = _read_text(solution)
        checks.append(
            _check(
                "solution:executable_hint",
                text.startswith("#!") or "python" in text or "bash" in text,
                "solution is executable or names an executable interpreter",
                severity="advisory",
            )
        )

    if before_report is not None:
        before = _read_json(before_report)
        checks.append(
            _check(
                "before_report:target_actionable",
                _target_is_actionable(before, target),
                f"{target!r} is an actionable uncovered tool in the before report",
            )
        )

    required = [check for check in checks if check["severity"] == "required"]
    required_failed = [check for check in required if not check["passed"]]
    status = "ready_for_oracle" if not required_failed else "needs_repair"
    return {
        "schema": "nemo.eval_author.task_close_inspection.v1",
        "draft": str(draft),
        "target_tool": target,
        "status": status,
        "valid": not required_failed,
        "checks": checks,
        "summary": {
            "required_passed": len(required) - len(required_failed),
            "required_failed": len(required_failed),
            "advisory_failed": sum(1 for check in checks if check["severity"] == "advisory" and not check["passed"]),
        },
    }


def _path_has_parts(path: Path, parts: tuple[str, str]) -> bool:
    """Return whether ``path`` is under a named ``.eval-author`` subdirectory."""
    resolved_parts = path.resolve().parts
    return any(resolved_parts[index : index + 2] == parts for index in range(len(resolved_parts) - 1))


def _run_ids_from_report(report: dict[str, Any], *, report_path: Path) -> list[str]:
    """Return ATIF ``subject.run_id`` values recorded in one aggregate coverage report."""
    input_reports = report.get("input_reports")
    if not isinstance(input_reports, list) or not input_reports:
        raise CloseError(f"after report must include input_reports with subject.run_id: {report_path}")
    run_ids: list[str] = []
    for index, entry in enumerate(input_reports):
        if not isinstance(entry, dict):
            raise CloseError(f"after report input_reports[{index}] must be an object: {report_path}")
        subject = entry.get("subject")
        if not isinstance(subject, dict):
            raise CloseError(f"after report input_reports[{index}] must include subject: {report_path}")
        run_id = subject.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise CloseError(
                f"after report input_reports[{index}].subject.run_id must be a non-empty string: {report_path}"
            )
        run_ids.append(run_id)
    return run_ids


def _coverage_runs(after_paths: list[Path], target: str) -> tuple[list[dict[str, Any]], bool]:
    """Return per-repeat coverage verdicts and whether all repeats cover ``target``."""
    if len(after_paths) < _MIN_AFTER_REPORTS:
        raise CloseError(f"at least {_MIN_AFTER_REPORTS} --after reports are required")
    resolved_paths = [path.resolve() for path in after_paths]
    if len(set(resolved_paths)) != len(resolved_paths):
        raise CloseError("--after reports must be distinct")

    runs: list[dict[str, Any]] = []
    run_ids: list[str] = []
    all_covered = True
    for path in after_paths:
        report = _read_json(path)
        report_run_ids = _run_ids_from_report(report, report_path=path)
        run_ids.extend(report_run_ids)
        covered = target in set(report.get("covered") or [])
        still_uncovered = target in set(report.get("uncovered") or [])
        passed = covered and not still_uncovered
        all_covered = all_covered and passed
        runs.append({"report": str(path), "run_ids": report_run_ids, "covered": covered, "passed": passed})

    if len(set(run_ids)) != len(run_ids):
        raise CloseError("--after reports must come from distinct ATIF subject.run_id values")
    return runs, all_covered


def _rewards_pass(rewards: list[float] | None, threshold: float) -> bool | None:
    """Return whether every provided reward meets ``threshold``; ``None`` means unproven."""
    if rewards is None or not rewards:
        return None
    return all(reward >= threshold for reward in rewards)


def _closure_report(
    *,
    before_path: Path,
    after_paths: list[Path],
    target: str,
    oracle_reward: float | None,
    agent_rewards: list[float] | None,
    reward_threshold: float,
    draft: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Classify one generated task draft from task, reward, and coverage evidence."""
    before = _read_json(before_path)
    target_actionable = _target_is_actionable(before, target)
    runs: list[dict[str, Any]] = []
    coverage_closed = False
    coverage_error = None
    if target_actionable:
        try:
            runs, coverage_closed = _coverage_runs(after_paths, target)
        except CloseError as exc:
            coverage_error = str(exc)

    oracle_passed = None if oracle_reward is None else oracle_reward >= reward_threshold
    agent_passed = _rewards_pass(agent_rewards, reward_threshold)

    inspection = _inspect_draft(draft, target=target, before_report=before_path) if draft is not None else None
    draft_ready = None if inspection is None else bool(inspection["valid"])

    if not target_actionable:
        status = "target_not_actionable"
        next_step = "Regenerate or inspect the before report; the target is not an actionable uncovered tool."
    elif draft_ready is False:
        status = "task_draft_needs_repair"
        next_step = "Repair the generated draft under .eval-author/task-drafts/ and rerun inspection."
    elif oracle_passed is None:
        status = "oracle_unproven"
        next_step = "Run Harbor Oracle and pass --oracle-reward from the observed result."
    elif not oracle_passed:
        status = "oracle_failed"
        next_step = "Repair the task environment, canonical solution, or verifier without weakening the verifier."
    elif coverage_error is not None:
        if coverage_error.startswith("at least"):
            status = "coverage_unproven"
            next_step = "Run and measure at least two distinct real-agent repeats before classifying closure."
        else:
            status = "trajectory_invalid"
            next_step = (
                "Fix the real-agent run or measurement artifact so each after report has a distinct ATIF run_id."
            )
    elif not coverage_closed and agent_passed is True:
        status = "agent_solved_without_target_tool"
        next_step = "Revise the task so success naturally requires the target tool, then rerun both real-agent trials."
    elif not coverage_closed:
        status = "coverage_not_closed"
        next_step = "Inspect trajectories and task design; the target tool was not covered in every repeat."
    else:
        status = "closed"
        next_step = "The generated task draft has evidence-backed coverage closure; promotion is a separate step."

    accepted = status == "closed"
    payload = {
        "schema": "nemo.eval_author.task_close_report.v1",
        "target_tool": target,
        "before": str(before_path),
        "after": [str(path) for path in after_paths],
        "status": status,
        "accepted": accepted,
        "valid": True,
        "failure_reason": None if accepted else status,
        "task_runnable": oracle_passed,
        "draft_ready": draft_ready,
        "oracle": {
            "reward": oracle_reward,
            "threshold": reward_threshold,
            "passed": oracle_passed,
        },
        "real_agent": {
            "rewards": agent_rewards or [],
            "threshold": reward_threshold,
            "passed_task": agent_passed,
        },
        "coverage": {
            "closed": coverage_closed,
            "error": coverage_error,
            "runs": runs,
        },
        "next_step": next_step,
    }
    if inspection is not None:
        payload["inspection"] = inspection
    return (0 if accepted else 1), payload


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="inspect a generated Harbor task draft")
    inspect.add_argument("--draft", type=Path, required=True)
    inspect.add_argument("--target", required=True)
    inspect.add_argument("--before", type=Path)
    inspect.add_argument("--out", type=Path)

    preflight = subparsers.add_parser("preflight", help="check local Harbor and optional Docker availability")
    preflight.add_argument("--require-docker", action="store_true")
    preflight.add_argument("--out", type=Path)

    report = subparsers.add_parser("report", help="classify closure from before/after coverage and reward evidence")
    report.add_argument("--before", type=Path, required=True)
    report.add_argument("--after", type=Path, action="append", required=True)
    report.add_argument("--target", required=True)
    report.add_argument("--draft", type=Path)
    report.add_argument("--oracle-reward", type=float)
    report.add_argument("--agent-reward", type=float, action="append")
    report.add_argument("--reward-threshold", type=float, default=_REWARD_THRESHOLD)
    report.add_argument("--out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one task-close command and print a JSON verdict on stdout."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            payload = _inspect_draft(args.draft, target=args.target, before_report=args.before)
            exit_code = 0 if payload["valid"] else 1
        elif args.command == "preflight":
            exit_code, payload = _preflight(require_docker=args.require_docker)
        else:
            exit_code, payload = _closure_report(
                before_path=args.before,
                after_paths=args.after,
                target=args.target,
                oracle_reward=args.oracle_reward,
                agent_rewards=args.agent_reward,
                reward_threshold=args.reward_threshold,
                draft=args.draft,
            )
        if args.out is not None:
            _write_json(args.out, payload)
    except CloseError as exc:
        payload = {"valid": False, "error": str(exc)}
        exit_code = 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
