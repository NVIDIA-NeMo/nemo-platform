# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the agent-evaluation job (AALGO-297).

These exercise the job against *real* execution seams, across the dimensions that
matter for this work:

* target type — a Codex *runner*, plus Model and Agent endpoint targets pointed at an
  IGW mock provider (canned response, so no real model or key);
* metric form — an inline metric bundle, plus a stored ``MetricRef`` resolved against
  the live entity store;
* execution mode — in-process ``run_local`` and service-side ``submit`` on both the
  subprocess and docker backends, against the session ``subprocess_platform`` /
  ``docker_platform`` fixtures in ``conftest.py``. (Docker submit is xfail today — the
  cpu-tasks image predates this work; tracked in AALGO-301.)

Marked ``integration`` (auto-applied to ``/integration/`` paths). Codex-dependent tests
gate on ``@requires_codex`` (skip when the ``codex`` CLI is absent, needs a logged-in
ChatGPT account); Model/Agent tests need only the running platform's IGW.

Run directly::

    uv run pytest plugins/nemo-evaluator/tests/integration/test_agent_evaluate_job.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

import cloudpickle
import httpx
import pytest
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.jobs.agent_evaluate import AgentEvalJob
from nemo_evaluator.jobs.agent_spec import (
    AgentEvalInputSpec,
    AgentEvalTaskInput,
    AgentTarget,
    CodexRunnerTarget,
    ModelTarget,
)
from nemo_evaluator.metric_refs import MetricRef
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.enums import AgentFormat, ModelFormat
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import Agent, Model, RunConfigOnline, RunConfigOnlineModel
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.scheduler import NemoJobScheduler
from nmp.testing import add_mock_provider
from nmp.testing.e2e import wait_for_platform_job

#: Opt-in: these tests spin real ``nemo services`` platforms (subprocess/docker/auth) and some need
#: a local ``codex`` CLI + login, so they're kept out of the standard CI integration job. Run them
#: locally (or on demand) with ``RUN_AGENT_EVAL_INTEGRATION=1``.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("RUN_AGENT_EVAL_INTEGRATION"),
        reason="opt-in; set RUN_AGENT_EVAL_INTEGRATION=1 to run (spins real nemo services platforms)",
    ),
]

#: Codex model the runner drives. ChatGPT-account dependent; gpt-5.5 is known-good.
CODEX_MODEL = "gpt-5.5"

WORKSPACE = "default"

#: Headers a job's task SDK carries (mirrors ``get_task_sdk``): an internal service principal the
#: default PDP policy grants full permissions. Authenticates test-side calls against the
#: auth-enabled platform without standing up OIDC.
SERVICE_PRINCIPAL_HEADERS = {"X-NMP-Principal-Id": "service:evaluator", "X-NMP-Internal": "true"}


def _codex_available() -> bool:
    return shutil.which("codex") is not None


requires_codex = pytest.mark.skipif(not _codex_available(), reason="codex CLI not on PATH")


# Pickle metrics defined in this test module BY VALUE so the cloudpickle bundle embeds the class
# itself — the submit-backend task runs in a subprocess that can't import this test module, and a
# by-reference pickle would fail to hydrate there.
cloudpickle.register_pickle_by_value(sys.modules[__name__])


class _OutputContainsMetric:
    """Custom metric: scores 1.0 iff the trial's output contains the expected token (case-insensitive).

    Validates what the agent actually produced — unlike a built-in clean-exit signal — and exercises
    the inline user-defined-metric path end to end (bundled, shipped in the spec, hydrated at run time).
    """

    def __init__(self, expected: str) -> None:
        self.expected = expected

    @property
    def type(self) -> str:
        return "output-contains"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.boolean("contains")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:  # noqa: A002
        text = input.candidate.output_text or ""
        return MetricResult(outputs=[MetricOutput(name="contains", value=self.expected.lower() in text.lower())])


def _output_contains_metric(expected: str) -> MetricInline:
    """An inline, user-defined metric that validates the agent's output text."""
    bundle = bundle_metric(_OutputContainsMetric(expected), CloudpickleMetricBundlePackager())
    return MetricInline.model_validate(bundle.model_dump(mode="json"))


