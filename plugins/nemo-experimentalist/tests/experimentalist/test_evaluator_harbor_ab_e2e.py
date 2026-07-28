# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live A/B: plain Harbor vs the SDK's ``HarborAgentTaskRunner``.

Everything else in the evaluator suite fakes Harbor's ``Job``. This module runs
the real thing over the bundled ``hello-harbor-agent`` example — Docker builds the
task image, the agent runs in the container, and the verifier writes the rewards —
once through each evaluator type, then asserts the two produce the same trials.

It needs Docker and ``harbor``, and is skipped otherwise. No LLM or network is
involved: the hello agent is stdlib-only and the Experimentalist's own LLM
components (Coder, Analyzer, Proposer) are not in this path.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_agent_task_runner import (
    HarborRunnerConfig,
    HarborRunnerEvaluator,
    harbor_task_names,
)

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.skip_in_ci, pytest.mark.asyncio]

_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "hello-harbor-agent"
_VALIDATION_DIR = _EXAMPLE_DIR / "dataset" / "validation"
_TRAIN_DIR = _EXAMPLE_DIR / "dataset" / "train"

# The baseline agent handles greetings but not arithmetic, so exactly one of the
# two tasks in each split scores; both emit format_ok. See the example README.
# test_hello_example_baseline.py guards this without Docker; here we confirm the
# whole container/verifier pipeline reproduces it.
_EXPECTED_AGGREGATE = {"reward": 0.5, "format_ok": 1.0}


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    # Bounded: `docker info` blocks indefinitely when a credential helper prompts
    # for keychain access in a non-interactive shell, which would hang collection
    # rather than skip the test.
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.fixture(scope="session")
def requires_docker() -> None:
    """Probe Docker once per session.

    Session-scoped on purpose: the probe result cannot change mid-run, and a
    function-scoped fixture would fork `docker info` once per test — paying the
    30s timeout four times over when the daemon is wedged, which is the exact
    hang this bound exists to avoid.
    """
    pytest.importorskip("harbor")
    if not _docker_available():
        pytest.skip("Docker daemon is required to run a Harbor job")


@pytest.fixture
def hello_agent_dir(tmp_path: Path) -> Path:
    """Materialize the example as `agent-0`, the way the loop does."""
    agent_dir = tmp_path / "agents" / "agent-0"
    shutil.copytree(_EXAMPLE_DIR, agent_dir, ignore=shutil.ignore_patterns("dataset", "__pycache__"))
    return agent_dir


async def test_train_split_still_has_a_real_failure_to_diagnose(
    requires_docker: None,
    hello_agent_dir: Path,
    tmp_path: Path,
) -> None:
    """End-to-end proof that the optimizer loop has something to work on.

    The Analyzer/Proposer/Coder round only demonstrates anything if a train task
    actually fails in a container. A baseline that quietly gained an arithmetic
    handler would score 1.0 here and leave the loop with nothing to diagnose.
    """

    result = await HarborRunnerEvaluator(experiment_dir=tmp_path).run(
        hello_agent_dir,
        HarborDataset.from_path(_TRAIN_DIR),
        HarborRunnerConfig(jobs_dir=Path("train-jobs"), quiet=True),
    )

    assert result.aggregate_metrics == pytest.approx(_EXPECTED_AGGREGATE)
    rewards = {trial.task_id: trial.metrics["reward"].value for trial in result.trials}
    assert rewards == {"greet-world": 1.0, "sum-two": 0.0}
    # The failure must be a scored 0, not a crashed trial: the Analyzer reads the
    # trace of a completed-but-wrong run, and an errored trial teaches it nothing.
    assert all(trial.status == "completed" for trial in result.trials)
    assert all(trial.trace is not None for trial in result.trials)


async def test_short_ids_translate_to_the_example_full_harbor_names(requires_docker: None) -> None:
    """The name translation the SDK path depends on, checked against real task.toml files."""
    dataset = HarborDataset.from_path(_VALIDATION_DIR)

    assert harbor_task_names(dataset) == {
        "greet-universe": "hello/greet-universe",
        "sum-three": "hello/sum-three",
    }


async def test_plain_and_sdk_evaluators_agree_on_the_hello_example(
    requires_docker: None,
    hello_agent_dir: Path,
    tmp_path: Path,
    comparable_trials: Any,
) -> None:
    dataset = HarborDataset.from_path(_VALIDATION_DIR)

    plain = await HarborEvaluator(experiment_dir=tmp_path).run(
        hello_agent_dir, dataset, HarborEvaluatorConfig(jobs_dir=Path("plain-jobs"), quiet=True)
    )
    sdk = await HarborRunnerEvaluator(experiment_dir=tmp_path).run(
        hello_agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("sdk-jobs"), quiet=True)
    )

    assert sdk.aggregate_metrics == pytest.approx(_EXPECTED_AGGREGATE)
    assert plain.aggregate_metrics == pytest.approx(_EXPECTED_AGGREGATE)
    assert comparable_trials(sdk.trials) == comparable_trials(plain.trials)

    # Both must cover the same tasks under their short Experimentalist ids, and
    # both must surface traces for the Analyzer to read.
    assert {trial.task_id for trial in sdk.trials} == {"greet-universe", "sum-three"}
    assert all(trial.status == "completed" for trial in sdk.trials)
    assert all(trial.trace is not None for trial in sdk.trials)


async def test_sdk_evaluator_serves_a_complete_run_from_cache(
    requires_docker: None,
    hello_agent_dir: Path,
    tmp_path: Path,
    comparable_trials: Any,
) -> None:
    """A second identical run must re-adapt the job dir instead of rebuilding it."""
    dataset = HarborDataset.from_path(_VALIDATION_DIR)
    evaluator = HarborRunnerEvaluator(experiment_dir=tmp_path)
    options = HarborRunnerConfig(jobs_dir=Path("jobs"), quiet=True)

    first = await evaluator.run(hello_agent_dir, dataset, options)
    job_dir = tmp_path / "jobs" / f"{hello_agent_dir.name}-{dataset.id}"
    # Harbor names each trial dir `<task>__<random>`, so identical dir names across
    # runs is real evidence of reuse. Globbing `.name` would only ever collect
    # {"result.json"} and pass no matter what the second run did.
    trial_dirs = {path.parent.name for path in job_dir.glob("*/result.json")}
    assert trial_dirs, "the first run must have written trial directories"

    cached = await evaluator.run(hello_agent_dir, dataset, options)

    assert comparable_trials(cached.trials) == comparable_trials(first.trials)
    assert {path.parent.name for path in job_dir.glob("*/result.json")} == trial_dirs

    # force_rerun must beat the cache: the old job dir is discarded, so Harbor
    # mints new randomly-suffixed trial dirs while the scores stay the same.
    rerun = await evaluator.run(hello_agent_dir, dataset, options.model_copy(update={"force_rerun": True}))
    assert rerun.aggregate_metrics == pytest.approx(_EXPECTED_AGGREGATE)
    assert {path.parent.name for path in job_dir.glob("*/result.json")}.isdisjoint(trial_dirs)
