"""E2E test for docker-mode agent deployments.

Unlike ``test_nemo_agents.py`` (backend-agnostic API/SDK surface, plus
subprocess-mode deployment coverage), this module deploys an agent as a real
**Docker container** through the nemo-deployments plugin and invokes it through
the agents gateway.

What it proves — the container-mode chain end to end::

    sdk.agents.invoke (gateway proxy, container-mode endpoint resolution)
      -> docker agent container (nat start fastapi)
      -> Inference Gateway /openai (base_url injected at deploy time)
      -> mock provider short-circuit (no real upstream / no API key)
      -> response back through the gateway

How it runs, and where:

- The deployed agent runs from the platform's own ``nmp-api`` image, which
  already ships the NAT runtime (``nvidia-nat-core`` / ``nvidia-nat-langchain``,
  via ``nemo-agents-plugin``) — so ``nat`` is on ``PATH`` and the
  ``chat_completion`` workflow / ``openai`` LLM the agent uses resolve. The
  deployments docker executor overrides the image entrypoint with
  ``nat start fastapi``, so the image's own entrypoint is irrelevant. No
  agent-specific image is built.
- The image is supplied prebuilt via ``NMP_E2E_IMAGE_REGISTRY`` /
  ``NMP_E2E_IMAGE_TAG`` (the existing e2e convention). Its dedicated CI job
  (``python-e2e-image-test``) builds/pulls ``nmp-api`` and sets these; the
  ``needs_nmp_api_image`` marker skips the test everywhere they are unset (the
  plain subprocess e2e job, the kind cluster job, and local runs without them).
- The agent is registered with a deterministic single-LLM ``chat_completion``
  workflow served by the e2e mock inference provider, so no ``NVIDIA_API_KEY``
  or model egress is needed; we assert the exact mocked completion round-trips.
- The platform runs as a normal local process (subprocess harness). The
  ``container_base_url_host`` harness option makes the harness bind the platform
  on all interfaces (``--host 0.0.0.0``) and rewrite ``platform.base_url`` to the
  docker bridge address; the runner seeds ``NMP_BASE_URL`` from that host paired
  with the actual bind port, so the Inference Gateway URL injected into the agent
  container is reachable from *inside* the container while the platform's own
  in-process clients still reach it. This requires the Linux docker bridge, which
  is reachable from both the container and the host process; Docker Desktop's
  host alias is not host-resolvable, so the module skips on non-Linux.
"""

import os
import platform
import time
import uuid
from contextlib import suppress
from typing import Any

import httpx
import pytest
from nemo_platform import NeMoPlatform
from nmp.testing import MockProviderResponse, add_mock_provider

# The docker bridge gateway. On Linux (incl. GitHub Actions ubuntu runners) this
# address is reachable both from inside a container AND by the platform process
# itself (it is a local host interface). That dual reachability is required:
# platform.base_url is used both as the Inference Gateway URL injected into the
# agent container *and* by the platform's own in-process service clients.
_DOCKER_BRIDGE_HOST = "172.17.0.1"

# Platform image name to deploy the agent from. The nmp-api image already ships
# the NAT runtime and the agent components (see module docstring), so it doubles
# as the agent runtime image. Registry and tag come from NMP_E2E_IMAGE_REGISTRY /
# NMP_E2E_IMAGE_TAG (the existing e2e image convention).
_AGENT_IMAGE_NAME = "nmp-api"

# Runs the platform as a local process wired with a docker deployments executor
# (see the config), and deploys the agent as a real docker container.
#
# Markers:
# - ``needs_nmp_api_image``: skips unless NMP_E2E_IMAGE_REGISTRY + NMP_E2E_IMAGE_TAG
#   are set (its dedicated CI job builds/pulls nmp-api and sets them). This also
#   keeps the test out of the plain subprocess e2e job and the kind cluster job.
# - ``subprocess_only``: this test drives its own subprocess-harness platform
#   configured with a docker deployments executor. It must NOT run against an
#   external cluster (``NMP_BASE_URL`` set, e.g. the Kind CPU e2e job), where the
#   deployed Helm platform has no docker executor and the module's own
#   ``e2e_config``/harness are ignored.
pytestmark = [
    pytest.mark.needs_nmp_api_image,
    pytest.mark.subprocess_only,
    pytest.mark.skipif(
        platform.system() != "Linux",
        reason="Docker-mode agent deployment e2e requires a Linux docker bridge reachable by both the "
        "platform process and the agent container (Docker Desktop's host alias is not host-resolvable).",
    ),
    pytest.mark.e2e_config(
        "e2e/configs/local-docker-agents.yaml",
        harness={"backend": "subprocess", "container_base_url_host": _DOCKER_BRIDGE_HOST},
    ),
]