def _bundle_dir(run_result: dict) -> Path:
    """The persisted run bundle directory (trials/scores/summary) from a run_local result."""
    return Path(run_result["artifact"]["artifact_url"].removeprefix("file://"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _chat_completion(content: str) -> dict:
    """An OpenAI ``chat.completion`` response body whose assistant message is ``content``."""
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _igw_chat_url(base_url: str, model_entity: str) -> str:
    """OpenAI-compatible chat URL for a model entity routed through the platform's IGW."""
    return f"{base_url}/apis/inference-gateway/v2/workspaces/{WORKSPACE}/model/{model_entity}/-/v1/chat/completions"


def _unique(prefix: str) -> str:
    """A unique entity name, so a rerun (e.g. pytest-rerunfailures) doesn't 409 on an existing one."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.mark.timeout(300)
def test_run_local_model_target_scores_a_real_trial(subprocess_platform: str) -> None:
    # dim 1 (Model endpoint target): generate a trial against an IGW mock provider that returns
    # "DONE" (no real model/key), then score the trial output with the inline metric.
    sdk = NeMoPlatform(base_url=subprocess_platform, max_retries=2)
    sdk.workspaces.create(name=WORKSPACE, exist_ok=True)
    model_name = _unique("model-judge")
    add_mock_provider(sdk, workspace=WORKSPACE, name=model_name, mock_response_body=_chat_completion("DONE"))

    input_spec = AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="ask",
                intent="Obtain a one-word reply from the model.",
                inputs={"prompt": "Reply with the single word DONE and nothing else."},
                metrics=[_output_contains_metric("DONE")],
            )
        ],
        target=ModelTarget(
            model=Model(
                url=_igw_chat_url(subprocess_platform, model_name), name=model_name, format=ModelFormat.OPEN_AI
            ),
            prompt_template={"messages": [{"role": "user", "content": "{{item.prompt}}"}]},
            params=RunConfigOnlineModel(),
        ),
    )

    result = NemoJobScheduler().run_local(AgentEvalJob, input_spec.model_dump(mode="json"))

    assert result["status"] == "completed"
    bundle = _bundle_dir(result)
    trials = _read_jsonl(bundle / "trials.jsonl")
    assert trials[0]["output"]["output_text"] == "DONE"
    scores = _read_jsonl(bundle / "scores.jsonl")
    assert scores[0]["outputs"][0]["value"] in (True, 1.0)


@pytest.mark.timeout(300)
def test_run_local_agent_target_scores_a_real_trial(subprocess_platform: str) -> None:
    # dim 1 (Agent endpoint target): a generic-HTTP agent posts to an IGW mock provider returning
    # "DONE"; response_path extracts the assistant content, then the inline metric scores it.
    sdk = NeMoPlatform(base_url=subprocess_platform, max_retries=2)
    sdk.workspaces.create(name=WORKSPACE, exist_ok=True)
    agent_name = _unique("agent-judge")
    add_mock_provider(sdk, workspace=WORKSPACE, name=agent_name, mock_response_body=_chat_completion("DONE"))

    agent = Agent(
        url=_igw_chat_url(subprocess_platform, agent_name),
        name=agent_name,
        format=AgentFormat.GENERIC,
        body={"model": agent_name, "messages": [{"role": "user", "content": "Reply with DONE."}]},
        response_path="$.choices[0].message.content",
    )
    input_spec = AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="ask",
                intent="Obtain a one-word reply from the agent.",
                inputs={"prompt": "Reply with the single word DONE and nothing else."},
                metrics=[_output_contains_metric("DONE")],
            )
        ],
        target=AgentTarget(agent=agent, params=RunConfigOnline()),
    )

    result = NemoJobScheduler().run_local(AgentEvalJob, input_spec.model_dump(mode="json"))

    assert result["status"] == "completed"
    bundle = _bundle_dir(result)
    trials = _read_jsonl(bundle / "trials.jsonl")
    assert trials[0]["output"]["output_text"] == "DONE"
    scores = _read_jsonl(bundle / "scores.jsonl")
    assert scores[0]["outputs"][0]["value"] in (True, 1.0)


@requires_codex
@pytest.mark.timeout(300)
def test_run_local_codex_runner_scores_a_real_trial() -> None:
    # One real Codex run covering dim 1 (runner) x dim 2 (inline metric) x dim 3 (run): the CLI
    # produces a trial and a user-defined inline metric scores its output. (Every task must declare
    # >=1 metric — the SDK evaluator rejects a metric-less task — so this is the minimal real run.)
    input_spec = AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="say-done",
                intent="Agent follows a trivial instruction and exits cleanly.",
                inputs={"instruction": "Reply with the single word DONE and nothing else."},
                metrics=[_output_contains_metric("DONE")],
            )
        ],
        target=CodexRunnerTarget(model=CODEX_MODEL),
    )

    result = NemoJobScheduler().run_local(AgentEvalJob, input_spec.model_dump(mode="json"))

    assert result["status"] == "completed"
    bundle = _bundle_dir(result)

    trials = _read_jsonl(bundle / "trials.jsonl")
    assert len(trials) == 1
    assert trials[0]["task_id"] == "say-done"
    assert trials[0]["status"] == "completed"

    scores = _read_jsonl(bundle / "scores.jsonl")
    assert [score["metric_type"] for score in scores] == ["output-contains"]
    assert scores[0]["trial_id"] == trials[0]["id"]
    # The custom metric actually validated the agent's output (it replied "DONE").
    output = scores[0]["outputs"][0]
    assert output["name"] == "contains"
    assert output["value"] in (True, 1.0)


# --- submit: service-side execution -----------------------------------------


def _offline_trials_input_spec() -> dict:
    """Submitter-facing spec: one precomputed trial scored offline by one inline metric.

    No target — so no online generation, no codex, no IGW. Runs entirely inside the task container,
    isolating the docker-backend-wiring + entrypoint condition (rather than also depending on a codex
    CLI/auth the image doesn't carry)."""
    return AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="say-done",
                intent="Agent follows a trivial instruction and exits cleanly.",
                inputs={"instruction": "Reply with the single word DONE and nothing else."},
                metrics=[_output_contains_metric("DONE")],
            )
        ],
        trials=[
            AgentEvalTrial(
                id="t-1",
                task_id="say-done",
                status=AgentEvalTrialStatus.COMPLETED,
                output=AgentOutput(output_text="DONE"),
            )
        ],
    ).model_dump(mode="json")


