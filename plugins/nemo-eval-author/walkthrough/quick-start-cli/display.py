# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rich console helpers for the Eval Author walkthrough quick-start CLI."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

GAP_FOCUS_BOILERPLATE_RE = re.compile(
    r"^Exercise a scenario where the agent should call [^:]+:\s*",
    re.IGNORECASE,
)
SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def format_gap_focus(focus: str, *, limit: int = 88) -> str:
    """Strip audit report boilerplate and truncate for table display."""
    text = str(focus).strip().replace("\n", " ")
    text = GAP_FOCUS_BOILERPLATE_RE.sub("", text)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Branding for the walkthrough CLI driver."""

    key: str
    title: str
    subtitle: str
    accent: str


PROFILES: dict[str, AgentProfile] = {
    "cursor": AgentProfile(
        key="cursor",
        title="Eval Author Walkthrough",
        subtitle="Demonstrating audit → gap task → verify with Cursor",
        accent="cyan",
    ),
    "claude": AgentProfile(
        key="claude",
        title="Eval Author Walkthrough",
        subtitle="Demonstrating audit → gap task → verify with Claude Code",
        accent="magenta",
    ),
}


def get_profile(agent: str) -> AgentProfile:
    """Return a supported agent profile or raise ``ValueError``."""
    normalized = agent.strip().lower()
    if normalized not in PROFILES:
        supported = ", ".join(sorted(PROFILES))
        raise ValueError(f"unsupported agent {agent!r}; choose one of: {supported}")
    return PROFILES[normalized]


def make_console(profile: AgentProfile) -> Console:
    """Build a console tuned for the selected agent profile."""
    return Console(highlight=False, soft_wrap=True)


def ethos_path_label(workspace_label: str) -> str:
    """Return the workspace-qualified ETHOS path for agent prompts."""
    path = workspace_label.rstrip("/")
    rel = os.environ["ETHOS_REL_PATH"].lstrip("/")
    return f"{path}/{rel}"


def build_nemo_ethos_prompt(fixture_label: str) -> str:
    """Return the nemo-ethos prompt for a fresh walkthrough workspace."""
    path = fixture_label.rstrip("/")
    ethos_path = ethos_path_label(path)
    return (
        f"Use nemo-ethos for {os.environ['AGENT_NAME']} in {path}; explore the cloned source at "
        f"{os.environ['RHO_AGENT_CHECKOUT']}/; write {ethos_path} locally only; do not upload to Filesets."
    )


def build_audit_phase_prompt(fixture_label: str) -> str:
    """Return the eval-author prompt for audit through the coverage report."""
    path = fixture_label.rstrip("/")
    ethos_path = ethos_path_label(path)
    return (
        f"Use eval-author for {path}/ through audit Step 5 only.\n"
        f"Use {ethos_path} as the ethos source.\n"
        "Generate and validate audit.md, run baseline task-0, measure the trial "
        "ATIF, and write .eval-author/audit-coverage-report.json.\n"
        "Do not run task_pipeline.py select or eval-author-task-create yet."
    )


def build_gap_close_prompt(fixture_label: str) -> str:
    """Return the eval-author prompt for closing actionable coverage gaps."""
    path = fixture_label.rstrip("/")
    return f"Close eval coverage gaps for {path}/ via eval-author skill."


def render_banner(console: Console, profile: AgentProfile, workspace: str) -> None:
    """Print the demo header."""
    body = Group(
        Text(profile.subtitle, style=profile.accent),
        Text(f"Workspace: {workspace}", style="dim"),
    )
    console.print(Panel(body, title=f"[bold {profile.accent}]{profile.title}[/]", border_style=profile.accent))
    console.print()


def render_env_checklist(console: Console, profile: AgentProfile, env: Mapping[str, str]) -> None:
    """Show environment variables the coding agent needs for Harbor runs."""
    rows = [
        ("PYTHONPATH", env.get("PYTHONPATH"), "workspace root"),
        (
            "OPENAI_API_KEY",
            "set" if env.get("OPENAI_API_KEY") or env.get("NVIDIA_API_KEY") else None,
            "or NVIDIA_API_KEY",
        ),
        (
            "OPENAI_BASE_URL",
            env.get("OPENAI_BASE_URL", "https://inference-api.nvidia.com/v1"),
            "inference gateway",
        ),
        (
            "RHO_AGENT_MODEL",
            env.get("RHO_AGENT_MODEL"),
            "rho-agent Harbor trials",
        ),
    ]
    table = Table(title="Environment", expand=True)
    table.add_column("Variable", style="bold", no_wrap=True)
    table.add_column("Value")
    table.add_column("Notes", style="dim")

    for name, value, notes in rows:
        if value is None:
            table.add_row(name, Text("missing", style="bold red"), notes)
        else:
            table.add_row(name, value, notes)

    console.print(table)
    console.print()


def infer_active_workspace_artifact(state: Mapping[str, Any]) -> str | None:
    """Return the workspace artifact key currently being worked on, if any."""
    if state.get("complete") or not state.get("watch_active", True):
        return None
    if not state.get("ethos"):
        return "ethos"
    if not state.get("audit_items"):
        return "audit"
    if not state.get("coverage_report"):
        return "coverage_report"

    gap_progress = state.get("gap_progress") or []
    if gap_progress:
        terminal = {"accepted", "failed"}
        if any(
            str(getattr(row, "phase", row.get("phase") if isinstance(row, dict) else "")) not in terminal
            for row in gap_progress
        ):
            return "task_drafts"

    fill_tools = state.get("fill_tools") or []
    task_drafts = state.get("task_drafts") or []
    if fill_tools:
        if len(task_drafts) < len(fill_tools):
            return "task_drafts"
        if gap_progress:
            return "task_drafts"

    return None


def _artifact_label(artifact: str, key: str, *, active_key: str | None, pulse: int) -> Text:
    if key != active_key:
        return Text(artifact)
    frame = SPINNER_FRAMES[pulse % len(SPINNER_FRAMES)]
    return Text.assemble((frame + " ", "cyan"), (artifact, "bold cyan"))


def _artifact_state(status: str, *, active: bool) -> Text | str:
    if active:
        return Text("in progress", style="bold cyan")
    if status == "missing":
        return Text("missing", style="dim")
    return status


def build_workspace_status_table(
    profile: AgentProfile,
    workspace: Path,
    state: dict[str, Any],
    *,
    pulse: int = 0,
) -> Group:
    """Return workspace status renderables for live refresh."""
    active_key = infer_active_workspace_artifact(state)
    rows = [
        ("ethos", os.environ["ETHOS_REL_PATH"], "present" if state.get("ethos") else "missing", "nemo-ethos"),
        (
            "audit",
            ".eval-author/audit.md",
            "present" if state.get("audit_items") else "missing",
            "eval-author-audit",
        ),
        (
            "coverage_report",
            ".eval-author/audit-coverage-report.json",
            "present" if state.get("coverage_report") else "missing",
            "eval-author-audit Step 5",
        ),
        (
            "task_drafts",
            "task drafts",
            ", ".join(state.get("task_drafts") or []) or "(none)",
            "eval-author-task-create",
        ),
    ]
    table = Table(title="Workspace activity", expand=True)
    table.add_column("Artifact", style="bold", no_wrap=True)
    table.add_column("State")
    table.add_column("Owner", style="dim")

    for key, artifact, status, owner in rows:
        active = key == active_key
        table.add_row(
            _artifact_label(artifact, key, active_key=active_key, pulse=pulse),
            _artifact_state(status, active=active),
            owner,
        )

    return Group(
        Rule(f"[bold {profile.accent}]Workspace[/]", style=profile.accent),
        Text(str(workspace), style="dim"),
        table,
    )


def render_step(console: Console, profile: AgentProfile, title: str, detail: str = "") -> None:
    """Print a section heading."""
    console.print(Rule(f"[bold {profile.accent}]{title}[/]", style=profile.accent))
    if detail:
        console.print(Text(detail, style="dim"))
        console.print()


def build_audit_table(items: Sequence[dict[str, Any]]) -> Table:
    """Build the finite audit denominator table."""
    table = Table(title="Audit denominator", show_lines=False, expand=True)
    table.add_column("Kind", style="bold", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Description")

    for item in sorted(items, key=lambda row: (row["kind"], row["name"])):
        description = str(item.get("description", "")).strip().replace("\n", " ")
        if len(description) > 96:
            description = description[:93] + "..."
        table.add_row(str(item["kind"]), str(item["name"]), description)
    return table


def _coverage_status(
    kind: str,
    name: str,
    covered: set[str],
    measured_kinds: set[str],
) -> Text:
    if kind not in measured_kinds:
        return Text("not measured", style="dim italic")
    if name in covered:
        return Text("covered", style="bold green")
    return Text("uncovered", style="bold red")


def build_coverage_table(
    items: Sequence[dict[str, Any]],
    *,
    covered: Iterable[str],
    measured_kinds: Iterable[str],
) -> Table:
    """Build coverage state table for each audit item."""
    covered_set = set(covered)
    measured_set = set(measured_kinds)
    table = Table(title="Coverage", show_lines=False, expand=True)
    table.add_column("Kind", style="bold", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Status", no_wrap=True)

    for item in sorted(items, key=lambda row: (row["kind"], row["name"])):
        kind = str(item["kind"])
        name = str(item["name"])
        table.add_row(
            kind,
            name,
            _coverage_status(kind, name, covered_set, measured_set),
        )
    return table


def build_gap_list_renderable(
    gaps: Sequence[dict[str, Any]],
) -> RenderableType:
    """Return actionable tool gaps or a short completion message."""
    if not gaps:
        return Text("No actionable tool gaps remain.", style="bold green")

    table = Table(title="Actionable gaps", expand=True)
    table.add_column("Tool", style="bold", no_wrap=True)
    table.add_column("Task slug", no_wrap=True)
    table.add_column("Focus")

    for gap in gaps:
        tool = str(gap["name"])
        focus = format_gap_focus(gap.get("focus", ""))
        table.add_row(Text(tool, style="bold red"), str(gap["task_slug"]), focus)

    return table


def _phase_style(phase: str) -> str:
    if phase in {"accepted", "complete"}:
        return "bold green"
    if phase in {"failed"}:
        return "bold red"
    if phase in {"retry"}:
        return "bold magenta"
    if phase in {"oracle", "trial-1", "trial-2", "measure", "verify"}:
        return "bold yellow"
    return "dim"


def _format_progress(row: Any) -> str:
    phase = str(getattr(row, "phase", row.get("phase") if isinstance(row, dict) else "waiting"))
    completed = int(getattr(row, "completed", row.get("completed", 0) if isinstance(row, dict) else 0))
    total = int(getattr(row, "total", row.get("total", 0) if isinstance(row, dict) else 0))
    attempt = int(getattr(row, "attempt", row.get("attempt", 1) if isinstance(row, dict) else 1))
    trial_index = int(getattr(row, "trial_index", row.get("trial_index", 0) if isinstance(row, dict) else 0))

    if phase == "oracle":
        return f"oracle{' (retry)' if attempt > 1 else ''}"
    if phase == "trial-1":
        return f"run 1/{total or 2}"
    if phase == "trial-2":
        if total > 0 and completed >= total:
            return f"runs {total}/{total}"
        if trial_index:
            return f"run {trial_index}/{total or 2}"
        return f"run 2/{total or 2}"
    if phase == "measure" and total > 0:
        return f"measure {completed + 1}/{total}" if completed < total else f"measure {total}/{total}"
    if phase == "retry":
        return f"retry {attempt}"
    if total > 0:
        return f"{completed}/{total}"
    if phase in {"oracle", "trial-1", "trial-2", "measure", "verify", "retry"}:
        return "…"
    return "—"


def build_gap_progress_table(progress_rows: Sequence[Any]) -> Table:
    """Show per-gap activity with optional numeric progress."""
    table = Table(title="Gap progress", expand=True)
    table.add_column("Tool", style="bold", no_wrap=True)
    table.add_column("Phase", no_wrap=True)
    table.add_column("Activity")
    table.add_column("Progress", no_wrap=True)

    for row in progress_rows:
        tool = str(getattr(row, "tool", row.get("tool") if isinstance(row, dict) else ""))
        phase = str(getattr(row, "phase", row.get("phase") if isinstance(row, dict) else "waiting"))
        detail = str(getattr(row, "detail", row.get("detail") if isinstance(row, dict) else ""))
        table.add_row(tool, Text(phase, style=_phase_style(phase)), detail, _format_progress(row))
    return table


def build_activity_progress(*, label: str, completed: int, total: int) -> Progress:
    """Return a compact Rich progress bar for one in-flight Harbor activity."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=24),
        TextColumn("{task.completed}/{task.total}"),
        expand=True,
    )
    task_id = progress.add_task(label, total=max(total, 1), completed=min(completed, total))
    progress.tasks[task_id].description = label
    return progress


