# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end coverage for the dataset-driven smoke-agent loop."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = _REPO_ROOT / "plugins" / "nemo-experimentalist" / "examples" / "smoke-agent"
_PLATFORM_URL = "http://localhost:8080"
_NO_PROXY = "localhost,127.0.0.1,::1,gateway.docker.internal,host.docker.internal"
_DEFAULT_MODEL = os.environ.get("NEMO_DEFAULT_MODEL", "default/openai-openai-gpt-5-5")
_FAST_MODEL = os.environ.get("NEMO_FAST_MODEL", "default/openai-openai-gpt-5-mini")
_RECORDS = _FIXTURE / "dataset" / "_shared" / "records.json"
_G4_CONTROL_TASKS = {"smoke/g4-lookup-grace"}
_REWARD_DELTA_THRESHOLD = 0.3
_ROOT_CAUSE_TERMS = {
    "g1-aggregation": ("total", "sum", "aggregat", "arithmetic"),
    "g2-name-patterns": ("regex", "apostrophe", "hyphen", "unicode", "character"),
    "g3-long-inputs": ("truncat", "max_instruction", "240", "preamble", "clip"),
    "g5-edge-cases": ("missing", "empty", "exception", "unknown", "lookup"),
}
_MIN_ROOT_CAUSE_HITS = 2


@dataclass(frozen=True)
class _E2EEnvironment:
    """The Platform model pair used by host-side E2E runs."""

    default_model: str
    fast_model: str


def _require_e2e_environment() -> tuple[str, str]:
    """Check that the host services required by the handover procedure are available."""
    if os.environ.get("SMOKE_AGENT_E2E") != "1":
        pytest.skip("set SMOKE_AGENT_E2E=1 to run smoke-agent E2E tests")
    platform = subprocess.run(
        ["curl", "-sf", "http://localhost:8080/health/ready"],
        capture_output=True,
        text=True,
        check=False,
    )
    if platform.returncode != 0:
        pytest.skip("start the Platform on http://localhost:8080 before running the smoke-agent E2E tests")
    return _DEFAULT_MODEL, _FAST_MODEL


def _run(command: list[str], *, log: Path, environment: dict[str, str] | None = None) -> None:
    """Run one command and save its combined output for failure diagnosis."""
    with log.open("a", encoding="utf-8") as output:
        output.write("$ " + " ".join(command) + "\n")
        result = subprocess.run(
            command,
            cwd=_REPO_ROOT,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if result.returncode:
        pytest.fail(f"E2E command failed; log: {log}\n{log.read_text(encoding='utf-8')}")


@pytest.fixture(scope="session")
def _e2e_environment(tmp_path_factory: pytest.TempPathFactory) -> _E2EEnvironment:
    """Prepare the shared host environment used by every E2E group."""
    default_model, fast_model = _require_e2e_environment()
    environment = _E2EEnvironment(
        default_model=default_model,
        fast_model=fast_model,
    )
    log = tmp_path_factory.mktemp("smoke-agent-e2e") / "host.log"
    _run(
        [
            "uv",
            "run",
            "--no-project",
            str(_FIXTURE / "scripts" / "build_image.py"),
        ],
        log=log,
    )
    return environment


def _run_e2e_command(
    environment: _E2EEnvironment,
    command: list[str],
    *,
    log: Path,
) -> None:
    """Run one Experimentalist command on the host."""
    process_environment = os.environ | {
        "NEMO_DEFAULT_MODEL": environment.default_model,
        "NEMO_FAST_MODEL": environment.fast_model,
        "NO_PROXY": _NO_PROXY,
        "no_proxy": _NO_PROXY,
    }
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


def _run_group(
    group: str,
    *,
    environment: _E2EEnvironment,
    artifact_parent: Path,
    profile_name: str = "optimizer.yaml",
) -> tuple[Path, Path]:
    """Run one group from a separate host-side copy of the smoke fixture."""
    artifact_parent.mkdir(parents=True, exist_ok=True)
    local_fixture = artifact_parent / "workspace" / "smoke-agent"
    experiment = artifact_parent / "experiment"
    shutil.copytree(_FIXTURE, local_fixture)
    log = artifact_parent / "run.log"
    profile = local_fixture / profile_name
    config = local_fixture / "configs" / "short.yaml"
    if group != "g1-aggregation":
        profile.write_text(profile.read_text(encoding="utf-8").replace("g1-aggregation", group), encoding="utf-8")
    if group == "g5-edge-cases":
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "disable_trajectory_scoring: true",
                "disable_trajectory_scoring: false",
            ),
            encoding="utf-8",
        )
    _run_e2e_command(
        environment,
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
            "nemo",
            "agents",
            "experimentalist",
            "run",
            "--profile",
            str(profile),
            "--no-insight",
            "--base-url",
            _PLATFORM_URL,
            "--config",
            str(config),
            "--experiment-dir",
            str(experiment),
        ],
        log=log,
    )
    assert experiment.is_dir(), f"Experimentalist did not create the experiment directory at {experiment}"
    return experiment, log


