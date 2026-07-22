# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for container-mode agent deployment e2e tests.

Both the Docker (``test_nemo_agents_docker.py``) and Kubernetes
(``test_nemo_agents_k8s.py``) modules deploy a real agent **container** through
the nemo-deployments plugin and invoke it through the agents gateway. The end-to
-end chain they prove is identical apart from the backend::

    sdk.agents.invoke (gateway proxy, container-mode endpoint resolution)
      -> agent container (nat start fastapi) on docker | kubernetes
      -> Inference Gateway /openai (base_url injected at deploy time)
      -> mock provider short-circuit (no real upstream / no API key)
      -> response back through the gateway

This module holds the backend-agnostic core: the mock-provider-backed agent
config, the create -> wait-running -> assert-container-shape -> invoke -> assert
flow, and cleanup. The per-backend modules own only what genuinely differs
(pytest markers, how the deployment image ref is resolved, and best-effort
container cleanup).
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from nemo_platform import NeMoPlatform
from nmp.testing import MockProviderResponse, add_mock_provider

# The mocked completion the deployed agent must round-trip back to the caller.
TEST_AGENT_RESPONSE = "The answer to your question is 42."


def unique_name(prefix: str) -> str:
    return f"e2e-{prefix}-{uuid.uuid4().hex[:8]}"


def _chat_completion_response(content: str, model: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-agents-container-e2e",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _mock_backed_agent_config(model_name: str) -> dict[str, Any]:
    """A deterministic single-LLM workflow pointed at the mock model.

    ``base_url``/``api_key`` are intentionally omitted so the deployment injects
    the Inference Gateway URL (and the mock provider short-circuits the call).
    """
    return {
        "llms": {
            "main": {
                "_type": "openai",
                "model_name": model_name,
            }
        },
        "workflow": {
            "_type": "chat_completion",
            "llm_name": "main",
        },
    }


def _page_data(page: Any) -> list[dict[str, Any]]:
    if isinstance(page, dict):
        data = page.get("data", [])
    else:
        data = getattr(page, "data", [])
    assert isinstance(data, list)
    return data


def delete_agent_if_exists(sdk: NeMoPlatform, *, workspace: str, name: str) -> None:
    try:
        sdk.agents.delete(name, workspace=workspace)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise


def delete_deployment_if_exists(sdk: NeMoPlatform, *, workspace: str, name: str) -> None:
    try:
        sdk.agents.deployments.delete(name, workspace=workspace)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise


def get_deployment_log_text(sdk: NeMoPlatform, *, workspace: str, name: str) -> str:
    try:
        response = sdk._client.get(
            f"/apis/agents/v2/workspaces/{workspace}/deployments/{name}/logs",
            params={"tail": 100},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return exc.response.text

    payload = response.json()
    lines = _page_data(payload)
    return "\n".join(str(line.get("message", line)) for line in lines)


def wait_for_deployment_deleted(
    sdk: NeMoPlatform,
    *,
    workspace: str,
    name: str,
    timeout_seconds: float = 120,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status: str | None = None
    while time.monotonic() < deadline:
        try:
            deployment = sdk.agents.deployments.get(name, workspace=workspace)
            last_status = deployment.get("status")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return
            raise
        time.sleep(2)
    pytest.fail(f"Deployment {name!r} was not deleted within {timeout_seconds}s; last status={last_status!r}")


def wait_for_deployment_running(
    sdk: NeMoPlatform,
    *,
    workspace: str,
    name: str,
    timeout_seconds: float = 300,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_deployment: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        deployment = sdk.agents.deployments.get(name, workspace=workspace)
        last_deployment = deployment
        status = deployment["status"]
        if status == "running":
            return deployment
        if status == "failed":
            logs = get_deployment_log_text(sdk, workspace=workspace, name=name)
            pytest.fail(f"Deployment {name!r} failed: {deployment.get('error', '')}\n{logs}")
        time.sleep(2)
    pytest.fail(f"Deployment {name!r} did not reach running within {timeout_seconds}s: {last_deployment}")


def run_container_agent_deploy_and_invoke(
    sdk: NeMoPlatform,
    *,
    workspace: str,
    deployment_mode: str,
    image: str,
    running_timeout_seconds: float = 300,
    reap_backend_resources: Callable[[str], None] | None = None,
) -> None:
    """Deploy a mock-backed agent as a container and invoke it through the gateway.

    Backend-agnostic core shared by the docker and k8s e2e modules:

    1. Register a mock inference provider + deterministic single-LLM agent.
    2. Deploy it with ``deployment_mode`` (``"docker"`` / ``"k8s"``) from ``image``.
    3. Wait for ``running`` and assert the container-mode endpoint shape (empty
       scalar ``endpoint``, populated ``endpoints``) — this guards that the pass
       came through the container path, not a subprocess fallback.
    4. Invoke through the gateway and assert the mocked completion round-trips.
    5. Clean up the deployment and agent (best-effort, isolated steps).

    ``reap_backend_resources``, if given, is called with the deployment name
    during teardown (after the deployment is deleted) so a backend module can
    best-effort reap leaked resources it uniquely knows about — e.g. a leftover
    docker container. It must not raise; failures are swallowed like the rest of
    teardown.
    """
    agent_name = unique_name("calc-agent")
    deployment_name = unique_name("calc-deployment")
    model_name = unique_name("calc-model")

    add_mock_provider(
        sdk,
        workspace=workspace,
        name=unique_name("calc-provider"),
        mock_response_body_by_model={
            f"{workspace}/{model_name}": [
                MockProviderResponse(response_body=_chat_completion_response(TEST_AGENT_RESPONSE, model_name)),
            ],
        },
        served_models={model_name: model_name},
    )

    sdk.agents.create(
        workspace=workspace,
        name=agent_name,
        config=_mock_backed_agent_config(f"{workspace}/{model_name}"),
    )

    try:
        created = sdk.agents.deployments.create(
            workspace=workspace,
            agent=agent_name,
            name=deployment_name,
            deployment_mode=deployment_mode,
            image=image,
        )
        assert created["deployment_mode"] == deployment_mode

        deployment = wait_for_deployment_running(
            sdk, workspace=workspace, name=deployment_name, timeout_seconds=running_timeout_seconds
        )
        assert deployment["agent"] == agent_name
        assert deployment["deployment_mode"] == deployment_mode

        # Container-mode addressing: the loopback scalar ``endpoint`` is empty and
        # the routable address lives in ``endpoints`` (this is what the gateway's
        # container-mode resolution reads). Guarding this shape ensures a pass can
        # only come through the container path, not a subprocess fallback.
        assert deployment.get("endpoint", "") == ""
        endpoints = deployment.get("endpoints") or []
        assert endpoints and endpoints[0]["url"], deployment

        response = sdk.agents.invoke(
            workspace=workspace,
            agent=agent_name,
            input="What is 12 multiplied by 8?",
        )
        content = response["choices"][0]["message"]["content"]
        assert TEST_AGENT_RESPONSE in content, response
    finally:
        # Each step is isolated so a failure (e.g. a deployment-delete timeout)
        # doesn't skip the remaining cleanup and leak resources.
        _safe(delete_deployment_if_exists, sdk, workspace=workspace, name=deployment_name)
        _safe(wait_for_deployment_deleted, sdk, workspace=workspace, name=deployment_name)
        if reap_backend_resources is not None:
            _safe(reap_backend_resources, deployment_name)
        _safe(delete_agent_if_exists, sdk, workspace=workspace, name=agent_name)


def _safe(fn: Any, *args: Any, **kwargs: Any) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:
        pass
