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
from experimentalist_smoke_test_types import SandboxRunner
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import CACHE_STAMP_FILENAME

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = _REPO_ROOT / "plugins" / "nemo-experimentalist" / "examples" / "smoke-agent"
_HOST_PLATFORM_URL = "http://localhost:8080"
_WORKSPACE = "smoke-agent"
_NO_PROXY = "localhost,127.0.0.1,::1,gateway.docker.internal,host.docker.internal"
_RECORDS = _FIXTURE / "dataset" / "_shared" / "records.json"
_REPAIR_GROUPS = ("g1-aggregation", "g2-name-patterns", "g3-long-inputs", "g5-edge-cases")
_INSIGHT_EVIDENCE_TASKS = {
    "g1-aggregation": (
        "total-hours-engineers",
        "total-hours-research",
        "total-hours-analysts",
        "total-hours-operators",
        "total-hours-ops",
    ),
    "g2-name-patterns": (
        "lookup-obrien",
        "lookup-zoe",
        "lookup-ann-marie",
        "lookup-obrien-hours",
        "lookup-ann-marie-role",
    ),
    "g3-long-inputs": (
        "preamble-dept",
        "preamble-role",
        "preamble-dept-zoe",
        "preamble-role-grace",
        "preamble-hours-obrien",
    ),
    "g5-edge-cases": (
        "empty-role",
        "missing-person",
        "missing-person-linus",
        "missing-person-marie",
        "missing-person-katherine",
    ),
}
_ROOT_CAUSE_TERMS = {
    "g1-aggregation": ("total", "sum", "aggregat", "arithmetic"),
    "g2-name-patterns": ("regex", "apostrophe", "hyphen", "unicode", "character"),
    "g3-long-inputs": ("truncat", "max_instruction", "240", "preamble", "clip"),
    "g5-edge-cases": ("missing", "empty", "exception", "unknown", "lookup"),
}
_MIN_ROOT_CAUSE_HITS = 2
_TEMPLATE_DIR = _FIXTURE / "dataset" / "task-template"
_PLACEHOLDER = re.compile(r"<[A-Z][A-Z0-9_]*>")
_FILLABLE = ("instruction.md", "task.toml", "tests/expected.txt")
_GRAMMAR = (
    re.compile(r"what is the \w+ of ", re.IGNORECASE),
    re.compile(r"how many .* in the \w+ department", re.IGNORECASE),
    re.compile(r"what is the total \w+ in the \w+ (?:department|role)", re.IGNORECASE),
)


