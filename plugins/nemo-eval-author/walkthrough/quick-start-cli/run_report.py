# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persist and print walkthrough gap-closing run reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gap_state import GapProgress, draft_is_ready
from harbor_progress import GapPhase
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

RUN_REPORT_SCHEMA = "nemo.eval_author.walkthrough_run.v1"
RUN_JSON_NAME = "walkthrough-run.json"
RUN_LOG_NAME = "walkthrough-run.log"


class WalkthroughGapFailures(Exception):
    """One or more selected gaps did not close successfully."""

    def __init__(self, failed_tools: list[str], *, log_path: Path, json_path: Path) -> None:
        self.failed_tools = failed_tools
        self.log_path = log_path
        self.json_path = json_path
        super().__init__(
            f"Gap closing failed for: {', '.join(failed_tools)}. "
            f"See {log_path.name} and {json_path.name} under .eval-author/."
        )


def run_report_paths(workspace: Path) -> tuple[Path, Path]:
    """Return JSON and text log paths under ``.eval-author/``."""
    eval_author = workspace / ".eval-author"
    return eval_author / RUN_JSON_NAME, eval_author / RUN_LOG_NAME


def _progress_to_dict(progress: GapProgress) -> dict[str, Any]:
    return {
        "tool": progress.tool,
        "task_slug": progress.task_slug,
        "phase": str(progress.phase),
        "detail": progress.detail,
        "completed": progress.completed,
        "total": progress.total,
        "attempt": progress.attempt,
        "trial_index": progress.trial_index,
        "accepted": progress.accepted,
        "error": progress.error,
        "error_log": progress.error_log,
    }


def _draft_status(workspace: Path, task_slug: str) -> dict[str, Any]:
    draft = workspace / ".eval-author" / "task-drafts" / task_slug
    required = (
        "instruction.md",
        "task.toml",
        "solution/solve.sh",
        "tests/test.sh",
    )
    missing = [rel for rel in required if not (draft / rel).is_file()]
    return {
        "draft_path": str(draft.relative_to(workspace)) if draft.exists() else None,
        "ready": draft_is_ready(workspace, task_slug),
        "missing_files": missing,
    }


def reconcile_gap_outcomes(
    gaps: list[GapProgress],
    *,
    fill_tools: list[str],
    complete: bool,
    covered: set[str] | None = None,
) -> list[GapProgress]:
    """Normalize gap progress into terminal accepted/failed states for reporting."""
    covered_tools = covered or set()
    by_tool = {progress.tool: progress for progress in gaps}
    reconciled: list[GapProgress] = []

    for tool in fill_tools:
        progress = by_tool.get(tool)
        if progress is None:
            reconciled.append(
                GapProgress(
                    tool=tool,
                    task_slug="",
                    phase=GapPhase.FAILED,
                    detail="no progress recorded",
                    error="gap closing did not run",
                    accepted=False,
                )
            )
            continue

        row = GapProgress(
            tool=progress.tool,
            task_slug=progress.task_slug,
            phase=progress.phase,
            detail=progress.detail,
            completed=progress.completed,
            total=progress.total,
            attempt=progress.attempt,
            trial_index=progress.trial_index,
            accepted=progress.accepted,
            error=progress.error,
            error_log=progress.error_log,
        )
        if complete or tool in covered_tools:
            row.phase = GapPhase.ACCEPTED
            row.detail = "coverage complete"
            row.accepted = True
            row.error = None
        elif row.phase not in {GapPhase.ACCEPTED, GapPhase.FAILED}:
            row.phase = GapPhase.FAILED
            row.detail = row.detail or "gap closing incomplete"
            row.accepted = False
            row.error = row.error or "agent exited before gap closed"
        reconciled.append(row)

    return reconciled


def build_run_record(
    workspace: Path,
    *,
    mode: str,
    gaps: list[GapProgress],
    fill_tools: list[str],
) -> dict[str, Any]:
    """Build a structured run report payload."""
    accepted = [row.tool for row in gaps if str(row.phase) == GapPhase.ACCEPTED]
    failed = [row.tool for row in gaps if str(row.phase) == GapPhase.FAILED]
    in_progress = [
        row.tool for row in gaps if str(row.phase) not in {GapPhase.ACCEPTED, GapPhase.FAILED, GapPhase.WAITING}
    ]
    gap_entries = []
    for progress in sorted(gaps, key=lambda row: row.tool):
        entry = _progress_to_dict(progress)
        entry["draft"] = _draft_status(workspace, progress.task_slug)
        gap_entries.append(entry)
    return {
        "schema": RUN_REPORT_SCHEMA,
        "finished_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "fill_tools": fill_tools,
        "summary": {
            "accepted": accepted,
            "failed": failed,
            "in_progress": in_progress,
        },
        "gaps": gap_entries,
    }


