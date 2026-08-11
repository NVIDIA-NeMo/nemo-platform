# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end coverage for the insight-driven smoke-agent loop."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = _REPO_ROOT / "plugins" / "nemo-experimentalist" / "examples" / "smoke-agent"
_INSIGHT_SUITE = (
    _REPO_ROOT / "plugins" / "nemo-experimentalist" / "tests" / "experimentalist" / "test_smoke_agent_insight_suite.py"
)
_PLATFORM_URL = "http://localhost:8080"
_WORKSPACE = "smoke-agent"
_NO_PROXY = "localhost,127.0.0.1,::1,gateway.docker.internal,host.docker.internal"
_DEFAULT_MODEL = os.environ.get("NEMO_DEFAULT_MODEL", "default/openai-openai-gpt-5-5")
_FAST_MODEL = os.environ.get("NEMO_FAST_MODEL", "default/openai-openai-gpt-5-mini")
_RECORDS = _FIXTURE / "dataset" / "_shared" / "records.json"
_REPAIR_GROUPS = ("g1-aggregation", "g2-name-patterns", "g3-long-inputs", "g5-edge-cases")
_FAILING_TRAIN_TASKS = {
    "g1-aggregation": ("total-hours-engineers", "total-hours-research"),
    "g2-name-patterns": ("lookup-obrien", "lookup-zoe"),
    "g3-long-inputs": ("preamble-dept", "preamble-role"),
    "g5-edge-cases": ("empty-role", "missing-person"),
}
_ROOT_CAUSE_TERMS = {
    "g1-aggregation": ("total", "sum", "aggregat", "arithmetic"),
    "g2-name-patterns": ("regex", "apostrophe", "hyphen", "unicode", "character"),
    "g3-long-inputs": ("truncat", "max_instruction", "240", "preamble", "clip"),
    "g5-edge-cases": ("missing", "empty", "exception", "unknown", "lookup"),
}
_MIN_ROOT_CAUSE_HITS = 2

# The Analyst is tested by the nemo-insights plugin.  This test instead supplies
# a reviewed Insight with fresh, real trace ids so it isolates the Mode 1 loop:
# trace recording, Eval Author, and the Experimentalist itself.
_MOCK_INSIGHTS = {
    "g1-aggregation": {
        "title": "Total-hours questions fall through to the fallback answer",
        "description": (
            "When the prompt asks for the total hours for a selected group (for example, by role or "
            "department), smoke-agent's ordered handler dispatch runs handle_lookup, handle_list, and "
            "handle_count, but none of them match the aggregate-total form. The top-level solve span then "
            "returns the fixed fallback string 'I do not know how to answer that.' instead of writing the "
            "required single-line total=<result> answer. This diverges from the contract that sums over "
            "records must be reported with the canonical total= key, and suggests the deterministic regex "
            "handler set is missing a total/sum-hours handler for grouped selections."
        ),
    },
    "g2-name-patterns": {
        "title": "Names containing punctuation or non-ASCII characters do not resolve",
        "description": (
            "When the prompt asks for a record whose name contains an apostrophe, hyphen, or non-ASCII "
            "character, smoke-agent's handle_lookup method does not resolve that person. The lookup regex "
            "only accepts ASCII letters and spaces, so it drops the significant part of names such as "
            "O'Brien and Zoë Washington before the records lookup runs. The method then raises while "
            "searching for the altered name, and solve returns the fixed fallback string instead of the "
            "required canonical field=value answer. This suggests that the name-matching pattern must retain "
            "the characters that the records file permits."
        ),
    },
    "g3-long-inputs": {
        "title": "Long instructions lose the actual question before dispatch",
        "description": (
            "When a reporting-policy preamble comes before an otherwise valid records question, smoke-agent "
            "does not reach the question form its handlers recognise. solve truncates the instruction before "
            "dispatch, so the end of a long prompt, including the requested lookup, is removed. None of "
            "handle_lookup, handle_list, or handle_count then match, and the method returns the fixed fallback "
            "string instead of the required canonical field=value answer. This diverges from the agent's "
            "reporting contract and suggests the instruction-length limit must be raised or removed."
        ),
    },
    "g5-edge-cases": {
        "title": "Missing records and empty fields return the fallback answer",
        "description": (
            "When the prompt asks for a record that is absent or for a field whose value is empty, "
            "smoke-agent's lookup path does not produce the documented graceful value. handle_lookup raises "
            "while searching for a missing record or formats an empty value, and solve catches the exception "
            "only at the top level. It then returns the fixed fallback string rather than writing the required "
            "field=unknown answer. This diverges from the records-report contract and suggests lookup failures "
            "and empty fields need explicit, per-field handling."
        ),
    },
}


