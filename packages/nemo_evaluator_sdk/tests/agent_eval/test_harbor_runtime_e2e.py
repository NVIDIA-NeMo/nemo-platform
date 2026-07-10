# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end test that the SDK runs Harbor's hello-world example natively.

Unlike ``test_harbor_runtime.py`` (which adapts a fabricated job dir with no
Docker), this drives a real Harbor job over the bundled ``hello_world_task``
using the deterministic oracle agent, then scores it through the SDK. It needs
both ``harbor`` installed and a working Docker daemon, and is skipped otherwise.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import reward_payload_from_result
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.skip_in_ci]

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "harbor" / "run_harbor_example.py"


def _load_example():
    spec = importlib.util.spec_from_file_location("harbor_example", _EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.asyncio
async def test_sdk_runs_harbor_hello_world_natively(tmp_path: Path) -> None:
    pytest.importorskip("harbor")
    if not _docker_available():
        pytest.skip("Docker daemon is required to run a Harbor job")

    example = _load_example()
    runner, tasks = example.build_hello_world_job_runner(tmp_path / "jobs")

    result = await AgentEvaluator().run(
        tasks=tasks,
        target=runner,
        config=AgentEvalRunConfig(write_dashboard=False),
    )

    # The oracle agent writes hello.txt, so the verifier reward is 1.0 and the
    # trial completes cleanly through the SDK's Harbor adapter.
    assert len(result.trials) == 1
    trial = result.trials[0]
    assert trial.task_id == example.HELLO_WORLD_TASK_NAME
    assert trial.status == AgentEvalTrialStatus.COMPLETED
    assert trial.metadata["reward"] == 1.0

    rewards = {score.task_id: score.outputs[0].value for score in result.scores if score.outputs}
    assert rewards == {example.HELLO_WORLD_TASK_NAME: 1.0}

    # Harbor really wrote a per-trial result.json under the job dir.
    trial_results = list((tmp_path / "jobs").glob("*/*/result.json"))
    assert trial_results, "Harbor did not write a per-trial result.json"
    assert json.loads(trial_results[0].read_text())["task_name"] == example.HELLO_WORLD_TASK_NAME

    # The optimizer-facing legacy payload reconstructs from the same result.
    payload = reward_payload_from_result(result)
    assert payload["reward"]["harbor_reward.reward"] == 1.0
    assert payload["exceptions"] == {}
