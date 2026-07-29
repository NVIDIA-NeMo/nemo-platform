# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end test that the SDK runs Harbor's hello-world example natively.

Unlike ``test_harbor_runtime.py`` (which adapts a fabricated job dir with no
Docker), this drives a real Harbor job over the bundled ``hello_world_dataset``
using the deterministic oracle agent through the one-call ``run_harbor_eval``
entry point, then checks the scores. It needs both ``harbor`` installed and a
working Docker daemon, and is skipped otherwise.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
    HarborRuntimeConfig,
    reward_payload_from_result,
    run_harbor_eval,
)
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.skip_in_ci]

_DATASET_DIR = Path(__file__).resolve().parents[2] / "examples" / "harbor" / "hello_world_dataset"
_TASK_NAME = "harbor/hello-world"

# Minimal BaseAgent for the resume probe. Satisfies the bundled hello-world verifier,
# which passes iff /app/hello.txt contains exactly "Hello, world!".
_RESUME_PROBE_AGENT = """\
from harbor import BaseAgent


class WrappedAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "resume-probe"

    def version(self) -> str | None:
        return "1.0.0"

    async def setup(self, environment) -> None:
        return None

    async def run(self, instruction, environment, context) -> None:
        await environment.exec("printf 'Hello, world!' > /app/hello.txt")
"""


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.asyncio
async def test_sdk_runs_harbor_hello_world_natively(tmp_path: Path) -> None:
    pytest.importorskip("harbor")
    if not _docker_available():
        pytest.skip("Docker daemon is required to run a Harbor job")

    # The whole caller side: a config and one call — no JobConfig, no harbor import.
    jobs_dir = tmp_path / "jobs"
    config = HarborRuntimeConfig(jobs_dir=jobs_dir, agent_name="oracle")
    result = await run_harbor_eval(config, _DATASET_DIR)

    # The oracle agent writes hello.txt, so the verifier reward is 1.0 and the
    # trial completes cleanly through the SDK's Harbor adapter.
    assert len(result.trials) == 1
    trial = result.trials[0]
    assert trial.task_id == _TASK_NAME
    assert trial.status == AgentEvalTrialStatus.COMPLETED
    assert trial.metadata["reward"] == 1.0

    rewards = {score.task_id: score.outputs[0].value for score in result.scores if score.outputs}
    assert rewards == {_TASK_NAME: 1.0}

    # Harbor really wrote a per-trial result.json under the job dir.
    trial_results = list(jobs_dir.glob("*/*/result.json"))
    assert trial_results, "Harbor did not write a per-trial result.json"
    assert json.loads(trial_results[0].read_text())["task_name"] == _TASK_NAME

    # The optimizer-facing legacy payload reconstructs from the same result.
    payload = reward_payload_from_result(result)
    assert payload["reward"]["harbor_reward.reward"] == 1.0
    assert payload["exceptions"] == {}


@pytest.mark.asyncio
async def test_harbor_resumes_a_partial_job_with_a_custom_agent_dir(tmp_path: Path) -> None:
    """Regression for AALGO-430 — a real Harbor resume with ``agent_dir`` set.

    This is the case every faked-``Job`` test misses, and the reason the bug went
    unnoticed: the scoped agent import path used to carry a fresh uuid per run, so
    Harbor's ``JobConfig`` comparison failed on the second call and it raised
    ``FileExistsError`` rather than resuming. Now the path is content-addressed, so
    an unchanged agent resumes and only the missing trial is re-run.
    """
    pytest.importorskip("harbor")
    if not _docker_available():
        pytest.skip("Docker daemon is required to run a Harbor job")

    # A loose wrapper file next to the dataset — the shape `agent_dir` exists for,
    # and the shape the Experimentalist always uses.
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "harbor_wrapper.py").write_text(_RESUME_PROBE_AGENT, encoding="utf-8")

    jobs_dir = tmp_path / "jobs"
    config = HarborRuntimeConfig(
        jobs_dir=jobs_dir,
        job_name="resume-job",  # pinned: the cache and Harbor's resume both need it
        agent_import_path="harbor_wrapper:WrappedAgent",
        agent_dir=agent_dir,
    )

    first = await run_harbor_eval(config, _DATASET_DIR)
    assert [trial.status for trial in first.trials] == [AgentEvalTrialStatus.COMPLETED]

    job_dir = jobs_dir / "resume-job"
    trial_dirs = {path.parent.name for path in job_dir.glob("*/result.json")}
    assert trial_dirs, "the first run must have written a trial"

    # Drop the only trial's result so the job is under-covered, leaving the job dir
    # (and its config.json) in place — the exact state that used to raise.
    for path in job_dir.glob("*/result.json"):
        path.unlink()

    second = await run_harbor_eval(config, _DATASET_DIR)

    assert [trial.status for trial in second.trials] == [AgentEvalTrialStatus.COMPLETED]
    assert second.trials[0].task_id == _TASK_NAME
    assert second.trials[0].metadata["reward"] == 1.0
