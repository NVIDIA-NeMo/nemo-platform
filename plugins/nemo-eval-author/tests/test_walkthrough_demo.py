# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_CLI_DIR = Path(__file__).resolve().parents[1] / "walkthrough" / "quick-start-cli"
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

from display import build_audit_phase_prompt, get_profile  # noqa: E402
from harbor_progress import HARBOR_TRIAL_RE  # noqa: E402


def test_get_profile_cursor() -> None:
    profile = get_profile("cursor")
    assert profile.key == "cursor"
    assert "Cursor" in profile.subtitle


def test_get_profile_claude() -> None:
    profile = get_profile("claude")
    assert profile.key == "claude"
    assert "Claude" in profile.subtitle


def test_get_profile_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported agent"):
        get_profile("copilot")


def test_build_nemo_ethos_prompt() -> None:
    from display import build_nemo_ethos_prompt  # noqa: E402

    prompt = build_nemo_ethos_prompt("tmp/rho-agent-walkthrough")
    assert prompt == (
        "Use nemo-ethos for rho-agent in tmp/rho-agent-walkthrough; explore the cloned source at "
        "rho-agent/; write tmp/rho-agent-walkthrough/agents/rho-agent-ethos/ETHOS.md locally only; "
        "do not upload to Filesets."
    )


def test_build_audit_phase_prompt() -> None:
    prompt = build_audit_phase_prompt("tmp/rho-agent-walkthrough")
    assert "through audit Step 5 only" in prompt
    assert "tmp/rho-agent-walkthrough/agents/rho-agent-ethos/ETHOS.md" in prompt
    assert "tmp/rho-agent-walkthrough/" in prompt
    assert "Bootstrap ETHOS" not in prompt
    assert "Do not run task_pipeline.py select" in prompt


def test_build_audit_phase_prompt_strips_trailing_slash() -> None:
    prompt = build_audit_phase_prompt("tmp/fixture/")
    assert "tmp/fixture/" in prompt
    assert "through audit Step 5 only" in prompt


_ETHOS = Path("agents/rho-agent-ethos/ETHOS.md")


def test_prepare_workspace_does_not_seed_eval_author_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from display import get_profile  # noqa: E402
    from runner import WalkthroughConfig, prepare_workspace  # noqa: E402

    workspace = tmp_path / "ws"

    def fake_copy_harbor_assets(workspace_arg: Path) -> None:
        assert workspace_arg == workspace.resolve()
        overlay = workspace / ".eval-author" / "sandbox" / "task-0"
        overlay.mkdir(parents=True)
        (overlay / "instruction.md").write_text("hello", encoding="utf-8")

    monkeypatch.setattr("runner._copy_walkthrough_harbor_assets", fake_copy_harbor_assets)
    monkeypatch.setattr("runner._ensure_rho_agent_checkout", lambda workspace_arg: None)

    config = WalkthroughConfig(
        workspace=workspace,
        workspace_label="tmp/ws",
        profile=get_profile("cursor"),
    )
    prepare_workspace(config)

    assert (workspace / "rho_harbor_agent.py").is_file()
    assert (workspace / "rho_atif_compat.py").is_file()
    assert not (workspace / _ETHOS).exists()
    assert not (workspace / ".eval-author" / "audit-items.yaml").exists()
    assert (workspace / ".eval-author" / "sandbox" / "task-0" / "instruction.md").is_file()


def test_prepare_workspace_aborts_when_artifacts_exist(tmp_path: Path) -> None:
    from display import get_profile  # noqa: E402
    from runner import WalkthroughConfig, WalkthroughError, prepare_workspace  # noqa: E402

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / _ETHOS).parent.mkdir(parents=True)
    (workspace / _ETHOS).write_text("# Ethos", encoding="utf-8")

    config = WalkthroughConfig(
        workspace=workspace,
        workspace_label="tmp/ws",
        profile=get_profile("cursor"),
        interactive=False,
    )

    with pytest.raises(WalkthroughError, match="Workspace already contains walkthrough artifacts"):
        prepare_workspace(config)


