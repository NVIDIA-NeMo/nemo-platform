# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for collecting Gym rollouts from a sandboxed host rather than the local ``gym`` CLI.

The host is faked at the HTTP boundary; everything on this side of it is the real path -- real
tasks from :func:`discover_gym_tasks`, the real dataset materialization, and the real rollout
parser. That is deliberate: the runner's whole claim is that only the *collection* step differs
from the CLI runner, so the test exercises the parts that are supposed to be shared.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.gym import discover_gym_tasks
from nemo_evaluator_sdk.agent_eval.runtimes.gym.records import NG_ROLLOUT_INDEX, NG_TASK_INDEX
from nemo_evaluator_sdk.agent_eval.runtimes.gym.sandboxed import (
    PROXY_AUTH_HEADER,
    SandboxedGymAgentTaskRunner,
    SandboxedGymRuntimeConfig,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig

ROLLOUT_URL = "http://gym-host.example/rollouts/run"


@pytest.fixture
def tasks(tmp_path: Path) -> list:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps({"responses_create_params": {"input": "What is 2 + 2?"}})
        + "\n"
        + json.dumps({"responses_create_params": {"input": "Capital of France?"}})
        + "\n",
        encoding="utf-8",
    )
    return discover_gym_tasks(dataset)


class _FakeHost:
    """Records what was posted and answers with rollout records keyed by the caller's own index."""

    def __init__(
        self,
        status: int = 200,
        body: Any = None,
        content: bytes | None = None,
        rewards: dict[int, float] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.posted: list[dict[str, Any]] = []
        self._status = status
        self._body = body
        self._content = content
        self._rewards = rewards

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            self.posted = json.loads(request.content.decode())["examples"]
            if self._content is not None:
                return httpx.Response(self._status, content=self._content)
            if self._body is not None or self._status >= 400:
                return httpx.Response(self._status, json=self._body if self._body is not None else {"error": "boom"})
            rewards = self._rewards if self._rewards is not None else {}
            results = [
                {
                    NG_TASK_INDEX: example[NG_TASK_INDEX],
                    NG_ROLLOUT_INDEX: 0,
                    "reward": rewards.get(example[NG_TASK_INDEX], 1.0),
                    "response": f"answer-{example[NG_TASK_INDEX]}",
                }
                for example in self.posted
            ]
            return httpx.Response(200, json={"results": results})

        return httpx.MockTransport(handle)


def bind_http_transport(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    """Point ``httpx.AsyncClient`` at ``transport``. Typed kwargs so ty can check the call."""
    original = httpx.AsyncClient

    def bound(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", bound)


def runner_against(host: _FakeHost, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> SandboxedGymAgentTaskRunner:
    """A runner whose HTTP client is bound to ``host``."""
    bind_http_transport(monkeypatch, host.transport())
    return SandboxedGymAgentTaskRunner(config=SandboxedGymRuntimeConfig(rollout_url=ROLLOUT_URL, **overrides))


async def test_rollouts_from_the_host_are_attributed_to_the_right_tasks(tasks, tmp_path, monkeypatch) -> None:
    # The property the whole design turns on: identity assigned here survives the hop and comes
    # back joinable. Distinct rewards make a swapped attribution visible rather than plausible.
    host = _FakeHost(rewards={0: 1.0, 1: 0.0})
    runner = runner_against(host, monkeypatch)

    trials = await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    rewards = {trial.task_id: trial.metadata["reward"] for trial in trials}
    assert rewards[tasks[0].id] == 1.0
    assert rewards[tasks[1].id] == 0.0


async def test_the_examples_posted_carry_the_index_we_stamped(tasks, tmp_path, monkeypatch) -> None:
    # The host cannot attribute anything we did not stamp, so this is the precondition for the
    # test above rather than a restatement of it.
    host = _FakeHost()
    runner = runner_against(host, monkeypatch)

    await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    assert [example[NG_TASK_INDEX] for example in host.posted] == [0, 1]
    assert all("responses_create_params" in example for example in host.posted)


async def test_the_auth_token_is_sent_as_the_proxy_header(tasks, tmp_path, monkeypatch) -> None:
    host = _FakeHost()
    runner = runner_against(host, monkeypatch, auth_token="tok-123", headers={"X-Extra": "kept"})

    await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    sent = host.requests[0].headers
    assert sent[PROXY_AUTH_HEADER] == "tok-123"
    assert sent["X-Extra"] == "kept", "caller-supplied headers must survive alongside the token"


async def test_no_auth_header_is_sent_when_no_token_is_configured(tasks, tmp_path, monkeypatch) -> None:
    # An unauthenticated proxy is a valid configuration; sending an empty token would fail closed
    # against it for no reason.
    host = _FakeHost()
    runner = runner_against(host, monkeypatch)

    await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    assert PROXY_AUTH_HEADER not in host.requests[0].headers


async def test_an_http_error_names_the_host_and_carries_its_body(tasks, tmp_path, monkeypatch) -> None:
    """The body says which example or server failed; the status code alone does not."""
    host = _FakeHost(status=502, body={"error": {"message": "resources_server crashed"}})
    runner = runner_against(host, monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    message = str(excinfo.value)
    assert "502" in message
    assert ROLLOUT_URL in message
    assert "resources_server crashed" in message


async def test_an_error_carried_on_a_200_is_still_a_failure(tasks, tmp_path, monkeypatch) -> None:
    """The host commits its 200 before the batch finishes, so late failures ride the body.

    It answers early on purpose: the sandbox proxy gives up on a request whose first byte has not
    arrived, and a batch outlasts that. Reading only the status would call a deadline or a crashed
    environment a success and then blame the run for having no results.
    """
    host = _FakeHost(body={"error": {"code": "deadline_exceeded", "message": "abandoned after 1800s"}})
    runner = runner_against(host, monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    message = str(excinfo.value)
    assert "deadline_exceeded" in message
    assert "abandoned after 1800s" in message
    assert ROLLOUT_URL in message


async def test_a_heartbeat_only_200_names_the_host_as_the_failure(tasks, tmp_path, monkeypatch) -> None:
    """OOMKill after the host committed 200 leaves heartbeats and no envelope.

    The orchestrator classifies that as the sandbox dying. This runner is a second client of the
    same host; it must not surface a JSON decode error that looks like a bug in the evaluator.
    """
    host = _FakeHost(content=b"     ")
    runner = runner_against(host, monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    message = str(excinfo.value)
    assert ROLLOUT_URL in message
    assert "JSON" not in message
    assert "error" in message.lower() or "results" in message.lower()


async def test_a_response_without_a_results_list_is_refused(tasks, tmp_path, monkeypatch) -> None:
    # Reaching the parser with nothing collected would surface as "no rollouts", blaming the run
    # for what is a malformed reply.
    host = _FakeHost(body={"unexpected": True})
    runner = runner_against(host, monkeypatch)

    with pytest.raises(RuntimeError, match="no `results` list"):
        await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))


async def test_a_task_the_host_never_answered_fails_the_run(tasks, tmp_path, monkeypatch) -> None:
    """Partial collection must not read as a completed evaluation with fewer tasks."""

    def handle(request: httpx.Request) -> httpx.Response:
        example = json.loads(request.content.decode())["examples"][0]
        return httpx.Response(
            200,
            json={"results": [{NG_TASK_INDEX: example[NG_TASK_INDEX], NG_ROLLOUT_INDEX: 0, "reward": 1.0}]},
        )

    bind_http_transport(monkeypatch, httpx.MockTransport(handle))
    runner = SandboxedGymAgentTaskRunner(config=SandboxedGymRuntimeConfig(rollout_url=ROLLOUT_URL))

    with pytest.raises(RuntimeError, match=r"no rollout for 1 of 2 requested task") as excinfo:
        await runner.run_tasks(tasks, AgentEvalRunConfig(work_dir=tmp_path))

    # The check that fires is the CLI runner's own, reached because this runner writes the records
    # where that parser reads them -- which is the reuse claim, stated as a test.
    assert "will not be scored" in str(excinfo.value)


def test_runner_info_records_the_host_but_not_the_token() -> None:
    runner = SandboxedGymAgentTaskRunner(
        config=SandboxedGymRuntimeConfig(rollout_url=ROLLOUT_URL, auth_token="sk-secret-value")
    )

    info = runner.runner_info()

    assert info.name == "gym"
    assert info.config["mode"] == "sandboxed"
    assert info.config["rollout_url"] == ROLLOUT_URL
    assert "sk-secret-value" not in json.dumps(info.config), "the token must not reach the run bundle"