def _render_tasks(dataset: Path) -> None:
    """Render the compact task manifest into a disposable dataset copy."""
    path = _FIXTURE / "scripts" / "render_tasks.py"
    spec = importlib.util.spec_from_file_location("_smoke_render_tasks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    module.render(dataset)


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
class _ExperimentCase:
    """One Mode 1 loop configuration."""

    group: str
    generated_only: bool
    outcome_evaluator: str


@dataclass(frozen=True)
class _Experiment:
    """One downloaded Mode 1 experiment."""

    case: _ExperimentCase
    path: Path


_EXPERIMENT_CONFIGURATIONS = (
    *(
        _ExperimentCase(group, generated_only, "harbor-native")
        for group in _REPAIR_GROUPS
        for generated_only in (False, True)
    ),
    _ExperimentCase("g1-aggregation", True, "harbor-runner"),
)
_EXPERIMENT_CASES = tuple(
    pytest.param(
        case,
        id=f"{case.group}-{'generated-only' if case.generated_only else 'augmented'}-{case.outcome_evaluator}",
        marks=pytest.mark.xdist_group(
            f"mode-1-{case.group}-{'generated-only' if case.generated_only else 'augmented'}-{case.outcome_evaluator}"
        ),
    )
    for case in _EXPERIMENT_CONFIGURATIONS
)
_GENERATED_ONLY_CASES = tuple(
    pytest.param(
        case,
        id=f"{case.group}-generated-only-{case.outcome_evaluator}",
        marks=pytest.mark.xdist_group(f"mode-1-{case.group}-generated-only-{case.outcome_evaluator}"),
    )
    for case in _EXPERIMENT_CONFIGURATIONS
    if case.generated_only
)


def _require_e2e_environment() -> None:
    """Check that the host services required by the handover procedure are available."""
    platform = subprocess.run(
        ["curl", "-sf", f"{_HOST_PLATFORM_URL}/health/ready"],
        capture_output=True,
        text=True,
        check=False,
    )
    if platform.returncode != 0:
        pytest.skip(f"start the Platform on {_HOST_PLATFORM_URL} before running the smoke-agent E2E tests")


def _process_environment() -> dict[str, str]:
    """Build the minimum environment shared by recording and optimization commands."""
    return {
        "NO_PROXY": _NO_PROXY,
        "no_proxy": _NO_PROXY,
    }


def _record_trace_ids(
    runtime: SandboxRunner,
    *,
    group: str,
    remote_fixture: str,
    workspace: str,
    remote_artifact_parent: str,
    log: Path,
) -> list[str]:
    """Record the group's train traces and return the published failing trace ids."""
    output = runtime.run(
        [
            "uv",
            "run",
            "--frozen",
            "--python",
            "3.13",
            "--package",
            "nemo-experimentalist-plugin",
            "--with",
            "./plugins/nemo-agents",
            "python",
            f"{remote_fixture}/scripts/record_traces.py",
            "--group",
            group,
            "--split",
            "insight-evidence",
            "--workspace",
            workspace,
            "--agent",
            f"{remote_fixture}/agent",
            "--dataset-root",
            f"{remote_fixture}/dataset",
            "--output",
            f"{remote_artifact_parent}/recordings",
            "--base-url",
            runtime.platform_url,
        ],
        log=log,
        environment=_process_environment(),
        capture_output=True,
    )
    published = dict(re.findall(r"^(\S+)\s+([0-9a-f]{32})$", output, flags=re.MULTILINE))
    expected = _INSIGHT_EVIDENCE_TASKS[group]
    missing = sorted(set(expected) - set(published))
    assert not missing, f"{group} recording did not publish failing task traces {missing}; see {log}"
    trace_ids = [published[task_id] for task_id in expected]
    assert len(trace_ids) == len(set(trace_ids)), f"{group} recording published duplicate trace ids: {trace_ids}"
    assert len(trace_ids) >= 5, f"{group} Insight has too few evidence traces: {trace_ids}"
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
    runtime: SandboxRunner,
    *,
    remote_fixture: str,
    remote_experiment: str,
    remote_insight: str,
    insight_id: str,
    workspace: str,
    log: Path,
) -> None:
    """Run the insight-driven loop in the selected boundary with one mocked Insight."""
    command = [
        "uv",
        "run",
        "--frozen",
        "--python",
        "3.13",
        "--package",
        "nemo-experimentalist-plugin",
        "--with",
        "./plugins/nemo-agents",
        "nemo",
        "agents",
        "experimentalist",
        "run",
        "--profile",
        f"{remote_fixture}/optimizer.yaml",
        "--insight",
        remote_insight,
        "--insight-id",
        insight_id,
        "--workspace",
        workspace,
        "--base-url",
        runtime.platform_url,
        "--config",
        f"{remote_fixture}/configs/short.yaml",
        "--experiment-dir",
        remote_experiment,
    ]
    runtime.run(command, log=log, environment=_process_environment())


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
    return _agent_replays_correctly(experiment / "eval-and-optimize" / "agents" / label / "agent.py", label, task_dir)