def test_prepare_workspace_interactive_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from display import get_profile  # noqa: E402
    from runner import WalkthroughConfig, prepare_workspace  # noqa: E402

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / _ETHOS).parent.mkdir(parents=True)
    (workspace / _ETHOS).write_text("# Ethos", encoding="utf-8")

    monkeypatch.setattr(
        "runner._copy_walkthrough_harbor_assets",
        lambda workspace_arg: None,
    )
    monkeypatch.setattr("runner._ensure_rho_agent_checkout", lambda workspace_arg: None)
    monkeypatch.setattr("runner.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: True)

    config = WalkthroughConfig(
        workspace=workspace,
        workspace_label="tmp/ws",
        profile=get_profile("cursor"),
    )
    prepare_workspace(config)

    assert not (workspace / _ETHOS).exists()


def test_prepare_workspace_interactive_abort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from display import get_profile  # noqa: E402
    from runner import WalkthroughArtifactsKept, WalkthroughConfig, prepare_workspace  # noqa: E402

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / _ETHOS).parent.mkdir(parents=True)
    (workspace / _ETHOS).write_text("# Ethos", encoding="utf-8")

    monkeypatch.setattr("runner.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: False)

    config = WalkthroughConfig(
        workspace=workspace,
        workspace_label="tmp/ws",
        profile=get_profile("cursor"),
    )

    with pytest.raises(WalkthroughArtifactsKept, match="Keeping existing walkthrough artifacts"):
        prepare_workspace(config)


def test_build_agent_command_cursor() -> None:
    from agents import build_agent_command  # noqa: E402

    command = build_agent_command(get_profile("cursor"), "audit this workspace")
    assert command[-1] == "audit this workspace"
    assert "-p" in command
    assert "-f" in command
    assert "--trust" in command
    assert "--output-format" in command
    assert "stream-json" in command
    assert command[0] in {"agent", "cursor"}


def test_build_agent_command_claude() -> None:
    from agents import build_agent_command  # noqa: E402

    command = build_agent_command(get_profile("claude"), "audit this workspace")
    assert command == ["claude", "--print", "--dangerously-skip-permissions"]


def test_agent_env_sets_pythonpath(tmp_path: Path) -> None:
    from agents import agent_env  # noqa: E402

    workspace = tmp_path / "ws"
    env = agent_env(get_profile("cursor"), workspace, {"PYTHONPATH": "/existing"})
    assert env["PYTHONPATH"] == f"{workspace}{os.pathsep}/existing"


def test_parse_cursor_stream_line_tool_call() -> None:
    from agent_events import parse_cursor_stream_line  # noqa: E402

    line = (
        '{"type":"tool_call","subtype":"started","tool_call":{"shellToolCall":{"args":'
        '{"command":"harbor jobs start","description":"Run baseline Harbor job"}}}}'
    )
    assert parse_cursor_stream_line(line) == "Running: shell — Run baseline Harbor job"


def test_parse_cursor_stream_line_thinking() -> None:
    from agent_events import parse_cursor_stream_line  # noqa: E402

    assert parse_cursor_stream_line('{"type":"thinking","subtype":"delta","text":"planning"}') == "Thinking…"


def test_start_agent_claude_writes_prompt_to_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import Mock

    from agents import start_agent  # noqa: E402

    captured: dict[str, str] = {}
    stdin = Mock()
    stdin.write = lambda data: captured.setdefault("prompt", data)
    stdin.close = Mock()

    proc = Mock()
    proc.stdin = stdin
    proc.stdout = Mock(__iter__=Mock(return_value=iter([])))
    proc.stderr = Mock(__iter__=Mock(return_value=iter([])))
    proc.poll = Mock(return_value=0)
    proc.returncode = 0

    monkeypatch.setattr("agents.subprocess.Popen", lambda *args, **kwargs: proc)
    monkeypatch.setattr("agents.preflight_agent_cli", lambda profile: ["claude"])

    start_agent(
        get_profile("claude"),
        prompt="run eval-author",
        cwd=tmp_path,
        workspace=tmp_path / "ws",
    )
    assert captured["prompt"] == "run eval-author"


@pytest.mark.parametrize(
    ("line", "completed", "total"),
    [
        ("  1/2 Mean: 0.500", 1, 2),
        ("  2/2 Mean: 1.000", 2, 2),
    ],
)
def test_harbor_progress_regex(line: str, completed: int, total: int) -> None:
    match = HARBOR_TRIAL_RE.match(line)
    assert match is not None
    assert int(match.group(1)) == completed
    assert int(match.group(2)) == total


def test_render_coverage_table_uses_covered_names() -> None:
    from io import StringIO

    from display import build_coverage_table, get_profile
    from rich.console import Console

    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=120, highlight=False)
    items = [
        {"kind": "tool", "name": "read", "description": "read files"},
        {"kind": "tool", "name": "write", "description": "write files"},
    ]
    console.print(
        build_coverage_table(
            items,
            covered=["write"],
            measured_kinds=["tool"],
        )
    )
    output = buffer.getvalue()
    assert "write" in output
    assert "read" in output
    assert get_profile("cursor").accent  # keep import used