def _aggregate_metrics(experiment: Path, label: str, dataset: str = "validation") -> dict[str, float]:
    """Read one candidate's aggregate metrics from its Harbor result."""
    result = experiment / "eval-and-optimize" / "results" / f"{label}-{dataset}" / "result.json"
    evaluations = list(json.loads(result.read_text(encoding="utf-8"))["stats"]["evals"].values())
    assert len(evaluations) == 1, f"expected one evaluation in {result}, found {len(evaluations)}"
    return evaluations[0]["metrics"][0]


def _validation_reward(experiment: Path, label: str) -> float:
    """Read one candidate's validation reward from its Harbor result."""
    return float(_aggregate_metrics(experiment, label)["reward"])


def _per_task_rewards(experiment: Path, label: str, dataset: str = "validation") -> dict[str, float]:
    """Read each task reward from one candidate's Harbor result."""
    result_dir = experiment / "eval-and-optimize" / "results" / f"{label}-{dataset}"
    rewards: dict[str, float] = {}
    for trial in sorted(result_dir.glob("*/result.json")):
        payload = json.loads(trial.read_text(encoding="utf-8"))
        rewards[payload["task_name"]] = float(payload["verifier_result"]["rewards"]["reward"])
    return rewards


def _agent_source(experiment: Path, label: str) -> str:
    """Read the saved source for one candidate."""
    return (experiment / "eval-and-optimize" / "agents" / label / "agent.py").read_text(encoding="utf-8")