def _agent_replays_correctly(agent_path: Path, label: str, task_dir: Path) -> bool:
    """Check one task against an agent source file."""
    os.environ["RECORDS_PATH"] = str(_RECORDS)
    os.environ.setdefault("TRACE_DIR", tempfile.mkdtemp(prefix="smoke-mode-1-traces-"))
    spec = importlib.util.spec_from_file_location(f"_smoke_mode_1_{label}", agent_path)
    assert spec is not None and spec.loader is not None, f"cannot import {agent_path}"
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


@pytest.mark.parametrize("group", _REPAIR_GROUPS)
def test_insight_evidence_tasks_fail_on_the_baseline(group: str, tmp_path: Path) -> None:
    """Check that five Insight evidence tasks show the group's baseline failure."""
    local_fixture = tmp_path / "smoke-agent"
    shutil.copytree(_FIXTURE, local_fixture)
    _render_tasks(local_fixture / "dataset")
    evidence = local_fixture / "dataset" / "groups" / group / "insight-evidence"
    tasks = [evidence / name for name in _INSIGHT_EVIDENCE_TASKS[group]]
    assert all(task.is_dir() for task in tasks), f"{group} did not create all Insight evidence tasks"
    still_passing = [
        task.name
        for task in tasks
        if _agent_replays_correctly(local_fixture / "agent" / "agent.py", f"baseline_{task.name}", task)
    ]
    assert not still_passing, f"{group} Insight evidence does not show the baseline failure: {still_passing}"


def _normalize(text: str) -> str:
    """Normalize line endings the same way the task verifier does."""
    return re.sub(r"\r$", "", text, flags=re.MULTILINE).rstrip("\n")


def _template_placeholders() -> set[str]:
    """Read every placeholder the committed task template declares."""
    found: set[str] = set()
    for name in _FILLABLE:
        path = _TEMPLATE_DIR / name
        if path.is_file():
            found.update(_PLACEHOLDER.findall(path.read_text(encoding="utf-8")))
    return found


def _suite_dirs(experiment: Path) -> list[Path]:
    """Find the materialized Insight suites from their manifests."""
    root = experiment / "eval-and-optimize" / "eval_author"
    return sorted(manifest.parent for manifest in root.rglob("insight-suite/manifest.json")) if root.is_dir() else []


def _materialized_tasks(suite: Path) -> list[Path]:
    """Read only the task directories listed in one suite manifest."""
    tasks = json.loads((suite / "manifest.json").read_text(encoding="utf-8")).get("tasks")
    return (
        [suite / entry["path"] for entry in tasks if isinstance(entry, dict) and entry.get("path")]
        if isinstance(tasks, list)
        else []
    )


def _authored_metric_keys(experiment: Path) -> set[str]:
    """Read the metrics Eval Author declared in its generated tasks."""
    keys: set[str] = set()
    for suite in _suite_dirs(experiment):
        for task in _materialized_tasks(suite):
            contract = task / "tests" / "metric-contract.json"
            if contract.is_file():
                keys.update(json.loads(contract.read_text(encoding="utf-8")).get("metric_keys") or [])
    return keys


def _baseline_split_metrics(experiment: Path, split: str) -> dict[str, float]:
    """Read the baseline aggregate metrics for one evaluated split."""
    result = experiment / "eval-and-optimize" / "results" / f"agent-0-{split}" / "result.json"
    evaluations = list(json.loads(result.read_text(encoding="utf-8"))["stats"]["evals"].values())
    assert len(evaluations) == 1, f"expected one evaluation in {result}, found {len(evaluations)}"
    metrics = evaluations[0]["metrics"]
    assert len(metrics) == 1, f"expected one aggregate metric record in {result}, found {len(metrics)}"
    return {str(name): float(value) for name, value in metrics[0].items()}