def _codex_eval_input_spec() -> dict:
    """Submitter-facing spec: one Codex-runner task scored by one inline metric."""
    return AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="say-done",
                intent="Agent follows a trivial instruction and exits cleanly.",
                inputs={"instruction": "Reply with the single word DONE and nothing else."},
                metrics=[_output_contains_metric("DONE")],
            )
        ],
        target=CodexRunnerTarget(model=CODEX_MODEL),
    ).model_dump(mode="json")


@requires_codex
@pytest.mark.timeout(600)
def test_submit_to_subprocess_backend_runs_agent_eval(subprocess_platform: str) -> None:
    # dim 3 (submit) x dim 4 (subprocess backend): submit through the plugin route; the jobs service
    # compiles + runs the task as a host subprocess (which has codex), to completion.
    client = NeMoPlatform(base_url=subprocess_platform, max_retries=2)
    client.workspaces.create(name=WORKSPACE, exist_ok=True)

    response = NemoJobScheduler().submit_remote(
        AgentEvalJob,
        _codex_eval_input_spec(),
        base_url=subprocess_platform,
        workspace=WORKSPACE,
        profile="default",
    )
    job_name = response.get("name") or response.get("id")
    assert job_name, f"submit response carried no job name/id: {response}"

    job = wait_for_platform_job(client, job_name, WORKSPACE, timeout=480)
    assert job.status == "completed", f"job {job_name} ended {job.status!r}: {getattr(job, 'status_details', None)}"


@requires_codex
@pytest.mark.timeout(600)
def test_submit_with_stored_metric_ref_resolves_and_scores(subprocess_platform: str) -> None:
    # dim 2 (stored MetricRef): store a metric in the platform, reference it by name, and submit.
    # The server-side to_spec must resolve the ref against the live entity store + files service
    # (not an inline bundle) before the job runs.
    client = NeMoPlatform(base_url=subprocess_platform, max_retries=2)
    client.workspaces.create(name=WORKSPACE, exist_ok=True)

    metric_name = _unique("done-contains")
    stored = _output_contains_metric("DONE")
    create = httpx.post(
        f"{subprocess_platform}/apis/evaluator/v2/workspaces/{WORKSPACE}/metrics/{metric_name}",
        content=stored.model_dump_json(),
        headers={"content-type": "application/json"},
        timeout=30,
    )
    assert create.status_code in (200, 201), f"metric create failed: {create.status_code} {create.text}"

    spec = AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="say-done",
                intent="Agent follows a trivial instruction and exits cleanly.",
                inputs={"instruction": "Reply with the single word DONE and nothing else."},
                metrics=[MetricRef(f"{WORKSPACE}/{metric_name}")],
            )
        ],
        target=CodexRunnerTarget(model=CODEX_MODEL),
    ).model_dump(mode="json")

    response = NemoJobScheduler().submit_remote(
        AgentEvalJob, spec, base_url=subprocess_platform, workspace=WORKSPACE, profile="default"
    )
    job_name = response.get("name") or response.get("id")
    assert job_name, f"submit response carried no job name/id: {response}"

    job = wait_for_platform_job(client, job_name, WORKSPACE, timeout=480)
    assert job.status == "completed", f"job {job_name} ended {job.status!r}: {getattr(job, 'status_details', None)}"