def build_workspace_activity_group(
    profile: AgentProfile,
    workspace: Path,
    state: dict[str, Any],
    *,
    pulse: int = 0,
) -> Group:
    """Compose workspace tables for live refresh without scrolling the terminal."""
    parts: list[RenderableType] = [
        build_workspace_status_table(profile, workspace, state, pulse=pulse),
    ]

    harbor_activity = state.get("harbor_activity")
    if isinstance(harbor_activity, dict):
        label = str(harbor_activity.get("label") or "Harbor")
        completed = int(harbor_activity.get("completed") or 0)
        total = int(harbor_activity.get("total") or 0)
        phase = str(harbor_activity.get("phase") or "")
        if harbor_activity.get("active") or total > 0:
            if phase == "oracle":
                label = "Oracle"
            elif phase == "trial-1":
                label = f"Harbor run 1/{total or 2}"
            elif phase == "trial-2":
                label = label if label.startswith("rho-agent") else f"Harbor run 2/{total or 2}"
            elif phase == "retry":
                attempt = int(harbor_activity.get("attempt") or 1)
                label = f"Retry {attempt}: {label}"
            parts.append(build_activity_progress(label=label, completed=completed, total=max(total, 1)))

    audit_items = state.get("audit_items") or []
    gap_closing = bool(state.get("fill_tools") or state.get("gap_progress"))
    if audit_items and not gap_closing:
        parts.append(build_audit_table(audit_items))

    report = state.get("coverage_report")
    if isinstance(report, dict) and audit_items:
        parts.append(
            build_coverage_table(
                audit_items,
                covered=report.get("covered", []),
                measured_kinds=report.get("measured_kinds", ["tool"]),
            )
        )
        parts.append(build_gap_list_renderable(state.get("actionable_gaps") or []))

    gap_progress = state.get("gap_progress") or []
    if gap_progress:
        parts.append(build_gap_progress_table(gap_progress))

    if state.get("complete"):
        covered = list((report or {}).get("covered") or [])
        parts.append(
            Panel(
                Group(
                    Text("Coverage complete", style="bold green"),
                    Text(f"Covered tools: {', '.join(sorted(covered)) or '(none)'}"),
                ),
                title="Result",
                border_style=profile.accent,
            )
        )
    return Group(*parts)
