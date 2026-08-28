# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare the rho-agent walkthrough workspace and run the quick-start CLI flow."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from display import (
    AgentProfile,
    build_audit_phase_prompt,
    build_gap_close_prompt,
    build_nemo_ethos_prompt,
    build_workspace_activity_group,
    ethos_path_label,
    make_console,
    render_banner,
    render_env_checklist,
    render_step,
)
from gap_state import infer_gap_progress
from harbor_progress import HarborProgressTracker, parse_harbor_trial_line
from interrupts import WalkthroughInterrupted, interruptible_sleep, terminate_agent
from live_display import WalkthroughLiveDisplay
from rich.console import Group
from run_report import (
    build_run_summary_group,
    finalize_gap_run_record,
    raise_on_gap_failures,
)

from agents import AgentCliError, AgentProcess, agent_env, start_agent

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_ROOT.parents[1]
AUDIT_SCRIPTS = PLUGIN_ROOT / "skills" / "eval-author-audit" / "scripts" / "audit_spec"
TASK_SCRIPT = PLUGIN_ROOT / "skills" / "eval-author-task-create" / "scripts" / "task_pipeline.py"
WALKTHROUGH_ADAPTERS = PLUGIN_ROOT / "walkthrough" / "rho-agent"
WALKTHROUGH_ASSETS = PLUGIN_ROOT / "walkthrough" / "assets" / "rho-agent"
DEFAULT_WORKSPACE = Path("tmp/rho-agent-walkthrough")
WATCH_INTERVAL_SEC = 1.0
AGENT_OUTPUT_DRAIN_LIMIT = 3


ARTIFACTS_KEPT_MESSAGE = (
    "Keeping existing walkthrough artifacts. Re-run and choose to remove them when prompted to start fresh."
)


def _agent_runtime_env(profile: AgentProfile, workspace: Path) -> dict[str, str]:
    """Environment for the coding agent and Harbor jobs it launches."""
    env = agent_env(profile, workspace)
    env.setdefault("RHO_AGENT_MODEL", os.environ["DEFAULT_RHO_AGENT_MODEL"])
    return env


@dataclass(slots=True)
class WalkthroughConfig:
    """Runtime options for one walkthrough CLI invocation."""

    workspace: Path
    workspace_label: str
    profile: AgentProfile
    interactive: bool = True


class WalkthroughError(RuntimeError):
    """Raised when workspace preparation fails."""


class WalkthroughArtifactsKept(WalkthroughError):
    """The operator chose to keep existing walkthrough artifacts."""


def _raise_interrupted(*, agent: AgentProcess | None = None, phase: str | None = None) -> None:
    terminate_agent(agent)
    raise WalkthroughInterrupted(phase=phase)