def _generated_trial_rewards(experiment: Path) -> list[dict[str, float]]:
    """Read baseline verifier rewards for the tasks Eval Author generated."""
    generated: list[dict[str, float]] = []
    for result in sorted((experiment / "eval-and-optimize" / "results").glob("agent-0-*/*/result.json")):
        payload = json.loads(result.read_text(encoding="utf-8"))
        if not str(payload.get("task_name", "")).startswith("smoke/generated__"):
            continue
        rewards = payload.get("verifier_result", {}).get("rewards")
        assert isinstance(rewards, dict), f"generated task {result.parent.name} has no verifier rewards"
        generated.append({str(name): float(value) for name, value in rewards.items()})
    assert generated, "no generated task produced a baseline trial result"
    return generated


def _check_insight_suite(experiment: Path, dataset: Path) -> None:
    """Check that Mode 1 produced usable generated tasks and objective metrics."""
    declared = _template_placeholders()
    assert declared, f"{_TEMPLATE_DIR} declares no <PLACEHOLDER> tokens"
    unmatched_curated = [
        path.parent.name
        for path in sorted((dataset / "groups").rglob("instruction.md"))
        if not any(pattern.search(path.read_text(encoding="utf-8")) for pattern in _GRAMMAR)
    ]
    assert not unmatched_curated, "curated tasks fall outside the agent grammar: " + ", ".join(unmatched_curated)
    suites = _suite_dirs(experiment)
    assert suites, "Eval Author did not materialize an Insight suite"
    tasks = [task for suite in suites for task in _materialized_tasks(suite)]
    assert tasks, "Insight suite manifests list no tasks"

    unfilled: list[str] = []
    empty_expected: list[str] = []
    off_grammar: list[str] = []
    for task in tasks:
        for name in _FILLABLE:
            path = task / name
            if path.is_file() and (
                remaining := sorted(set(_PLACEHOLDER.findall(path.read_text(encoding="utf-8"))) & declared)
            ):
                unfilled.append(f"{task.name}/{name}: {', '.join(remaining)}")
        expected = task / "tests" / "expected.txt"
        if expected.is_file() and not expected.read_text(encoding="utf-8").strip():
            empty_expected.append(task.name)
        instruction = task / "instruction.md"
        if instruction.is_file() and not any(
            pattern.search(instruction.read_text(encoding="utf-8")) for pattern in _GRAMMAR
        ):
            off_grammar.append(task.name)
    assert not unfilled, "Eval Author left template placeholders: " + "; ".join(unfilled)
    assert not empty_expected, "generated tasks have empty expected answers: " + ", ".join(empty_expected)
    assert not off_grammar, "generated questions fall outside the agent grammar: " + ", ".join(off_grammar)

    authored = _authored_metric_keys(experiment)
    assert authored, "Eval Author wrote no metric contract for the generated suite"
    missing_from_trials = [
        sorted(authored - rewards.keys())
        for rewards in _generated_trial_rewards(experiment)
        if not authored <= rewards.keys()
    ]
    assert not missing_from_trials, "generated task verifier results dropped authored metric keys: " + "; ".join(
        ", ".join(keys) for keys in missing_from_trials
    )
    for split in ("train", "validation"):
        missing = sorted(authored - _baseline_split_metrics(experiment, split).keys())
        assert not missing, f"baseline {split} aggregate dropped authored metric keys: {missing}"

    run = json.loads((experiment / "eval-and-optimize" / "run.json").read_text(encoding="utf-8"))
    objectives = run.get("config_snapshot", {}).get("objective_function")
    assert isinstance(objectives, list), "run.json has no objective_function in config_snapshot"
    objective_names = {str(metric.get("name")) for metric in objectives if isinstance(metric, dict)}
    assert objective_names == authored, (
        f"Mode 1 objectives {sorted(objective_names)} do not match Eval Author metrics {sorted(authored)}"
    )

    results = experiment / "eval-and-optimize" / "results"
    for task in tasks:
        matches = [
            trial
            for trial in results.rglob("*")
            if trial.is_dir()
            and (base := re.sub(r"__[A-Za-z0-9]+$", "", trial.name))
            and len(base) >= 12
            and task.name.startswith(base)
        ]
        assert matches and any((trial / "verifier" / "reward.json").is_file() for trial in matches), (
            f"generated task {task.name} produced no reward.json"
        )