def _agent_class(experiment: Path, label: str) -> Any:
    """Load one candidate's agent class from its saved source file."""
    os.environ["RECORDS_PATH"] = str(_RECORDS)
    os.environ.setdefault("TRACE_DIR", tempfile.mkdtemp(prefix="smoke-e2e-traces-"))
    path = experiment / "eval-and-optimize" / "agents" / label / "agent.py"
    spec = importlib.util.spec_from_file_location(f"_smoke_e2e_{label}", path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.ReportAgent


def _normalize(text: str) -> str:
    """Normalize line endings the same way the task verifier does."""
    return re.sub(r"\r$", "", text, flags=re.MULTILINE).rstrip("\n")


def _replays_correctly(experiment: Path, label: str, task_dir: Path) -> bool:
    """Check one committed task against a saved candidate."""
    instruction = (task_dir / "instruction.md").read_text(encoding="utf-8").strip()
    expected = (task_dir / "tests" / "expected.txt").read_text(encoding="utf-8")
    actual = _agent_class(experiment, label)().solve(instruction) + "\n"
    return _normalize(actual) == _normalize(expected)


def _winner_label(experiment: Path) -> str:
    """Read the selected winner from the completed run."""
    run = json.loads((experiment / "eval-and-optimize" / "run.json").read_text(encoding="utf-8"))
    winner = run.get("winner_agent")
    assert winner, f"run.json has no winner_agent: {sorted(run)}"
    return str(winner)


def _assert_repair_group(experiment: Path, group: str) -> None:
    """Check that one repair group changed source and passes every held-out task."""
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

    baseline = _validation_reward(experiment, "agent-0")
    improved = _validation_reward(experiment, winner)
    assert improved - baseline >= _REWARD_DELTA_THRESHOLD, (
        f"{group} validation reward {baseline} -> {improved} is below {_REWARD_DELTA_THRESHOLD}"
    )


def _assert_analysis_named_problem(experiment: Path, group: str) -> None:
    """Check that the Analyzer named the weakness measured by one repair group."""
    analyses = sorted((experiment / "eval-and-optimize" / "analysis").glob("round-*.md"))
    assert analyses, f"{group} has no Analyzer output"
    text = " ".join(path.read_text(encoding="utf-8") for path in analyses).lower()
    hits = [term for term in _ROOT_CAUSE_TERMS[group] if term in text]
    assert len(hits) >= _MIN_ROOT_CAUSE_HITS, f"{group} analysis did not name its weakness; matched only {hits}"


def _best_train_metrics(experiment: Path, label: str) -> dict[str, float]:
    """Read the best train aggregate for one candidate."""
    result_dirs = sorted((experiment / "eval-and-optimize" / "results").glob(f"{label}-train*"))
    assert result_dirs, f"no train results for {label}"
    metrics: list[dict[str, float]] = []
    for result_dir in result_dirs:
        evaluations = list(
            json.loads((result_dir / "result.json").read_text(encoding="utf-8"))["stats"]["evals"].values()
        )
        assert len(evaluations) == 1, f"expected one evaluation in {result_dir}"
        metrics.append(evaluations[0]["metrics"][0])
    return max(metrics, key=lambda values: values["reward"])


def _assert_g4_rejected_narrow_fix(experiment: Path) -> None:
    """Check that g4 rejects a train-only fix and keeps the baseline."""
    winner = _winner_label(experiment)
    assert winner == "agent-0", f"g4 selected {winner}; validation did not reject the narrow fix"
    candidates = sorted(
        path.name for path in (experiment / "eval-and-optimize" / "agents").iterdir() if path.name != "agent-0"
    )
    assert candidates, "g4 produced no candidates"
    baseline_train = _best_train_metrics(experiment, "agent-0")["reward"]
    best_candidate = max(candidates, key=lambda label: _best_train_metrics(experiment, label)["reward"])
    best_train = _best_train_metrics(experiment, best_candidate)["reward"]
    assert best_train > baseline_train, f"g4 never improved on train ({baseline_train} -> {best_train})"
    assert _validation_reward(experiment, best_candidate) <= _validation_reward(experiment, "agent-0"), (
        "g4 train winner also improved validation, so the held-out split did not reject it"
    )
    rewards = _per_task_rewards(experiment, "agent-0")
    broken_controls = {task for task in _G4_CONTROL_TASKS if rewards.get(task, 0.0) < 1.0}
    assert not broken_controls, f"g4 baseline controls are failing: {sorted(broken_controls)}"


@pytest.mark.e2e
@pytest.mark.timeout(2400)
@pytest.mark.parametrize("group", ("g1-aggregation", "g2-name-patterns", "g3-long-inputs", "g5-edge-cases"))
def test_repair_groups_improve_validation(
    group: str,
    _e2e_environment: _E2EEnvironment,
    tmp_path: Path,
) -> None:
    """Check that every repair group improves validation from its own agent copy."""
    experiment, _ = _run_group(group, environment=_e2e_environment, artifact_parent=tmp_path / group)
    _assert_repair_group(experiment, group)
    _assert_analysis_named_problem(experiment, group)


@pytest.mark.e2e
@pytest.mark.timeout(1800)
def test_g4_rejects_a_non_generalizing_fix(_e2e_environment: _E2EEnvironment, tmp_path: Path) -> None:
    """Check that g4 retains the baseline after validation rejects a narrow fix."""
    experiment, _ = _run_group(
        "g4-dispatch-order",
        environment=_e2e_environment,
        artifact_parent=tmp_path / "g4-dispatch-order",
        profile_name="optimizer-generalization.yaml",
    )
    _assert_g4_rejected_narrow_fix(experiment)