def _run_json(command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise WalkthroughError(message)
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise WalkthroughError("expected JSON object from helper script")
    return payload


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _load_audit_items(audit_path: Path) -> list[dict[str, Any]]:
    sys.path.insert(0, str(AUDIT_SCRIPTS))
    from _markdown import extract_schema_block  # noqa: PLC0415

    block = extract_schema_block(audit_path)
    payload = yaml.safe_load(block)
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise WalkthroughError("audit items must be a list")
    return items


def _load_coverage_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WalkthroughError(f"invalid coverage report: {path}")
    return payload


def _list_actionable_gaps(
    workspace: Path,
    report_path: Path,
) -> list[dict[str, Any]]:
    command = [
        "uv",
        "run",
        str(TASK_SCRIPT),
        "select",
        "--report",
        str(report_path.relative_to(workspace)),
    ]
    payload = _run_json(command, cwd=workspace)
    gaps = payload.get("actionable_tools", [])
    if not isinstance(gaps, list):
        raise WalkthroughError("select returned invalid actionable_tools")
    return gaps


def _ensure_rho_agent_checkout(workspace: Path) -> None:
    """Clone pinned rho-agent source when the walkthrough workspace is missing it."""
    if str(WALKTHROUGH_ADAPTERS) not in sys.path:
        sys.path.insert(0, str(WALKTHROUGH_ADAPTERS))
    from prepare_sandbox import clone_rho_agent  # noqa: PLC0415

    clone_rho_agent(workspace)


def _copy_walkthrough_harbor_assets(workspace: Path) -> None:
    """Copy bundled baseline task and Harbor job config into the workspace."""
    source_task = WALKTHROUGH_ASSETS / "task-0"
    if not source_task.is_dir():
        raise WalkthroughError(f"walkthrough missing bundled task-0 at {source_task}")

    sandbox_task = workspace / ".eval-author" / "sandbox" / "task-0"
    if sandbox_task.exists():
        shutil.rmtree(sandbox_task)
    shutil.copytree(
        source_task,
        sandbox_task,
        ignore=shutil.ignore_patterns("Dockerfile.legacy"),
    )
    (sandbox_task / "tests" / "test.sh").chmod(0o755)
    (sandbox_task / "solution" / "solve.sh").chmod(0o755)
    _copy_file(WALKTHROUGH_ASSETS / "baseline-job.yaml", workspace / ".eval-author" / "baseline-job.yaml")


def _ethos_path(workspace: Path) -> Path:
    return workspace / os.environ["ETHOS_REL_PATH"]


def _walkthrough_artifact_paths(workspace: Path) -> list[Path]:
    paths: list[Path] = []
    ethos = _ethos_path(workspace)
    if ethos.exists():
        paths.append(ethos)
    eval_author = workspace / ".eval-author"
    if eval_author.exists():
        paths.append(eval_author)
    return paths


def _format_walkthrough_artifact_list(workspace: Path, existing: Sequence[Path]) -> str:
    labels = sorted(
        f"{path.relative_to(workspace).as_posix()}/" if path.is_dir() else path.relative_to(workspace).as_posix()
        for path in existing
    )
    bullet_list = "\n".join(f"  - {label}" for label in labels)
    return f"Workspace already contains walkthrough artifacts:\n{bullet_list}"


def _remove_walkthrough_artifacts(existing: Sequence[Path]) -> None:
    for path in existing:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def ensure_walkthrough_workspace(
    workspace: Path,
    *,
    interactive: bool = True,
    console: Any | None = None,
) -> None:
    """Prompt to remove prior walkthrough artifacts, or abort."""
    existing = _walkthrough_artifact_paths(workspace)
    if not existing:
        return

    artifact_message = _format_walkthrough_artifact_list(workspace, existing)

    if interactive and sys.stdin.isatty():
        from rich.prompt import Confirm  # noqa: PLC0415

        if console is not None:
            console.print(artifact_message)
            console.print(
                "[dim]Yes removes the artifacts above and continues. No exits without changing the workspace.[/]",
            )
        else:
            print(artifact_message)
            print("Yes removes the artifacts above and continues. No exits without changing the workspace.")
        try:
            if Confirm.ask("Remove these artifacts and start over?", default=True, console=console):
                _remove_walkthrough_artifacts(existing)
                return
            raise WalkthroughArtifactsKept(ARTIFACTS_KEPT_MESSAGE)
        except KeyboardInterrupt:
            raise WalkthroughInterrupted(phase="artifact cleanup") from None

    raise WalkthroughError(artifact_message)


def prepare_workspace(config: WalkthroughConfig, *, console: Any | None = None) -> None:
    """Copy Harbor adapters and bundled baseline task assets into the workspace."""
    workspace = config.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    ensure_walkthrough_workspace(
        workspace,
        interactive=config.interactive,
        console=console,
    )

    for name in ("rho_harbor_agent.py", "rho_atif_compat.py"):
        target = workspace / name
        if not target.exists():
            _copy_file(WALKTHROUGH_ADAPTERS / name, target)

    _ensure_rho_agent_checkout(workspace)
    _copy_walkthrough_harbor_assets(workspace)


def _workspace_snapshot(
    workspace: Path,
    *,
    fill_gaps: list[dict[str, Any]] | None = None,
    harbor_activity: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return a change token and a renderable workspace state."""
    paths = [
        _ethos_path(workspace),
        workspace / ".eval-author" / "audit.md",
        workspace / ".eval-author" / "audit-coverage-report.json",
    ]
    token_parts: list[str] = []
    for path in paths:
        if path.is_file():
            token_parts.append(f"{path}:{path.stat().st_mtime_ns}:{path.stat().st_size}")

    drafts = workspace / ".eval-author" / "task-drafts"
    if drafts.is_dir():
        for path in sorted(drafts.rglob("*")):
            if path.is_file():
                rel = path.relative_to(workspace)
                token_parts.append(f"{rel}:{path.stat().st_mtime_ns}")

    measurements = workspace / ".eval-author" / "task-measurements"
    if measurements.is_dir():
        for path in sorted(measurements.rglob("coverage.json")):
            rel = path.relative_to(workspace)
            token_parts.append(f"{rel}:{path.stat().st_mtime_ns}")

    fill_tools = [str(gap["name"]) for gap in fill_gaps] if fill_gaps else []

    state: dict[str, Any] = {
        "ethos": _ethos_path(workspace).is_file(),
        "audit_items": [],
        "coverage_report": None,
        "actionable_gaps": [],
        "task_drafts": [],
        "fill_tools": fill_tools,
        "gap_progress": [],
        "harbor_activity": harbor_activity,
        "watch_active": True,
        "complete": False,
    }

    if fill_gaps:
        state["gap_progress"] = [
            infer_gap_progress(workspace, str(gap["name"]), str(gap["task_slug"])) for gap in fill_gaps
        ]
        for progress in state["gap_progress"]:
            token_parts.append(
                f"gap:{progress.tool}:{progress.phase}:{progress.completed}:{progress.total}:"
                f"{progress.attempt}:{progress.trial_index}:{progress.detail}"
            )

    audit_path = workspace / ".eval-author" / "audit.md"
    if audit_path.is_file():
        try:
            state["audit_items"] = _load_audit_items(audit_path)
        except (WalkthroughError, OSError, yaml.YAMLError):
            state["audit_items"] = []

    report_path = workspace / ".eval-author" / "audit-coverage-report.json"
    if report_path.is_file():
        try:
            state["coverage_report"] = _load_coverage_report(report_path)
            state["actionable_gaps"] = _list_actionable_gaps(workspace, report_path)
            covered = set(state["coverage_report"].get("covered") or [])
            if not state["actionable_gaps"]:
                if fill_tools:
                    state["complete"] = {str(name) for name in fill_tools}.issubset(covered)
                elif state["audit_items"]:
                    tool_names = {str(item["name"]) for item in state["audit_items"] if item.get("kind") == "tool"}
                    state["complete"] = tool_names.issubset(covered)
        except (WalkthroughError, OSError, json.JSONDecodeError):
            state["coverage_report"] = None

    if drafts.is_dir():
        state["task_drafts"] = sorted(path.name for path in drafts.iterdir() if path.is_dir())

    return "|".join(token_parts), state


def _render_workspace_activity(
    live: WalkthroughLiveDisplay,
    profile: AgentProfile,
    workspace: Path,
    state: dict[str, Any],
) -> None:
    live.set_main(build_workspace_activity_group(profile, workspace, state, pulse=live.pulse))


def _live_watch_loop(
    live: WalkthroughLiveDisplay,
    profile: AgentProfile,
    workspace: Path,
    *,
    agent: AgentProcess | None = None,
    agent_exit_reported: bool = False,
    fill_gaps: list[dict[str, Any]] | None = None,
    harbor_activity: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """One live-display iteration; returns updated exit flag and workspace state."""
    agent_exit_reported = _poll_agent(
        agent,
        live,
        agent_exit_reported=agent_exit_reported,
        harbor_activity=harbor_activity,
    )
    _token, state = _workspace_snapshot(
        workspace,
        fill_gaps=fill_gaps,
        harbor_activity=harbor_activity,
    )
    state["watch_active"] = agent is not None and not agent_exit_reported
    _render_workspace_activity(live, profile, workspace, state)
    live.touch()
    return agent_exit_reported, state


def _poll_agent(
    agent: AgentProcess | None,
    live: WalkthroughLiveDisplay,
    *,
    agent_exit_reported: bool,
    harbor_activity: dict[str, Any] | None = None,
) -> bool:
    if agent is None:
        return agent_exit_reported

    prefix = f"[cyan]{agent.label}:[/] "
    if agent.activity is not None:
        live.set_agent_activity(agent.activity.status)
    for event in agent.drain_activity(AGENT_OUTPUT_DRAIN_LIMIT):
        live.extend_agent([f"{prefix}{event}"])
    drained = agent.drain(AGENT_OUTPUT_DRAIN_LIMIT)
    if harbor_activity is not None:
        tracker = harbor_activity.get("_tracker")
        if not isinstance(tracker, HarborProgressTracker):
            tracker = HarborProgressTracker()
            harbor_activity["_tracker"] = tracker
        for line in drained:
            update = tracker.feed_line(line)
            if update is not None:
                harbor_activity["active"] = True
                harbor_activity["phase"] = str(update.phase)
                harbor_activity["label"] = update.detail
                harbor_activity["completed"] = update.completed
                harbor_activity["total"] = update.total
                harbor_activity["attempt"] = update.attempt
                continue
            parsed = parse_harbor_trial_line(line)
            if parsed is not None:
                completed, total = parsed
                harbor_activity["active"] = True
                harbor_activity["completed"] = completed
                harbor_activity["total"] = total
                if total <= 1:
                    harbor_activity["phase"] = "oracle"
                    harbor_activity["label"] = "oracle"
                elif completed <= 0:
                    harbor_activity["phase"] = "trial-1"
                    harbor_activity["label"] = f"rho-agent run 1/{total}"
                elif completed < total:
                    harbor_activity["phase"] = "trial-2"
                    harbor_activity["label"] = f"rho-agent run {completed + 1}/{total}"
                else:
                    harbor_activity["phase"] = "trial-2"
                    harbor_activity["label"] = f"rho-agent runs {total}/{total} done"
    if agent.activity is None:
        live.extend_agent(f"{prefix}{line}" for line in drained)

    if agent.done() and not agent_exit_reported:
        live.set_agent_activity(None)
        if agent.returncode == 0:
            live.append_agent(f"[dim]{agent.label} exited.[/]")
        else:
            live.append_agent(f"[yellow]Warning:[/] {agent.label} exited with code {agent.returncode}.")
            for line in agent.recent_lines(5):
                live.append_agent(f"[dim]{agent.label}:[/] {line}")
        return True
    return agent_exit_reported


def watch_until_ethos(
    console: Any,
    profile: AgentProfile,
    workspace: Path,
    *,
    agent: AgentProcess | None = None,
) -> None:
    """Poll until workspace ETHOS.md exists, then stop the ethos agent."""
    render_step(
        console,
        profile,
        "Ethos phase",
        "Workspace tables refresh above; agent activity scrolls in the bottom panel.",
    )
    agent_label = agent.label if agent is not None else profile.key
    agent_exit_reported = False
    try:
        with WalkthroughLiveDisplay(console, profile, agent_label=agent_label) as live:
            while True:
                agent_exit_reported, state = _live_watch_loop(
                    live,
                    profile,
                    workspace,
                    agent=agent,
                    agent_exit_reported=agent_exit_reported,
                )
                if state.get("ethos"):
                    if agent is not None:
                        agent.terminate()
                    return
                interruptible_sleep(WATCH_INTERVAL_SEC)
    except KeyboardInterrupt:
        _raise_interrupted(agent=agent, phase="ethos phase")


def watch_until_coverage_report(
    console: Any,
    profile: AgentProfile,
    workspace: Path,
    *,
    agent: AgentProcess | None = None,
) -> dict[str, Any]:
    """Poll until the aggregate coverage report exists, then stop the audit agent."""
    render_step(
        console,
        profile,
        "Audit phase",
        f"Workspace tables refresh above; {profile.key} activity scrolls in the bottom panel.",
    )
    agent_label = agent.label if agent is not None else profile.key
    agent_exit_reported = False
    try:
        with WalkthroughLiveDisplay(console, profile, agent_label=agent_label) as live:
            while True:
                agent_exit_reported, state = _live_watch_loop(
                    live,
                    profile,
                    workspace,
                    agent=agent,
                    agent_exit_reported=agent_exit_reported,
                )
                if state.get("coverage_report") is not None:
                    if agent is not None:
                        agent.terminate()
                    return state
                interruptible_sleep(WATCH_INTERVAL_SEC)
    except KeyboardInterrupt:
        _raise_interrupted(agent=agent, phase="audit phase")


def _present_gap_closing_finish(
    live: WalkthroughLiveDisplay,
    profile: AgentProfile,
    workspace: Path,
    state: dict[str, Any],
    *,
    fill_tools: list[str],
    selected_gaps: list[dict[str, Any]],
    interactive: bool,
) -> None:
    """Render the final workspace view and run summary inside the live TUI."""
    gap_progress = state.get("gap_progress")
    if not gap_progress:
        gap_progress = [infer_gap_progress(workspace, str(gap["name"]), str(gap["task_slug"])) for gap in selected_gaps]
    complete = bool(state.get("complete"))
    covered = set((state.get("coverage_report") or {}).get("covered") or [])
    _token, refreshed = _workspace_snapshot(workspace, fill_gaps=selected_gaps)
    display_state = {**refreshed, "complete": complete}
    reconciled, json_path, log_path, record = finalize_gap_run_record(
        workspace,
        gap_progress,
        mode="sequential",
        fill_tools=fill_tools,
        complete=complete,
        covered=covered,
    )

    final_state = {
        **display_state,
        "watch_active": False,
        "complete": complete,
        "gap_progress": reconciled,
        "harbor_activity": None,
    }
    workspace_view = build_workspace_activity_group(profile, workspace, final_state, pulse=live.pulse)
    summary = build_run_summary_group(record, json_path=json_path, log_path=log_path)
    main = Group(workspace_view, summary) if summary is not None else workspace_view
    live.set_main(main)
    live.set_agent_activity(None)
    if interactive:
        live.hold_until_enter()

    raise_on_gap_failures(record, log_path=log_path, json_path=json_path)


def watch_workspace(
    console: Any,
    profile: AgentProfile,
    workspace: Path,
    *,
    agent: AgentProcess | None = None,
    fill_gaps: list[dict[str, Any]] | None = None,
    fill_tools: list[str] | None = None,
    interactive: bool = True,
) -> dict[str, Any]:
    """Poll workspace artifacts and render Rich updates while the coding agent works."""
    render_step(
        console,
        profile,
        "Watching workspace",
        "Workspace tables refresh in place; agent activity and Harbor progress update live.",
    )
    agent_label = agent.label if agent is not None else profile.key
    agent_exit_reported = False
    harbor_activity: dict[str, Any] = {
        "active": False,
        "completed": 0,
        "total": 0,
        "label": "Harbor",
        "phase": "",
        "attempt": 1,
        "_tracker": HarborProgressTracker(),
    }
    try:
        with WalkthroughLiveDisplay(console, profile, agent_label=agent_label) as live:
            final_state: dict[str, Any] = {}
            while True:
                agent_exit_reported, state = _live_watch_loop(
                    live,
                    profile,
                    workspace,
                    agent=agent,
                    agent_exit_reported=agent_exit_reported,
                    fill_gaps=fill_gaps,
                    harbor_activity=harbor_activity,
                )
                if state.get("complete"):
                    if agent is not None:
                        agent.terminate()
                    final_state = state
                    break
                if agent is not None and agent_exit_reported and not state.get("complete"):
                    final_state = state
                    break
                interruptible_sleep(WATCH_INTERVAL_SEC)

            selected_gaps = fill_gaps or []
            if fill_tools and selected_gaps:
                _present_gap_closing_finish(
                    live,
                    profile,
                    workspace,
                    final_state,
                    fill_tools=fill_tools,
                    selected_gaps=selected_gaps,
                    interactive=interactive,
                )
            elif interactive:
                live.hold_until_enter()

            return final_state
    except KeyboardInterrupt:
        _raise_interrupted(agent=agent, phase="gap closing")


def run_walkthrough(config: WalkthroughConfig) -> None:
    """Prepare the sandbox, run audit, then close actionable coverage gaps."""
    console = make_console(config.profile)
    try:
        _run_walkthrough(config, console)
    except KeyboardInterrupt:
        _raise_interrupted(phase="walkthrough")


def _run_walkthrough(config: WalkthroughConfig, console: Any) -> None:
    workspace = config.workspace.resolve()

    render_banner(console, config.profile, str(workspace))
    render_step(console, config.profile, "Prepare workspace", "Copy Harbor adapters and sandbox overlays")
    prepare_workspace(config, console=console)
    agent_runtime_env = _agent_runtime_env(config.profile, workspace)
    render_env_checklist(console, config.profile, agent_runtime_env)

    if not _ethos_path(workspace).is_file():
        render_step(
            console,
            config.profile,
            "Launch coding agent — ethos phase",
            f"Writing {ethos_path_label(config.workspace_label)} via nemo-ethos through the {config.profile.key} CLI",
        )
        ethos_prompt = build_nemo_ethos_prompt(config.workspace_label)
        try:
            ethos_agent = start_agent(
                config.profile,
                prompt=ethos_prompt,
                cwd=REPO_ROOT,
                workspace=workspace,
                env=agent_runtime_env,
            )
        except AgentCliError as exc:
            raise WalkthroughError(str(exc)) from exc

        console.print(f"[dim]Prompt:[/] {ethos_prompt.replace(chr(10), ' ')}")
        console.print()
        watch_until_ethos(console, config.profile, workspace, agent=ethos_agent)

    render_step(
        console,
        config.profile,
        "Launch coding agent — audit phase",
        f"Running eval-author audit through coverage report via the {config.profile.key} CLI",
    )
    audit_prompt = build_audit_phase_prompt(config.workspace_label)
    try:
        audit_agent = start_agent(
            config.profile,
            prompt=audit_prompt,
            cwd=REPO_ROOT,
            workspace=workspace,
            env=agent_runtime_env,
        )
    except AgentCliError as exc:
        raise WalkthroughError(str(exc)) from exc

    console.print(f"[dim]Prompt:[/] {audit_prompt.replace(chr(10), ' ')}")
    console.print()

    watch_until_coverage_report(console, config.profile, workspace, agent=audit_agent)
    all_gaps = _list_actionable_gaps(
        workspace,
        workspace / ".eval-author" / "audit-coverage-report.json",
    )
    if not all_gaps:
        console.print("[green]No actionable gaps in coverage report.[/]")
        return

    fill_tools = [str(gap["name"]) for gap in all_gaps]

    render_step(
        console,
        config.profile,
        "Launch coding agent — gap closing",
        f"Closing actionable gaps via the {config.profile.key} CLI",
    )
    gap_prompt = build_gap_close_prompt(config.workspace_label)
    try:
        gap_agent = start_agent(
            config.profile,
            prompt=gap_prompt,
            cwd=REPO_ROOT,
            workspace=workspace,
            env=agent_runtime_env,
        )
    except AgentCliError as exc:
        raise WalkthroughError(str(exc)) from exc

    console.print(f"[dim]Prompt:[/] {gap_prompt.replace(chr(10), ' ')}")
    console.print()

    watch_workspace(
        console,
        config.profile,
        workspace,
        agent=gap_agent,
        fill_gaps=all_gaps,
        fill_tools=fill_tools,
        interactive=config.interactive,
    )