def _assert_committed_validation_passes(experiment: Path, group: str, dataset: Path) -> None:
    """Check that the Mode 1 winner repairs every committed validation task."""
    winner = _winner_label(experiment)
    assert winner != "agent-0", f"{group} retained the baseline; nothing was repaired"
    assert _agent_source(experiment, winner) != _agent_source(experiment, "agent-0"), (
        f"{group} winner source is identical to the baseline"
    )
    validation = dataset / "groups" / group / "validation"
    tasks = [task for task in sorted(validation.iterdir()) if (task / "task.toml").is_file()]
    assert tasks, f"no validation tasks under {validation}; the fixture moved"
    failed = [task.name for task in tasks if not _replays_correctly(experiment, winner, task)]
    assert not failed, f"{winner} does not answer held-out {group} tasks: {failed}"


def _assert_loop_only_evaluated_generated_tasks(experiment: Path) -> None:
    """Check that the Mode 1 loop evaluated only tasks created from the Insight."""
    results = experiment / "eval-and-optimize" / "results"
    task_names: set[str] = set()
    for result in sorted(results.glob("agent-*/*/result.json")):
        payload = json.loads(result.read_text(encoding="utf-8"))
        task_name = payload.get("task_name")
        if isinstance(task_name, str):
            task_names.add(task_name)
    assert task_names, "the loop produced no trial results"
    leaked = sorted(name for name in task_names if not name.startswith("smoke/generated__"))
    assert not leaked, f"the Mode 1 loop evaluated committed tasks instead of only the Insight suite: {leaked}"


def _validation_metrics(experiment: Path, label: str) -> dict[str, float]:
    """Read one candidate's final validation metric values."""
    path = experiment / "eval-and-optimize" / "agents" / label / "metadata.json"
    metrics = (json.loads(path.read_text(encoding="utf-8")).get("rewards", {}).get("validation") or {}).get(
        "metrics", {}
    )
    assert isinstance(metrics, dict), f"{label} has no validation metrics"
    return {str(name): float(value) for name, value in metrics.items()}


def _assert_winner_improves_objectives_without_regression(experiment: Path) -> None:
    """Check that the selected Mode 1 winner improves objectives and preserves guardrails."""
    run = json.loads((experiment / "eval-and-optimize" / "run.json").read_text(encoding="utf-8"))
    winner = _winner_label(experiment)
    assert winner != "agent-0", "Mode 1 retained the baseline instead of selecting an improved winner"
    baseline = _validation_metrics(experiment, "agent-0")
    selected = _validation_metrics(experiment, winner)
    snapshot = run.get("config_snapshot", {})
    objectives = snapshot.get("objective_function")
    regressions = snapshot.get("regression_metrics")
    assert isinstance(objectives, list) and objectives, "run.json has no Mode 1 objective metrics"
    assert isinstance(regressions, list), "run.json has no Mode 1 regression metrics"

    for target in objectives:
        assert isinstance(target, dict) and isinstance(target.get("name"), str), f"invalid objective target: {target}"
        name = target["name"]
        assert name in baseline and name in selected, f"objective {name!r} is missing from winner or baseline metrics"
        assert selected[name] > baseline[name], (
            f"winner {winner} did not improve objective {name!r}: {baseline[name]} -> {selected[name]}"
        )

    for target in regressions:
        assert isinstance(target, dict) and isinstance(target.get("name"), str), f"invalid regression target: {target}"
        name = target["name"]
        direction = target.get("direction")
        assert direction in {"maximize", "minimize"}, f"invalid regression direction for {name!r}: {direction!r}"
        assert name in baseline and name in selected, f"regression {name!r} is missing from winner or baseline metrics"
        worsened = selected[name] < baseline[name] if direction == "maximize" else selected[name] > baseline[name]
        assert not worsened, f"winner {winner} regressed {name!r}: {baseline[name]} -> {selected[name]}"