def test_draft_is_ready_requires_harbor_files(tmp_path: Path) -> None:
    from gap_state import draft_is_ready  # noqa: E402

    draft = tmp_path / ".eval-author" / "task-drafts" / "cover-read"
    (draft / "solution").mkdir(parents=True)
    (draft / "tests").mkdir(parents=True)
    assert draft_is_ready(tmp_path, "cover-read") is False
    for name in ("instruction.md", "task.toml"):
        (draft / name).write_text("x", encoding="utf-8")
    (draft / "solution" / "solve.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (draft / "tests" / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    assert draft_is_ready(tmp_path, "cover-read") is True


def test_harbor_tracker_oracle_then_trials() -> None:
    from harbor_progress import GapPhase, HarborProgressTracker  # noqa: E402

    tracker = HarborProgressTracker()
    oracle = tracker.start_oracle()
    assert oracle.phase == GapPhase.ORACLE
    assert oracle.detail == "oracle"

    update = tracker.feed_line("  1/2 Mean: 0.500")
    assert update is not None
    assert update.phase == GapPhase.TRIAL_2
    assert "run 2/2" in update.detail

    update = tracker.feed_line("  2/2 Mean: 1.000")
    assert update is not None
    assert update.phase == GapPhase.TRIAL_2
    assert "2/2 done" in update.detail


def test_harbor_tracker_detects_retry_on_backtrack() -> None:
    from harbor_progress import GapPhase, HarborProgressTracker  # noqa: E402

    tracker = HarborProgressTracker()
    tracker.start_trials(total=2)
    tracker.feed_line("  2/2 Mean: 1.000")
    update = tracker.feed_line("  1/2 Mean: 0.000")
    assert update is not None
    assert update.attempt == 2
    assert update.phase == GapPhase.RETRY
    assert "retry 2" in update.detail


def test_infer_gap_phase_from_measurements(tmp_path: Path) -> None:
    from harbor_progress import GapPhase, infer_gap_phase  # noqa: E402

    slug = "cover-read"
    draft = tmp_path / ".eval-author" / "task-drafts" / slug
    (draft / "solution").mkdir(parents=True)
    (draft / "tests").mkdir(parents=True)
    for name in ("instruction.md", "task.toml"):
        (draft / name).write_text("x", encoding="utf-8")
    (draft / "solution" / "solve.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (draft / "tests" / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    progress = infer_gap_phase(tmp_path, "read", slug)
    assert progress.phase == GapPhase.ORACLE

    repeat = tmp_path / ".eval-author" / "task-measurements" / slug / "repeat-1"
    (repeat / "tool_calls").mkdir(parents=True)
    (repeat / "tool_calls" / "coverage.json").write_text("{}", encoding="utf-8")
    progress = infer_gap_phase(tmp_path, "read", slug)
    assert progress.phase == GapPhase.MEASURE


def test_infer_gap_progress_wrapper(tmp_path: Path) -> None:
    from gap_state import infer_gap_progress  # noqa: E402
    from harbor_progress import GapPhase  # noqa: E402

    progress = infer_gap_progress(tmp_path, "read", "cover-read")
    assert progress.tool == "read"
    assert progress.phase == GapPhase.WAITING


def test_agent_log_pane_renders_activity() -> None:
    from live_display import AgentLogPane  # noqa: E402

    pane = AgentLogPane("cursor", max_lines=5)
    pane.set_activity("Running: shell — harbor jobs start")
    panel = pane.render(pulse=3)
    assert panel.title is not None


def test_build_workspace_activity_hides_audit_denominator_during_gap_closing() -> None:
    from io import StringIO

    from display import build_workspace_activity_group, get_profile  # noqa: E402
    from rich.console import Console

    profile = get_profile("cursor")
    items = [{"kind": "tool", "name": "read", "description": "read files"}]
    report = {"covered": ["write"], "measured_kinds": ["tool"]}
    workspace = Path("tmp/rho-agent-walkthrough")
    base_state = {"audit_items": items, "coverage_report": report}

    def render(state: dict[str, object]) -> str:
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=True, width=120, highlight=False)
        console.print(build_workspace_activity_group(profile, workspace, state))
        return buffer.getvalue()

    assert "Audit denominator" in render({**base_state, "fill_tools": []})
    assert "Audit denominator" not in render({**base_state, "fill_tools": ["read"]})


def test_format_gap_focus_strips_boilerplate() -> None:
    from display import format_gap_focus  # noqa: E402

    raw = "Exercise a scenario where the agent should call read: Used when the agent must inspect file contents."
    assert format_gap_focus(raw) == "Used when the agent must inspect file contents."


def test_gap_list_shows_actionable_gaps() -> None:
    from io import StringIO

    from display import build_gap_list_renderable  # noqa: E402
    from rich.console import Console

    gaps = [
        {"name": "read", "task_slug": "cover-read", "focus": "Read a file"},
        {"name": "sqlite", "task_slug": "cover-sqlite", "focus": "Query sqlite"},
    ]
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=120, highlight=False)
    console.print(build_gap_list_renderable(gaps))
    output = buffer.getvalue()
    assert "Actionable gaps" in output
    assert "sqlite" in output
    assert "read" in output


