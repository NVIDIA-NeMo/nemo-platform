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

How it stays hermetic and CI-friendly:

- The agent image is built locally from the ``calculator-agent`` example
  package (real NAT deps), so the container is a faithful NAT runtime image, but
  the agent itself is registered with a deterministic single-LLM
  ``chat_completion`` workflow. A mock LLM cannot actually drive a multi-call
  ReAct loop, so we assert the exact mocked completion round-trips rather than a
  computed answer.
- The LLM is served by the e2e mock inference provider, so no ``NVIDIA_API_KEY``
  or network egress to a real model is required.
- The platform runs as a normal local process (subprocess harness backend). The
  ``container_base_url_host`` harness option makes the harness (a) bind the
  platform on all interfaces (``--host 0.0.0.0``) and (b) rewrite
  ``platform.base_url`` to the docker bridge address with the port it actually
  bound. The runner then seeds ``NMP_BASE_URL`` from that host, so the Inference
  Gateway URL injected into the agent container points at a host reachable from
  *inside* that container (the bridge), while the platform's own in-process
  clients — which also use ``NMP_BASE_URL`` — can still reach it because the
  server listens on all interfaces. (The runner seeds ``NMP_BASE_URL`` from the
  config ``platform.base_url`` host paired with the actual bind port.)
"""

import platform
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from nemo_platform import NeMoPlatform
from nmp.testing import MockProviderResponse, add_mock_provider

# The docker bridge gateway. On Linux (incl. GitHub Actions ubuntu runners) this
# address is reachable both from inside a container AND by the platform process
# itself (it is a local host interface). That dual reachability is required:
# platform.base_url is used both as the Inference Gateway URL injected into the
# agent container *and* by the platform's own in-process service clients. On
# Docker Desktop (macOS/Windows) the container-facing host alias
# (host.docker.internal) is not resolvable by the host platform process, so this
# scenario only works on Linux; the module skips elsewhere.
_DOCKER_BRIDGE_HOST = "172.17.0.1"

# Runs the platform as a local process, but wired with a docker deployments
# executor (see the config). ``container_base_url_host`` tells the harness to
# advertise the docker bridge address as platform.base_url so the deployed agent
# container can reach the Inference Gateway.
#
# Markers:
# - ``subprocess_only``: this test drives its own subprocess-harness platform
#   configured with a docker deployments executor. It must NOT run against an
#   external cluster (``NMP_BASE_URL`` set, e.g. the Kind CPU e2e job), where the
#   deployed Helm platform has no docker executor and the module's own
#   ``e2e_config``/harness are ignored — the docker-mode deploy would fail with
#   "No executor specified and no default_executor configured."
# - ``docker``: self-skips when no Docker daemon is reachable.
pytestmark = [
    pytest.mark.subprocess_only,
    pytest.mark.docker,
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

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CALCULATOR_EXAMPLE = _REPO_ROOT / "plugins/nemo-agents/examples/calculator-agent"

# Base image for the agent runtime build. A slim Python is all that's needed —
# the NAT runtime and its version come from the example package's dependencies.
# Kept as a variable rather than hardcoded inline; there is no shared repo-level
# base-image constant to reuse (the nemo agents packager's default is a heavier
# nvcr.io NVIDIA base gated behind the `container` extra, not appropriate here).
_AGENT_IMAGE_BASE = "python:3.11-slim"

# A locally-built image tag (never pushed to a registry — the executor is
# configured with pull_images=false so the local image is used as-is).
_AGENT_IMAGE = "nmp-e2e-calculator-agent:local"

_TEST_AGENT_RESPONSE = "The answer to your question is 42."

# The NAT server inside the container binds this port (must match
# agents.deployments.container_port in the config).
_CONTAINER_PORT = 8000


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
def calculator_agent_image() -> str:
    """Build a NAT runtime image for the calculator agent example (idempotent).

    A slim python base with the calculator example package installed, so ``nat``
    is on the PATH and the agent's components resolve. The NAT runtime
    (nvidia-nat-core / nvidia-nat-langchain) is pulled in transitively via the
    example package's own dependencies, so the version stays defined in one
    place — the example's pyproject.toml — with nothing to keep in sync here.
    Built with the host Docker daemon; tagged locally and never pushed (the
    executor uses pull_images=false).
    """
    import docker

    client = docker.from_env()
    if client.images.list(name=_AGENT_IMAGE):
        return _AGENT_IMAGE

    dockerfile = "\n".join(
        [
            f"FROM {_AGENT_IMAGE_BASE}",
            "RUN apt-get update"
            " && apt-get install -y --no-install-recommends curl ca-certificates"
            " && rm -rf /var/lib/apt/lists/*",
            "COPY calculator-agent /opt/calculator-agent",
            "RUN pip install --no-cache-dir /opt/calculator-agent",
            "",
        ]
    )

    import shutil
    import tempfile

    with tempfile.TemporaryDirectory(prefix="nmp-e2e-agent-build-") as build_dir:
        build_path = Path(build_dir)
        shutil.copytree(_CALCULATOR_EXAMPLE, build_path / "calculator-agent")
        (build_path / "Dockerfile").write_text(dockerfile)
        # The docker SDK's build stream is awkward to surface on failure; shell
        # out so the full build log lands in the test output on error.
        proc = subprocess.run(
            ["docker", "build", "-t", _AGENT_IMAGE, str(build_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            pytest.fail(f"Failed to build calculator agent image:\n{proc.stdout}\n{proc.stderr}")

    return _AGENT_IMAGE


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
    sdk: NeMoPlatform, workspace: str, calculator_agent_image: str
) -> None:
    """Deploy the calculator-agent image as a docker container and invoke it.

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
            image=calculator_agent_image,
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
        _delete_deployment_if_exists(sdk, workspace=workspace, name=deployment_name)
        _wait_for_deployment_deleted(sdk, workspace=workspace, name=deployment_name)
        _remove_agent_container_if_present(deployment_name)
        _delete_agent_if_exists(sdk, workspace=workspace, name=agent_name)