def _assert_analysis_named_problem(experiment: Path, group: str) -> None:
    """Check that the Analyzer named the problem measured by this group."""
    analyses = sorted((experiment / "eval-and-optimize" / "analysis").glob("round-*.md"))
    assert analyses, f"{group} has no Analyzer output"
    text = " ".join(path.read_text(encoding="utf-8") for path in analyses).lower()
    hits = [term for term in _ROOT_CAUSE_TERMS[group] if term in text]
    assert len(hits) >= _MIN_ROOT_CAUSE_HITS, f"{group} analysis did not name its problem; matched only {hits}"


def _assert_harbor_runner_execution_provenance(experiment: Path, case: _ExperimentCase) -> None:
    """Check that runner cases wrote the SDK's Harbor cache-stamp artifact."""
    if case.outcome_evaluator != "harbor-runner":
        return
    stamps = sorted((experiment / "eval-and-optimize" / "results").rglob(CACHE_STAMP_FILENAME))
    assert stamps, "harbor-runner did not write an SDK Harbor cache stamp into its job directories"


def _run_mode_1_case(
    group: str,
    tmp_path: Path,
    runtime: SandboxRunner,
    *,
    generated_only: bool,
    outcome_evaluator: str,
) -> Path:
    """Run and download one Mode 1 group with either augmented or generated-only data."""
    _require_e2e_environment()
    mode = "generated-only" if generated_only else "augmented"
    artifact_parent = tmp_path / f"{group}-{mode}-{outcome_evaluator}"
    experiment = artifact_parent / "experiment"
    log = artifact_parent / "run.log"
    workspace = f"smoke-agent-e2e-{group}-{uuid.uuid4().hex[:8]}"
    artifact_parent.mkdir(parents=True)
    remote_fixture, remote_experiment = runtime.prepare_fixture(artifact_parent, log=log)
    remote_artifact_parent = str(Path(remote_experiment).parent)
    profile = f"{remote_fixture}/optimizer.yaml"
    runtime.replace_text(profile, "g1-aggregation", group, log=log)
    runtime.replace_text(profile, "workspace: default", f"workspace: {workspace}", log=log)
    if generated_only:
        runtime.make_directories(
            f"{remote_fixture}/generated-only/train",
            f"{remote_fixture}/generated-only/validation",
            log=log,
        )
        runtime.replace_text(profile, f"./dataset/groups/{group}/train", "./generated-only/train", log=log)
        runtime.replace_text(profile, f"./dataset/groups/{group}/validation", "./generated-only/validation", log=log)
    if group == "g5-edge-cases":
        runtime.replace_text(
            f"{remote_fixture}/configs/short.yaml",
            "disable_trajectory_scoring: true",
            "disable_trajectory_scoring: false",
            log=log,
        )
    if outcome_evaluator == "harbor-runner":
        runtime.replace_text(
            f"{remote_fixture}/configs/short.yaml",
            "outcome_evaluator_config:",
            "outcome_evaluator: harbor-runner\noutcome_evaluator_config:",
            log=log,
        )

    if os.environ.get("SMOKE_AGENT_IMAGE_BUILT") != "1":
        runtime.run(
            ["uv", "run", "--no-project", f"{remote_fixture}/scripts/build_image.py"],
            log=log,
        )
    trace_ids = _record_trace_ids(
        runtime,
        group=group,
        remote_fixture=remote_fixture,
        workspace=workspace,
        remote_artifact_parent=remote_artifact_parent,
        log=log,
    )
    insight = artifact_parent / "insights" / f"{group}.yaml"
    insight_id = _write_mock_insight(
        group=group,
        workspace=workspace,
        trace_ids=trace_ids,
        path=insight,
    )
    remote_insights = f"{remote_artifact_parent}/insights"
    runtime.make_directories(remote_insights, log=log)
    runtime.copy_in(insight, remote_insights, log=log)
    _run_experimentalist(
        runtime,
        remote_fixture=remote_fixture,
        remote_experiment=remote_experiment,
        remote_insight=f"{remote_insights}/{insight.name}",
        insight_id=insight_id,
        workspace=workspace,
        log=log,
    )
    runtime.fetch(remote_experiment, artifact_parent, log=log)
    assert experiment.is_dir(), f"Experimentalist did not create the experiment directory at {experiment}"
    return experiment