@pytest.mark.timeout(420)
def test_submit_model_target_under_auth_forwards_identity_to_igw(auth_subprocess_platform: str) -> None:
    # dim 1 (Model target) x dim 3 (submit) under auth.enabled: the submitted task's get_task_sdk
    # identity (X-NMP-Principal-Id: service:evaluator) must be forwarded to the evaluator's IGW
    # inference client (AgentEvalJob._build_evaluator) — otherwise the IGW returns 401 and the job
    # fails. A clean completion proves the forwarded service-principal headers authenticate online
    # inference under auth, with no bearer. (Probed directly too: service headers -> 200, none -> 401.)
    # No codex: the target is an IGW mock provider, so this runs without the runner toolchain.
    sdk = NeMoPlatform(base_url=auth_subprocess_platform, default_headers=SERVICE_PRINCIPAL_HEADERS, max_retries=2)
    sdk.workspaces.create(name=WORKSPACE, exist_ok=True)
    model_name = _unique("auth-model")
    add_mock_provider(sdk, workspace=WORKSPACE, name=model_name, mock_response_body=_chat_completion("DONE"))

    spec = AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="ask",
                intent="Obtain a one-word reply from the model.",
                inputs={"prompt": "Reply with the single word DONE and nothing else."},
                metrics=[_output_contains_metric("DONE")],
            )
        ],
        target=ModelTarget(
            model=Model(
                url=_igw_chat_url(auth_subprocess_platform, model_name), name=model_name, format=ModelFormat.OPEN_AI
            ),
            prompt_template={"messages": [{"role": "user", "content": "{{item.prompt}}"}]},
            params=RunConfigOnlineModel(),
        ),
    ).model_dump(mode="json")

    response = NemoJobScheduler().submit_remote(
        AgentEvalJob,
        spec,
        base_url=auth_subprocess_platform,
        workspace=WORKSPACE,
        profile="default",
        headers=SERVICE_PRINCIPAL_HEADERS,
    )
    job_name = response.get("name") or response.get("id")
    assert job_name, f"submit response carried no job name/id: {response}"

    job = wait_for_platform_job(sdk, job_name, WORKSPACE, timeout=360)
    assert job.status == "completed", f"job {job_name} ended {job.status!r}: {getattr(job, 'status_details', None)}"


@pytest.mark.timeout(600)
@pytest.mark.xfail(
    reason="agent-eval can't run under the docker backend until the cpu-tasks image is rebuilt with "
    "this work: the published image predates the nemo_evaluator.tasks.agent_evaluate entrypoint "
    "(container exits with ModuleNotFoundError). This submits an offline trials spec (no online "
    "generation, no codex, no IGW), so the stale image is the only remaining failure cause — the "
    "xfail flips the moment the image ships the entrypoint. Tracked in AALGO-301.",
    strict=False,
)
def test_submit_to_docker_backend_runs_agent_eval(docker_platform: str) -> None:
    # dim 4 (docker backend): the platform routes cpu/default to the docker backend (no subprocess
    # executor is registered, so the step isn't rerouted), so the agent-eval task runs in the
    # cpu-tasks container. Verified to genuinely reach the docker backend (it creates a container
    # from the cpu-tasks image); it fails today because that image predates this work — hence xfail.
    # An offline trials spec keeps the task self-contained in-container, so this isolates the
    # backend-wiring + entrypoint condition rather than also depending on a codex CLI/auth.
    client = NeMoPlatform(base_url=docker_platform, max_retries=2)
    client.workspaces.create(name=WORKSPACE, exist_ok=True)

    response = NemoJobScheduler().submit_remote(
        AgentEvalJob,
        _offline_trials_input_spec(),
        base_url=docker_platform,
        workspace=WORKSPACE,
        profile="default",
    )
    job_name = response.get("name") or response.get("id")
    assert job_name, f"submit response carried no job name/id: {response}"

    job = wait_for_platform_job(client, job_name, WORKSPACE, timeout=480)
    assert job.status == "completed"
