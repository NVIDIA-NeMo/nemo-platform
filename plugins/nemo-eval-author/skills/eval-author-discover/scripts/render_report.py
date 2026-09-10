#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render a human-friendly discovery report from discover.py JSON."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def render_report(report: dict[str, Any]) -> str:
    """Return the Markdown saved at .eval-author/discovery.md."""
    proven = bool(report.get("proven"))
    runnable = bool(report.get("runnable"))
    configs = report.get("configs") if isinstance(report.get("configs"), list) else []
    run_command = report.get("run_command")
    task_count = report.get("task_count", 0)
    dataset_count = len(report.get("dataset_paths") or [])

    if not proven:
        lines: list[str] = [
            "# Eval Discovery",
            "",
            "I found possible Harbor evals, but I could not prove whether they run.",
            "",
        ]
    elif runnable:
        lines = [
            "# Eval Discovery",
            "",
            "This repo has Harbor evals, and they are ready to run.",
            "",
        ]
    else:
        blocker_names = ", ".join(f"`{check.get('name', 'unknown')}`" for check in _required_failures(report))
        blocker_summary = f" The current blocker is {blocker_names}." if blocker_names else ""
        lines = [
            "# Eval Discovery",
            "",
            f"This repo has Harbor evals, but they are not ready to run yet.{blocker_summary}",
            "",
        ]

    lines.extend(
        [
            "## At A Glance",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Evals found | {_evals_found(configs, task_count, dataset_count)} |",
            f"| Can I run them now? | {_run_verdict(proven, runnable)} |",
            f"| Job configs | {_config_paths(configs)} |",
            f"| Task directories | {task_count} |",
            f"| Dataset directories | {dataset_count} |",
            f"| Run command | {_code(run_command) if run_command else 'None yet'} |",
            "",
            "## What To Do Next",
            "",
        ]
    )

    if not proven:
        lines.append(
            "Rerun discovery with the Python interpreter for this eval suite, where `import harbor` works. "
            "Until then, treat the config and task counts as a map of what was found, not proof that the suite runs."
        )
    elif runnable and run_command:
        lines.extend(["Run the evals with:", "", "```bash", str(run_command), "```"])
    elif runnable:
        lines.append(
            "Each discovered config is ready. Pick the config you want to run, then start Harbor with that config."
        )
    else:
        failures = _required_failures(report)
        if failures:
            lines.append("Fix the blocker below, then rerun discovery before starting the evals:")
            lines.append("")
            lines.extend(_check_bullets(failures))
        else:
            lines.append(
                "Discovery did not find a runnable config. Check whether the eval config is deeper than four directories or uses a nonstandard layout."
            )

    lines.extend(["", "## Configs", ""])
    if configs:
        for config in configs:
            lines.extend(_config_section(config))
    else:
        lines.append("No repository-owned Harbor configs were found.")
        lines.append("")

    advisories = _advisories(report)
    lines.extend(["## Advisories", ""])
    if advisories:
        lines.extend(_check_bullets(advisories))
    else:
        lines.append("None.")
    lines.extend(["", "## Evidence JSON", "", "```json", json.dumps(report, indent=2), "```", ""])
    return "\n".join(lines)


def _config_section(config: dict[str, Any]) -> list[str]:
    path = config.get("path") or config.get("name") or "unknown config"
    required_env_vars = config.get("required_env_vars") if isinstance(config.get("required_env_vars"), list) else []
    failures = [
        check
        for check in config.get("checks") or []
        if check.get("status") == "fail" and check.get("severity") == "required"
    ]
    lines = [
        f"### `{path}`",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Runnable | {_yes_no(bool(config.get('runnable')))} |",
        f"| Required host variables | {_env_vars(required_env_vars)} |",
        "",
    ]
    if failures:
        lines.extend(["Required failures:", "", *_check_bullets(failures)])
    else:
        lines.append("No required failures.")
    lines.append("")
    return lines


def _required_failures(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        check
        for check in report.get("checks") or []
        if check.get("status") == "fail" and check.get("severity") == "required"
    ]


def _advisories(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        check
        for check in report.get("checks") or []
        if check.get("severity") == "advisory" and check.get("status") in {"warn", "fail"}
    ]


def _check_bullets(checks: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for check in checks:
        lines.append(f"- `{check.get('name', 'unknown')}`: {check.get('message', '')}")
        if check.get("hint"):
            lines.append(f"  Hint: {check['hint']}")
    return lines


def _env_vars(required_env_vars: list[dict[str, Any]]) -> str:
    names = [str(item.get("name")) for item in required_env_vars if item.get("name")]
    return ", ".join(f"`{name}`" for name in names) if names else "None"


def _evals_found(configs: list[dict[str, Any]], task_count: object, dataset_count: int) -> str:
    return "Yes" if configs or task_count or dataset_count else "No"


def _run_verdict(proven: bool, runnable: bool) -> str:
    if not proven:
        return "Unknown"
    return "Yes" if runnable else "No"


def _config_paths(configs: list[dict[str, Any]]) -> str:
    paths = [
        str(config.get("path") or config.get("name")) for config in configs if config.get("path") or config.get("name")
    ]
    return ", ".join(f"`{path}`" for path in paths) if paths else "None found"


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _code(value: object) -> str:
    return f"`{value}`"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render discover.py JSON as a human-friendly Markdown report.")
    parser.add_argument("report", nargs="?", help="Path to discover.py JSON. Reads stdin when omitted.")
    args = parser.parse_args(argv)
    text = open(args.report, encoding="utf-8").read() if args.report else sys.stdin.read()
    sys.stdout.write(render_report(json.loads(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
