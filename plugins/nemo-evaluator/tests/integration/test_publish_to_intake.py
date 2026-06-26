# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test: publish_to_intake against a live Intake + ClickHouse.

Marked ``integration`` (auto-applied to ``/integration/`` paths), so it runs under
``make test-integration`` / ``-m integration`` and is excluded from the unit suite.
Session fixtures stand up ClickHouse (Docker) and the platform
(``auth,entities,intake``); the test skips cleanly when Docker is unavailable.

Run directly::

    uv run pytest plugins/nemo-evaluator/tests/integration/test_publish_to_intake.py -v

Requires Docker (Intake is ClickHouse-backed) and a free :8080 / :8123.
"""

from __future__ import annotations

import math
import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from importlib.util import find_spec
from pathlib import Path

import pytest
from nemo_evaluator.intake.publish import publish_to_intake
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.metrics.protocol import MetricOutput
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.intake.trace_filter_param import TraceFilterParam

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[4]
BASE_URL = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
WORKSPACE = "default"
GROUP_NAME = "intake-it-group"
EXPERIMENT_NAME = "intake-it-exp"
RUN_ID = "intake-it-run"
NAN_EXPERIMENT_NAME = "intake-it-nan-exp"
NAN_RUN_ID = "intake-it-nan-run"
CLICKHOUSE_CONTAINER = "nmp-intake-clickhouse"


def _docker_available() -> bool:
    if find_spec("docker") is None:
        return False
    from docker.errors import DockerException

    import docker

    try:
        client = docker.from_env()
        try:
            client.ping()
        finally:
            client.close()
        return True
    except (DockerException, OSError):
        return False


def _wait_for_tcp(host: str, port: int, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(1)
    raise RuntimeError(f"{host}:{port} not reachable within {timeout}s")


def _wait_for_ready(base_url: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health/ready", timeout=2) as response:  # noqa: S310
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(2)
    raise RuntimeError(f"platform at {base_url} not ready within {timeout}s")


@pytest.fixture(scope="session")
def _clickhouse() -> Iterator[None]:
    if not _docker_available():
        pytest.skip("Docker not available; required for ClickHouse-backed Intake")
    subprocess.run(
        ["bash", str(REPO_ROOT / "services/intake/scripts/spans/run_clickhouse.sh")],
        check=True,
        cwd=REPO_ROOT,
    )
    try:
        _wait_for_tcp("localhost", 8123, timeout=60)
        yield
    finally:
        subprocess.run(["docker", "rm", "-f", CLICKHOUSE_CONTAINER], check=False)


@pytest.fixture(scope="session")
def platform_base_url(_clickhouse: None) -> Iterator[str]:
    process = subprocess.Popen(
        ["uv", "run", "nemo", "services", "run", "--services", "auth,entities,intake"],
        cwd=REPO_ROOT,
        env={**os.environ, "NMP_BASE_URL": BASE_URL},
    )
    try:
        _wait_for_ready(BASE_URL, timeout=180)
        yield BASE_URL
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()


def _result() -> AgentEvalResult:
    trials = [
        AgentEvalTrial(
            id="trial-1",
            task_id="task-1",
            status=AgentEvalTrialStatus.COMPLETED,
            output=AgentOutput(output_text="The capital of France is Paris."),
        ),
        AgentEvalTrial(
            id="trial-2",
            task_id="task-2",
            status=AgentEvalTrialStatus.COMPLETED,
            output=AgentOutput(output_text="2 + 2 = 4."),
        ),
    ]
    scores = [
        AgentEvalTaskScore(
            id="score-1",
            run_id=RUN_ID,
            task_id="task-1",
            trial_id="trial-1",
            metric_type="accuracy",
            status=AgentEvalScoreStatus.COMPLETED,
            outputs=[MetricOutput(name="score", value=1.0), MetricOutput(name="passed", value=True)],
        ),
        AgentEvalTaskScore(
            id="score-2",
            run_id=RUN_ID,
            task_id="task-1",
            trial_id="trial-1",
            metric_type="judge",
            status=AgentEvalScoreStatus.COMPLETED,
            outputs=[MetricOutput(name="verdict", value="correct")],
        ),
        AgentEvalTaskScore(
            id="score-3",
            run_id=RUN_ID,
            task_id="task-2",
            trial_id="trial-2",
            metric_type="accuracy",
            status=AgentEvalScoreStatus.COMPLETED,
            outputs=[MetricOutput(name="score", value=0.0), MetricOutput(name="passed", value=False)],
        ),
    ]
    return AgentEvalResult(run_id=RUN_ID, tasks=[], trials=trials, scores=scores, summary=AgentEvalSummary())


async def test_publish_to_intake_round_trip(platform_base_url: str) -> None:
    async with AsyncNeMoPlatform(base_url=platform_base_url, max_retries=2) as client:
        # Precondition: the Experiment must exist before ingest.
        group = await client.experiment_groups.create(
            workspace=WORKSPACE, name=GROUP_NAME, description="Intake IT", exist_ok=True
        )
        await client.experiments.create(
            workspace=WORKSPACE,
            name=EXPERIMENT_NAME,
            experiment_group_id=group.id,
            dataset_name="intake-it-dataset",
            dataset_version="v1",
            exist_ok=True,
        )

        report = await publish_to_intake(
            _result(),
            platform=client,
            experiment_id=EXPERIMENT_NAME,
            workspace=WORKSPACE,
            agent_name="intake-it-agent",
            model_name="intake-it-model",
        )

        assert report.trial_count == 2
        assert report.evaluator_result_count == 5
        published = {trial.trial_id: trial for trial in report.published_trials}

        # --- trial-1: trajectory + experiment-context propagation, read back via the Intake API.
        t1 = published["trial-1"]
        trace_filter: TraceFilterParam = {"session_id": t1.session_id}
        traces = [trace async for trace in client.intake.traces.list(workspace=WORKSPACE, filter=trace_filter)]
        assert len(traces) == 1
        trace = traces[0]
        assert trace.session_id == t1.session_id
        assert trace.root_span_id == t1.span_id
        assert trace.experiment_context is not None
        assert trace.experiment_context.experiment_id == EXPERIMENT_NAME
        assert trace.experiment_context.test_case_id == "task-1"

        # --- trial-1 scores: every field, every data_type coercion.
        rows = await client.intake.spans.evaluator_results.list(t1.span_id, workspace=WORKSPACE)
        by_name = {row.name: row for row in rows}
        assert set(by_name) == {"accuracy.score", "accuracy.passed", "judge.verdict"}
        for row in rows:
            assert row.session_id == t1.session_id
            assert row.span_id == t1.span_id
            assert row.workspace == WORKSPACE
        assert by_name["accuracy.score"].data_type == "NUMERIC"
        assert by_name["accuracy.score"].value == 1.0
        assert by_name["accuracy.passed"].data_type == "BOOLEAN"
        assert by_name["accuracy.passed"].value == 1.0
        assert by_name["judge.verdict"].data_type == "TEXT"
        assert by_name["judge.verdict"].string_value == "correct"

        # --- trial-2: distinct session/span; BOOLEAN false coerces to 0.0.
        t2 = published["trial-2"]
        assert t2.session_id != t1.session_id
        assert t2.span_id != t1.span_id
        rows2 = await client.intake.spans.evaluator_results.list(t2.span_id, workspace=WORKSPACE)
        by_name2 = {row.name: row for row in rows2}
        assert set(by_name2) == {"accuracy.score", "accuracy.passed"}
        assert by_name2["accuracy.passed"].data_type == "BOOLEAN"
        assert by_name2["accuracy.passed"].value == 0.0
        assert by_name2["accuracy.score"].value == 0.0


def _nan_result() -> AgentEvalResult:
    """A result with a NaN-valued output and a FAILED score alongside one valid score."""
    trial = AgentEvalTrial(
        id="trial-1",
        task_id="task-1",
        status=AgentEvalTrialStatus.COMPLETED,
        output=AgentOutput(output_text="answer"),
    )
    scores = [
        AgentEvalTaskScore(
            id="score-ok",
            run_id=NAN_RUN_ID,
            task_id="task-1",
            trial_id="trial-1",
            metric_type="accuracy",
            status=AgentEvalScoreStatus.COMPLETED,
            outputs=[MetricOutput(name="score", value=0.5), MetricOutput(name="broken", value=math.nan)],
        ),
        AgentEvalTaskScore(
            id="score-failed",
            run_id=NAN_RUN_ID,
            task_id="task-1",
            trial_id="trial-1",
            metric_type="judge",
            status=AgentEvalScoreStatus.FAILED,
            outputs=[MetricOutput(name="verdict", value=math.nan)],
        ),
    ]
    return AgentEvalResult(run_id=NAN_RUN_ID, tasks=[], trials=[trial], scores=scores, summary=AgentEvalSummary())


async def test_publish_skips_nan_and_failed_scores(platform_base_url: str) -> None:
    # A NaN value is not representable in JSON and a FAILED score is not a real measurement; neither
    # should reach Intake. Only the finite, completed output should be stored.
    async with AsyncNeMoPlatform(base_url=platform_base_url, max_retries=2) as client:
        group = await client.experiment_groups.create(workspace=WORKSPACE, name=GROUP_NAME, exist_ok=True)
        await client.experiments.create(
            workspace=WORKSPACE,
            name=NAN_EXPERIMENT_NAME,
            experiment_group_id=group.id,
            dataset_name="intake-it-nan-dataset",
            dataset_version="v1",
            exist_ok=True,
        )

        report = await publish_to_intake(
            _nan_result(),
            platform=client,
            experiment_id=NAN_EXPERIMENT_NAME,
            workspace=WORKSPACE,
            agent_name="intake-it-agent",
        )

        published = report.published_trials[0]
        rows = await client.intake.spans.evaluator_results.list(published.span_id, workspace=WORKSPACE)
        assert {row.name for row in rows} == {"accuracy.score"}
        assert report.evaluator_result_count == 1

        # The dropped outputs are surfaced (not silently lost) until Intake can model failure.
        assert {(skip.name, skip.reason) for skip in report.skipped} == {
            ("accuracy.broken", "non-finite value"),
            ("judge.verdict", "scoring failed"),
        }