_TEST_AGENT_RESPONSE = "The answer to your question is 42."


def _unique_name(prefix: str) -> str:
    return f"e2e-{prefix}-{uuid.uuid4().hex[:8]}"


def _chat_completion_response(content: str, model: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-agents-docker-e2e",
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


def _delete_agent_if_exists(sdk: NeMoPlatform, *, workspace: str, name: str) -> None:
    try:
        sdk.agents.delete(name, workspace=workspace)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise


def _delete_deployment_if_exists(sdk: NeMoPlatform, *, workspace: str, name: str) -> None:
    try:
        sdk.agents.deployments.delete(name, workspace=workspace)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise


def _get_deployment_log_text(sdk: NeMoPlatform, *, workspace: str, name: str) -> str:
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


def _wait_for_deployment_deleted(
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


def _wait_for_deployment_running(
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
            logs = _get_deployment_log_text(sdk, workspace=workspace, name=name)
            pytest.fail(f"Deployment {name!r} failed: {deployment.get('error', '')}\n{logs}")
        time.sleep(2)
    pytest.fail(f"Deployment {name!r} did not reach running within {timeout_seconds}s: {last_deployment}")


@pytest.fixture(scope="session")
def agent_deployment_image() -> str:
    """Return the prebuilt platform image ref to deploy the agent from.

    Composed from the e2e image convention (``NMP_E2E_IMAGE_REGISTRY`` /
    ``NMP_E2E_IMAGE_TAG``) as ``{registry}/nmp-api:{tag}``. The nmp-api image
    already ships the NAT runtime and agent components, so no agent-specific
    image is built here. The ``needs_nmp_api_image`` marker guarantees both env
    vars are set before this test runs; assert defensively.
    """
    registry = os.environ.get("NMP_E2E_IMAGE_REGISTRY")
    tag = os.environ.get("NMP_E2E_IMAGE_TAG")
    assert registry and tag, "needs_nmp_api_image marker should have skipped when registry/tag are unset"
    return f"{registry.rstrip('/')}/{_AGENT_IMAGE_NAME}:{tag}"


def _remove_agent_container_if_present(deployment_name: str) -> None:
    """Best-effort removal of a leaked agent container after teardown."""
    try:
        from docker.errors import NotFound

        import docker
    except Exception:
        return
    try:
        client = docker.from_env()
    except Exception:
        return
    # The deployments docker backend names containers after the deployment; match
    # loosely so a naming-scheme change does not silently leak containers.
    for container in client.containers.list(all=True):
        if deployment_name in container.name:
            try:
                container.remove(force=True)
            except NotFound:
                pass
            except Exception:
                pass


def test_docker_agent_deploys_and_invokes_through_gateway(
    sdk: NeMoPlatform, workspace: str, agent_deployment_image: str
) -> None:
    """Deploy an agent as a docker container from the nmp-api image and invoke it.

    Asserts the deployment reaches ``running`` with the container-mode endpoint
    shape (empty scalar ``endpoint``, populated ``endpoints``), then invokes
    through the gateway and asserts the mocked completion round-trips from inside
    the container back to the caller.
    """
    agent_name = _unique_name("calc-agent")
    deployment_name = _unique_name("calc-deployment")
    model_name = _unique_name("calc-model")

    add_mock_provider(
        sdk,
        workspace=workspace,
        name=_unique_name("calc-provider"),
        mock_response_body_by_model={
            f"{workspace}/{model_name}": [
                MockProviderResponse(response_body=_chat_completion_response(_TEST_AGENT_RESPONSE, model_name)),
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
            deployment_mode="docker",
            image=agent_deployment_image,
        )
        assert created["deployment_mode"] == "docker"

        deployment = _wait_for_deployment_running(sdk, workspace=workspace, name=deployment_name)
        assert deployment["agent"] == agent_name
        assert deployment["deployment_mode"] == "docker"

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
        assert _TEST_AGENT_RESPONSE in content, response
    finally:
        # Each step is isolated so a failure (e.g. a deployment-delete timeout)
        # doesn't skip the remaining cleanup and leak resources.
        with suppress(Exception):
            _delete_deployment_if_exists(sdk, workspace=workspace, name=deployment_name)
        with suppress(Exception):
            _wait_for_deployment_deleted(sdk, workspace=workspace, name=deployment_name)
        with suppress(Exception):
            _remove_agent_container_if_present(deployment_name)
        with suppress(Exception):
            _delete_agent_if_exists(sdk, workspace=workspace, name=agent_name)