@dataclass(frozen=True)
class _E2EEnvironment:
    """The Platform model pair used by the host-side E2E run."""

    default_model: str
    fast_model: str


def _require_e2e_environment() -> _E2EEnvironment:
    """Check that the host services required by the handover procedure are available."""
    if os.environ.get("SMOKE_AGENT_E2E") != "1":
        pytest.skip("set SMOKE_AGENT_E2E=1 to run smoke-agent E2E tests")
    platform = subprocess.run(
        ["curl", "-sf", f"{_PLATFORM_URL}/health/ready"],
        capture_output=True,
        text=True,
        check=False,
    )
    if platform.returncode != 0:
        pytest.skip(f"start the Platform on {_PLATFORM_URL} before running the smoke-agent E2E tests")
    return _E2EEnvironment(default_model=_DEFAULT_MODEL, fast_model=_FAST_MODEL)


def _run(command: list[str], *, log: Path, environment: dict[str, str] | None = None) -> str:
    """Run one command and save its combined output for failure diagnosis."""
    with log.open("a", encoding="utf-8") as output:
        output.write("$ " + " ".join(command) + "\n")
        result = subprocess.run(
            command,
            cwd=_REPO_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        output.write(result.stdout or "")
    if result.returncode:
        pytest.fail(f"E2E command failed; log: {log}\n{log.read_text(encoding='utf-8')}")
    return result.stdout or ""


def _process_environment(environment: _E2EEnvironment) -> dict[str, str]:
    """Build the host environment shared by recording and optimization commands."""
    return os.environ | {
        "NEMO_DEFAULT_MODEL": environment.default_model,
        "NEMO_FAST_MODEL": environment.fast_model,
        "NO_PROXY": _NO_PROXY,
        "no_proxy": _NO_PROXY,
    }


def _record_trace_ids(
    environment: _E2EEnvironment,
    *,
    group: str,
    local_fixture: Path,
    workspace: str,
    artifact_parent: Path,
    log: Path,
) -> list[str]:
    """Record the group's train traces and return the published failing trace ids."""
    output = _run(
        [
            "uv",
            "run",
            "--frozen",
            "--python",
            "3.13",
            "--package",
            "nemo-experimentalist-plugin",
            "--with",
            str(_REPO_ROOT / "plugins" / "nemo-agents"),
            "python",
            str(local_fixture / "scripts" / "record_traces.py"),
            "--group",
            group,
            "--workspace",
            workspace,
            "--agent",
            str(local_fixture / "agent"),
            "--dataset-root",
            str(local_fixture / "dataset"),
            "--output",
            str(artifact_parent / "recordings"),
            "--base-url",
            _PLATFORM_URL,
        ],
        log=log,
        environment=_process_environment(environment),
    )
    published = dict(re.findall(r"^(\S+)\s+([0-9a-f]{32})$", output, flags=re.MULTILINE))
    expected = _FAILING_TRAIN_TASKS[group]
    missing = sorted(set(expected) - set(published))
    assert not missing, f"{group} recording did not publish failing task traces {missing}; see {log}"
    trace_ids = [published[task_id] for task_id in expected]
    assert len(trace_ids) == len(set(trace_ids)), f"{group} recording published duplicate trace ids: {trace_ids}"
    return trace_ids


def _write_mock_insight(
    *,
    group: str,
    workspace: str,
    trace_ids: list[str],
    path: Path,
) -> str:
    """Write one reviewed Insight that points at this run's recorded traces."""
    template = _MOCK_INSIGHTS[group]
    insight_id = f"mock-{group}-{uuid.uuid4().hex}"
    payload = {
        "insights": [
            {
                "id": insight_id,
                "workspace": workspace,
                "name": f"mock-{group}",
                "title": template["title"],
                "agent": "smoke-agent",
                "description": template["description"],
                "status": "open",
                "trace_refs": trace_ids,
            }
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # JSON is valid YAML.  Keeping this dependency-free makes the fixture's
    # mocked Analyst output easy to inspect in a failed pytest directory.
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return insight_id


def _run_experimentalist(
    environment: _E2EEnvironment,
    *,
    local_fixture: Path,
    experiment: Path,
    insight: Path,
    insight_id: str,
    workspace: str,
    log: Path,
) -> None:
    """Run the insight-driven loop on the host with one mocked Insight."""
    command = [
        "uv",
        "run",
        "--frozen",
        "--python",
        "3.13",
        "--package",
        "nemo-experimentalist-plugin",
        "--with",
        str(_REPO_ROOT / "plugins" / "nemo-agents"),
        "nemo",
        "agents",
        "experimentalist",
        "run",
        "--profile",
        str(local_fixture / "optimizer.yaml"),
        "--insight",
        str(insight),
        "--insight-id",
        insight_id,
        "--workspace",
        workspace,
        "--base-url",
        _PLATFORM_URL,
        "--config",
        str(local_fixture / "configs" / "short.yaml"),
        "--experiment-dir",
        str(experiment),
    ]
    process_environment = _process_environment(environment)
    with log.open("a", encoding="utf-8") as output:
        output.write("$ " + " ".join(command) + "\n")
        output.flush()
        process = subprocess.Popen(
            command,
            cwd=_REPO_ROOT,
            env=process_environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result = process.wait()
    if result:
        pytest.fail(f"E2E command failed; log: {log}\n{log.read_text(encoding='utf-8')}")


def _winner_label(experiment: Path) -> str:
    """Read the selected winner from the completed run."""
    run = json.loads((experiment / "eval-and-optimize" / "run.json").read_text(encoding="utf-8"))
    winner = run.get("winner_agent")
    assert winner, f"run.json has no winner_agent: {sorted(run)}"
    return str(winner)


def _agent_source(experiment: Path, label: str) -> str:
    """Read the saved source for one candidate."""
    return (experiment / "eval-and-optimize" / "agents" / label / "agent.py").read_text(encoding="utf-8")


def _replays_correctly(experiment: Path, label: str, task_dir: Path) -> bool:
    """Check one committed task against a saved candidate."""
    os.environ["RECORDS_PATH"] = str(_RECORDS)
    os.environ.setdefault("TRACE_DIR", tempfile.mkdtemp(prefix="smoke-mode-1-traces-"))
    path = experiment / "eval-and-optimize" / "agents" / label / "agent.py"
    spec = importlib.util.spec_from_file_location(f"_smoke_mode_1_{label}", path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    instruction = (task_dir / "instruction.md").read_text(encoding="utf-8").strip()
    expected = (task_dir / "tests" / "expected.txt").read_text(encoding="utf-8")
    actual = module.ReportAgent().solve(instruction) + "\n"
    return _normalize(actual) == _normalize(expected)


def _normalize(text: str) -> str:
    """Normalize line endings the same way the task verifier does."""
    return re.sub(r"\r$", "", text, flags=re.MULTILINE).rstrip("\n")


def _assert_committed_validation_passes(experiment: Path, group: str) -> None:
    """Check that the Mode 1 winner repairs every committed validation task."""
    winner = _winner_label(experiment)
    assert winner != "agent-0", f"{group} retained the baseline; nothing was repaired"
    assert _agent_source(experiment, winner) != _agent_source(experiment, "agent-0"), (
        f"{group} winner source is identical to the baseline"
    )
    validation = _FIXTURE / "dataset" / "groups" / group / "validation"
    tasks = [task for task in sorted(validation.iterdir()) if (task / "task.toml").is_file()]
    assert tasks, f"no validation tasks under {validation}; the fixture moved"
    failed = [task.name for task in tasks if not _replays_correctly(experiment, winner, task)]
    assert not failed, f"{winner} does not answer held-out {group} tasks: {failed}"


def _assert_analysis_named_problem(experiment: Path, group: str) -> None:
    """Check that the Analyzer named the problem measured by this group."""
    analyses = sorted((experiment / "eval-and-optimize" / "analysis").glob("round-*.md"))
    assert analyses, f"{group} has no Analyzer output"
    text = " ".join(path.read_text(encoding="utf-8") for path in analyses).lower()
    hits = [term for term in _ROOT_CAUSE_TERMS[group] if term in text]
    assert len(hits) >= _MIN_ROOT_CAUSE_HITS, f"{group} analysis did not name its problem; matched only {hits}"


@pytest.mark.e2e
@pytest.mark.timeout(2400)
@pytest.mark.parametrize("group", _REPAIR_GROUPS)
def test_insight_driven_loop_repairs_group(group: str, tmp_path: Path) -> None:
    """Check that Mode 1 records traces, uses a mocked Insight, and repairs one group."""
    environment = _require_e2e_environment()
    artifact_parent = tmp_path / group
    local_fixture = artifact_parent / "workspace" / "smoke-agent"
    experiment = artifact_parent / "experiment"
    log = artifact_parent / "run.log"
    workspace = f"smoke-agent-e2e-{group}-{uuid.uuid4().hex[:8]}"
    artifact_parent.mkdir(parents=True)
    shutil.copytree(_FIXTURE, local_fixture)

    profile = local_fixture / "optimizer.yaml"
    profile.write_text(
        profile.read_text(encoding="utf-8")
        .replace("g1-aggregation", group)
        .replace("workspace: default", f"workspace: {workspace}"),
        encoding="utf-8",
    )
    if group == "g5-edge-cases":
        config = local_fixture / "configs" / "short.yaml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "disable_trajectory_scoring: true",
                "disable_trajectory_scoring: false",
            ),
            encoding="utf-8",
        )

    _run(
        ["uv", "run", "--no-project", str(local_fixture / "scripts" / "build_image.py")],
        log=log,
    )
    trace_ids = _record_trace_ids(
        environment,
        group=group,
        local_fixture=local_fixture,
        workspace=workspace,
        artifact_parent=artifact_parent,
        log=log,
    )
    insight = artifact_parent / "insights" / f"{group}.yaml"
    insight_id = _write_mock_insight(
        group=group,
        workspace=workspace,
        trace_ids=trace_ids,
        path=insight,
    )
    _run_experimentalist(
        environment,
        local_fixture=local_fixture,
        experiment=experiment,
        insight=insight,
        insight_id=insight_id,
        workspace=workspace,
        log=log,
    )
    assert experiment.is_dir(), f"Experimentalist did not create the experiment directory at {experiment}"

    check_environment = os.environ | {
        "SMOKE_EXPERIMENT_DIR": str(experiment),
    }
    _assert_committed_validation_passes(experiment, group)
    _assert_analysis_named_problem(experiment, group)
    # This includes the authored-metric check, so the E2E stays red while the
    # known Mode 1 metric-discrimination defect remains unfixed.
    _run(
        ["uv", "run", "--frozen", "pytest", str(_INSIGHT_SUITE), "-v"],
        log=log,
        environment=check_environment,
    )