def _format_text_log(record: dict[str, Any]) -> str:
    lines = [
        "Eval Author walkthrough run report",
        f"finished_at: {record['finished_at']}",
        f"mode: {record['mode']}",
        f"fill_tools: {', '.join(record.get('fill_tools') or []) or '(none)'}",
        "",
        "Summary",
        f"  accepted: {', '.join(record['summary']['accepted']) or '(none)'}",
        f"  failed: {', '.join(record['summary']['failed']) or '(none)'}",
        f"  in_progress: {', '.join(record['summary']['in_progress']) or '(none)'}",
        "",
    ]
    for gap in record.get("gaps") or []:
        lines.extend(
            [
                f"Tool: {gap['tool']} ({gap['task_slug']})",
                f"  phase: {gap['phase']}",
                f"  detail: {gap['detail']}",
            ]
        )
        draft = gap.get("draft") or {}
        if draft.get("ready") is False:
            missing = ", ".join(draft.get("missing_files") or []) or "(unknown)"
            lines.append(f"  draft: incomplete; missing {missing}")
        if gap.get("error"):
            lines.append(f"  error: {gap['error']}")
        if gap.get("error_log"):
            lines.append("  output:")
            for log_line in str(gap["error_log"]).splitlines():
                lines.append(f"    {log_line}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_run_report(
    workspace: Path,
    *,
    mode: str,
    gaps: list[GapProgress],
    fill_tools: list[str],
) -> tuple[Path, Path, dict[str, Any]]:
    """Write JSON and text run logs; return their paths and the record."""
    record = build_run_record(workspace, mode=mode, gaps=gaps, fill_tools=fill_tools)
    json_path, log_path = run_report_paths(workspace)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log_path.write_text(_format_text_log(record), encoding="utf-8")
    return json_path, log_path, record


def build_run_summary_group(
    record: dict[str, Any],
    *,
    json_path: Path,
    log_path: Path,
) -> RenderableType | None:
    """Build a Rich summary panel for the final walkthrough screen."""
    summary = record.get("summary") or {}
    accepted = summary.get("accepted") or []
    failed = summary.get("failed") or []
    if not failed:
        if not accepted:
            return None
        return Panel(
            Group(
                Text(f"Closed gaps: {', '.join(accepted)}", style="bold green"),
                Text(f"Run log: {log_path}", style="dim"),
                Text(f"Structured report: {json_path}", style="dim"),
            ),
            title="[bold green]Walkthrough complete[/]",
            border_style="green",
        )

    table = Table(title="Gap failures", expand=True, show_lines=True)
    table.add_column("Tool", style="bold", no_wrap=True)
    table.add_column("Phase", no_wrap=True)
    table.add_column("Detail")
    table.add_column("Error")

    for gap in record.get("gaps") or []:
        if gap.get("tool") not in failed:
            continue
        error_text = str(gap.get("error") or "")
        error_log = str(gap.get("error_log") or "")
        snippet = error_text or (error_log.splitlines()[-1] if error_log else "")
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        table.add_row(
            str(gap["tool"]),
            Text(str(gap.get("phase") or ""), style="bold red"),
            str(gap.get("detail") or ""),
            snippet or Text("see log", style="dim"),
        )

    return Panel(
        Group(
            table,
            Text(f"Detailed log: {log_path}", style="dim"),
            Text(f"Structured report: {json_path}", style="dim"),
        ),
        title="[bold red]Walkthrough incomplete[/]",
        border_style="red",
    )


def render_run_summary(
    console: Console,
    record: dict[str, Any],
    *,
    json_path: Path,
    log_path: Path,
) -> None:
    """Print a post-run table after the live display exits."""
    panel = build_run_summary_group(record, json_path=json_path, log_path=log_path)
    if panel is not None:
        console.print(panel)


def _failed_tools(record: dict[str, Any]) -> list[str]:
    return list((record.get("summary") or {}).get("failed") or [])


def raise_on_gap_failures(record: dict[str, Any], *, log_path: Path, json_path: Path) -> None:
    """Raise when the run report lists one or more failed gaps."""
    failed = _failed_tools(record)
    if failed:
        raise WalkthroughGapFailures(failed, log_path=log_path, json_path=json_path)


def finalize_gap_run_record(
    workspace: Path,
    gaps: list[GapProgress],
    *,
    mode: str,
    fill_tools: list[str],
    complete: bool,
    covered: set[str] | None = None,
) -> tuple[list[GapProgress], Path, Path, dict[str, Any]]:
    """Reconcile gap outcomes, write run logs, and return paths plus the record."""
    reconciled = reconcile_gap_outcomes(
        gaps,
        fill_tools=fill_tools,
        complete=complete,
        covered=covered,
    )
    json_path, log_path, record = write_run_report(
        workspace,
        mode=mode,
        gaps=reconciled,
        fill_tools=fill_tools,
    )
    return reconciled, json_path, log_path, record


def finalize_gap_run(
    console: Console,
    workspace: Path,
    gaps: list[GapProgress],
    *,
    mode: str,
    fill_tools: list[str],
    complete: bool | None = None,
    covered: set[str] | None = None,
) -> None:
    """Write run logs, print a failure report, and raise when any gap failed."""
    if complete is not None:
        reconciled, json_path, log_path, record = finalize_gap_run_record(
            workspace,
            gaps,
            mode=mode,
            fill_tools=fill_tools,
            complete=complete,
            covered=covered,
        )
    else:
        json_path, log_path, record = write_run_report(
            workspace,
            mode=mode,
            gaps=gaps,
            fill_tools=fill_tools,
        )
    render_run_summary(console, record, json_path=json_path, log_path=log_path)
    raise_on_gap_failures(record, log_path=log_path, json_path=json_path)