@pytest.fixture(scope="session")
def experiment(
    request: pytest.FixtureRequest,
    sandbox_runner: SandboxRunner,
    tmp_path_factory: pytest.TempPathFactory,
) -> _Experiment:
    """Run and download one Mode 1 case."""
    case = request.param
    assert isinstance(case, _ExperimentCase)
    path = _run_mode_1_case(
        case.group,
        tmp_path_factory.mktemp(f"mode-1-{case.group}-{case.outcome_evaluator}"),
        sandbox_runner,
        generated_only=case.generated_only,
        outcome_evaluator=case.outcome_evaluator,
    )
    run = json.loads((path / "eval-and-optimize" / "run.json").read_text(encoding="utf-8"))
    assert run.get("config_snapshot", {}).get("outcome_evaluator") == case.outcome_evaluator
    _assert_harbor_runner_execution_provenance(path, case)
    return _Experiment(case, path)


@pytest.fixture(scope="session")
def rendered_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Render curated tasks for host-side candidate checks."""
    dataset = tmp_path_factory.mktemp("smoke-agent-dataset") / "dataset"
    shutil.copytree(_FIXTURE / "dataset", dataset)
    _render_tasks(dataset)
    return dataset


@pytest.mark.e2e
@pytest.mark.timeout(3600)
@pytest.mark.parametrize("experiment", _EXPERIMENT_CASES, indirect=True)
def test_insight_driven_loop_materializes_a_usable_suite(experiment: _Experiment, rendered_dataset: Path) -> None:
    """Check that each downloaded Mode 1 experiment has usable generated tasks and objectives."""
    _check_insight_suite(experiment.path, rendered_dataset)


@pytest.mark.e2e
@pytest.mark.timeout(3600)
@pytest.mark.parametrize("experiment", _EXPERIMENT_CASES, indirect=True)
def test_insight_driven_loop_improves_objectives(experiment: _Experiment) -> None:
    """Check that each downloaded Mode 1 winner improves objectives without regression."""
    _assert_winner_improves_objectives_without_regression(experiment.path)


@pytest.mark.e2e
@pytest.mark.timeout(3600)
@pytest.mark.parametrize("experiment", _GENERATED_ONLY_CASES, indirect=True)
def test_generated_only_mode_1_uses_only_generated_tasks(experiment: _Experiment) -> None:
    """Check that generated-only Mode 1 experiments never evaluate committed tasks in the loop."""
    _assert_loop_only_evaluated_generated_tasks(experiment.path)


@pytest.mark.e2e
@pytest.mark.timeout(3600)
@pytest.mark.parametrize("experiment", _GENERATED_ONLY_CASES, indirect=True)
def test_generated_only_mode_1_repairs_committed_holdout(experiment: _Experiment, rendered_dataset: Path) -> None:
    """Check that generated-only Mode 1 winners repair their untouched committed validation tasks."""
    _assert_committed_validation_passes(experiment.path, experiment.case.group, rendered_dataset)


@pytest.mark.e2e
@pytest.mark.timeout(3600)
@pytest.mark.parametrize("experiment", _EXPERIMENT_CASES, indirect=True)
def test_mode_1_analysis_names_the_problem(experiment: _Experiment) -> None:
    """Check that each downloaded Mode 1 experiment contains the expected diagnosis."""
    _assert_analysis_named_problem(experiment.path, experiment.case.group)