def test_infer_active_workspace_artifact_ethos() -> None:
    from display import infer_active_workspace_artifact  # noqa: E402

    assert infer_active_workspace_artifact({"watch_active": True}) == "ethos"
    assert infer_active_workspace_artifact({"ethos": True, "watch_active": True}) == "audit"
    assert (
        infer_active_workspace_artifact({"ethos": True, "audit_items": [{}], "watch_active": True}) == "coverage_report"
    )


def test_infer_active_workspace_artifact_task_drafts() -> None:
    from display import infer_active_workspace_artifact  # noqa: E402

    base = {
        "ethos": True,
        "audit_items": [{}],
        "coverage_report": {"covered": []},
        "fill_tools": ["read"],
        "watch_active": True,
    }
    assert infer_active_workspace_artifact(base) == "task_drafts"
    assert infer_active_workspace_artifact({**base, "task_drafts": ["cover-read"]}) is None
    assert (
        infer_active_workspace_artifact(
            {
                **base,
                "task_drafts": ["cover-read"],
                "gap_progress": [{"phase": "trial-1", "tool": "read"}],
            }
        )
        == "task_drafts"
    )


def test_finalize_gap_run_raises_on_failed_gap(tmp_path: Path) -> None:
    from io import StringIO

    from gap_state import GapProgress  # noqa: E402
    from harbor_progress import GapPhase  # noqa: E402
    from rich.console import Console
    from run_report import WalkthroughGapFailures, finalize_gap_run, run_report_paths  # noqa: E402

    gaps = [
        GapProgress(
            tool="read",
            task_slug="cover-read",
            phase=GapPhase.FAILED,
            detail="oracle failed",
            error="reward 0",
            error_log="reward 0\n",
        ),
    ]
    console = Console(file=StringIO(), force_terminal=True, width=120, highlight=False)
    with pytest.raises(WalkthroughGapFailures, match="read"):
        finalize_gap_run(
            console,
            tmp_path,
            gaps,
            mode="sequential",
            fill_tools=["read"],
        )

    json_path, log_path = run_report_paths(tmp_path)
    assert json_path.is_file()
    assert log_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["failed"] == ["read"]
    assert "oracle failed" in log_path.read_text(encoding="utf-8")


def test_reconcile_gap_outcomes_marks_incomplete_sequential_gaps_failed() -> None:
    from gap_state import GapProgress  # noqa: E402
    from harbor_progress import GapPhase  # noqa: E402
    from run_report import reconcile_gap_outcomes  # noqa: E402

    gaps = [
        GapProgress(
            tool="read",
            task_slug="cover-read",
            phase=GapPhase.TRIAL_2,
            detail="rho-agent run 2/2",
        ),
    ]
    reconciled = reconcile_gap_outcomes(
        gaps,
        fill_tools=["read"],
        complete=False,
        covered=set(),
    )
    assert reconciled[0].phase == GapPhase.FAILED
    assert reconciled[0].error == "agent exited before gap closed"


def test_reconcile_gap_outcomes_marks_complete_run_accepted() -> None:
    from gap_state import GapProgress  # noqa: E402
    from harbor_progress import GapPhase  # noqa: E402
    from run_report import reconcile_gap_outcomes  # noqa: E402

    gaps = [
        GapProgress(
            tool="read",
            task_slug="cover-read",
            phase=GapPhase.VERIFY,
            detail="verify",
        ),
    ]
    reconciled = reconcile_gap_outcomes(
        gaps,
        fill_tools=["read"],
        complete=True,
        covered={"read"},
    )
    assert reconciled[0].phase == GapPhase.ACCEPTED
    assert reconciled[0].accepted is True


def test_agent_log_pane_keeps_last_n_lines() -> None:
    from live_display import AgentLogPane  # noqa: E402

    pane = AgentLogPane("cursor", max_lines=10)
    for index in range(15):
        pane.append(f"line {index}")
    assert len(pane._lines) == 10
    assert pane._lines[0] == "line 5"
    assert pane._lines[-1] == "line 14"
