# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from nemo_agents_plugin.entities import (
    AgentEnvironmentInline,
    ComputeResources,
    ComputeSpecInline,
    EnvironmentSpecInline,
)
from nemo_agents_plugin.sdk import AgentsResource, AsyncAgentsResource, agents_sdk_resources
from nemo_agents_plugin.session_protocol import SESSION_ID_HEADER


def _install_mock_transport(handler) -> AbstractContextManager[Any]:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    return patch("nemo_agents_plugin.sdk.httpx.Client", _factory)


def test_create_resolves_default_model_placeholder_before_post() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "calc"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    config = {"llms": {"llm": {"_type": "openai", "model_name": "${NEMO_DEFAULT_MODEL}"}}}

    with (
        _install_mock_transport(handler),
        patch("nemo_agents_plugin.utils.get_default_model", return_value="team-a/nemotron"),
    ):
        result = client.create(name="calc", config=config)

    assert result == {"name": "calc"}
    assert captured["path"] == "/apis/agents/v2/workspaces/team-a/agents"
    assert captured["body"]["config"]["llms"]["llm"]["model_name"] == "team-a/nemotron"
    assert config["llms"]["llm"]["model_name"] == "${NEMO_DEFAULT_MODEL}"


def test_create_rejects_unresolved_default_model_placeholder() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("should not POST unresolved agent config")

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    config = {"llms": {"llm": {"_type": "openai", "model_name": "$NEMO_DEFAULT_MODEL"}}}

    with (
        _install_mock_transport(handler),
        patch("nemo_agents_plugin.utils.get_default_model", return_value=None),
        pytest.raises(ValueError, match="NEMO_DEFAULT_MODEL"),
    ):
        client.create(name="calc", config=config)


def test_deployments_create_uses_client_workspace_by_default() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "calc-dep"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))

    with _install_mock_transport(handler):
        result = client.deployments.create(agent="calc", deployment_mode="k8s", image="repo/calc:1.0")

    assert result == {"name": "calc-dep"}
    assert captured["path"] == "/apis/agents/v2/workspaces/team-a/deployments"
    assert captured["body"] == {"agent": "calc", "deployment_mode": "k8s", "image": "repo/calc:1.0"}


def test_deployments_create_forwards_image_entrypoint_mode() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "calc-dep"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))

    with _install_mock_transport(handler):
        client.deployments.create(
            agent="calc",
            deployment_mode="docker",
            image="repo/calc:1.0",
            use_image_entrypoint=True,
        )

    assert captured["body"] == {
        "agent": "calc",
        "deployment_mode": "docker",
        "image": "repo/calc:1.0",
        "use_image_entrypoint": True,
    }


def test_deployments_create_rejects_image_entrypoint_for_subprocess() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("should not POST image entrypoint mode for subprocess")

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))

    with _install_mock_transport(handler), pytest.raises(ValueError, match="use_image_entrypoint"):
        client.deployments.create(agent="calc", use_image_entrypoint=True)


def test_invoke_sends_session_id_as_header() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.read())
        captured["session_id"] = req.headers.get(SESSION_ID_HEADER)
        return httpx.Response(200, json={"id": "completion-id"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))

    with _install_mock_transport(handler):
        result = client.invoke(input="Continue", deployment="calc-dep", session_id="session-entity-id")

    assert result == {"id": "completion-id"}
    assert captured["path"] == "/apis/agents/v2/workspaces/team-a/deployments/calc-dep/-/v1/chat/completions"
    assert captured["session_id"] == "session-entity-id"
    assert captured["body"] == {
        "messages": [{"role": "user", "content": "Continue"}],
        "stream": False,
    }


def test_invoke_without_session_id_omits_header() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["session_id"] = req.headers.get(SESSION_ID_HEADER)
        return httpx.Response(200, json={"id": "completion-id"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))

    with _install_mock_transport(handler):
        client.invoke(input="Hello", agent="calc")

    assert captured["session_id"] is None


def test_invoke_rejects_empty_session_id() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("should not invoke with an empty session ID")

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))

    with _install_mock_transport(handler), pytest.raises(ValueError, match="session_id must not be empty"):
        client.invoke(input="Hello", agent="calc", session_id="")


# ---------------------------------------------------------------------------
# environment / environment-spec / compute-spec resources
# ---------------------------------------------------------------------------


def test_deployments_create_forwards_environment() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "d1"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="default"))
    with _install_mock_transport(handler):
        client.deployments.create(agent="calc", environment="default/env1")

    assert captured["body"]["environment"] == "default/env1"


def test_environment_specs_create_posts_inline_fields() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "ben"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    with _install_mock_transport(handler):
        result = client.environment_specs.create(name="ben", env={"LOG_LEVEL": "debug"}, secrets={"TOK": "default/tok"})

    assert result == {"name": "ben"}
    assert captured["path"] == "/apis/agents/v2/workspaces/team-a/environment-specs"
    assert captured["body"] == {"name": "ben", "env": {"LOG_LEVEL": "debug"}, "secrets": {"TOK": "default/tok"}}


def test_environments_create_with_refs() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "env1"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="default"))
    with _install_mock_transport(handler):
        client.environments.create(name="env1", environment_spec="default/ben", compute_spec="default/big")

    assert captured["path"] == "/apis/agents/v2/workspaces/default/environments"
    assert captured["body"]["environment_spec"] == "default/ben"
    assert captured["body"]["compute_spec"] == "default/big"


def test_environments_create_omits_unset_refs() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "env2"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="default"))
    with _install_mock_transport(handler):
        client.environments.create(name="env2", environment_spec="default/ben")

    assert "compute_spec" not in captured["body"]
    assert captured["body"]["environment_spec"] == "default/ben"


def test_compute_specs_get_and_delete() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured.setdefault("calls", []).append((req.method, req.url.path))
        if req.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"name": "big"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    with _install_mock_transport(handler):
        got = client.compute_specs.get("big")
        client.compute_specs.delete("big")

    assert got == {"name": "big"}
    assert ("GET", "/apis/agents/v2/workspaces/team-a/compute-specs/big") in captured["calls"]
    assert ("DELETE", "/apis/agents/v2/workspaces/team-a/compute-specs/big") in captured["calls"]


class _RecordingPlatform:
    """Stand-in for the platform client's request pipeline.

    The job resources deliberately go through ``platform.post`` / ``platform.get``
    rather than a bare ``httpx`` client, so the caller's auth headers, base URL,
    and retry policy are applied. Recording those calls is enough to pin the
    request shape.
    """

    def __init__(self, response: Any = None, workspace: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response if response is not None else {"name": "execute-a1b2"}
        self.workspace = workspace

    def post(self, path: str, *, body: Any = None, cast_to: Any = None) -> Any:
        self.calls.append({"method": "POST", "path": path, "body": body, "cast_to": cast_to})
        return self._response

    def get(self, path: str, *, cast_to: Any = None) -> Any:
        self.calls.append({"method": "GET", "path": path, "cast_to": cast_to})
        return self._response


def test_execute_job_create_posts_spec_to_job_collection() -> None:
    platform = _RecordingPlatform()
    resource = AgentsResource(platform)

    result = resource.jobs.execute.create(spec={"agent": "calc", "input": "2+2"}, workspace="team-a")

    assert result == {"name": "execute-a1b2"}
    assert platform.calls == [
        {
            "method": "POST",
            "path": "/apis/agents/v2/workspaces/team-a/jobs/execute",
            "body": {"spec": {"agent": "calc", "input": "2+2"}},
            "cast_to": dict[str, Any],
        }
    ]


def test_execute_job_create_omits_name_when_unset() -> None:
    """An omitted name lets the Jobs service generate a unique one."""
    platform = _RecordingPlatform()

    AgentsResource(platform).jobs.execute.create(spec={"agent": "calc", "input": "hi"})

    assert "name" not in platform.calls[0]["body"]


def test_execute_job_create_includes_name_and_description_when_given() -> None:
    platform = _RecordingPlatform()

    AgentsResource(platform).jobs.execute.create(
        spec={"agent": "calc", "input": "hi"}, name="run-1", description="demo"
    )

    assert platform.calls[0]["body"]["name"] == "run-1"
    assert platform.calls[0]["body"]["description"] == "demo"


def test_execute_job_get_and_list_results_paths() -> None:
    platform = _RecordingPlatform()
    jobs = AgentsResource(platform).jobs.execute

    jobs.get("execute-a1b2", workspace="team-a")
    jobs.list_results("execute-a1b2", workspace="team-a")

    assert [call["path"] for call in platform.calls] == [
        "/apis/agents/v2/workspaces/team-a/jobs/execute/execute-a1b2",
        "/apis/agents/v2/workspaces/team-a/jobs/execute/execute-a1b2/results",
    ]


def test_execute_job_get_accepts_workspace_positionally() -> None:
    """Mirrors sibling ``get``/``delete`` methods, which take workspace positional-or-keyword."""
    platform = _RecordingPlatform()
    jobs = AgentsResource(platform).jobs.execute

    jobs.get("execute-a1b2", "team-a")

    assert platform.calls[0]["path"] == "/apis/agents/v2/workspaces/team-a/jobs/execute/execute-a1b2"


def test_execute_job_create_uses_client_workspace_by_default() -> None:
    platform = _RecordingPlatform(workspace="team-a")

    AgentsResource(platform).jobs.execute.create(spec={"agent": "calc", "input": "2+2"})

    assert platform.calls[0]["path"] == "/apis/agents/v2/workspaces/team-a/jobs/execute"


def test_execute_job_get_and_list_results_use_client_workspace_by_default() -> None:
    platform = _RecordingPlatform(workspace="team-a")
    jobs = AgentsResource(platform).jobs.execute

    jobs.get("execute-a1b2")
    jobs.list_results("execute-a1b2")

    assert [call["path"] for call in platform.calls] == [
        "/apis/agents/v2/workspaces/team-a/jobs/execute/execute-a1b2",
        "/apis/agents/v2/workspaces/team-a/jobs/execute/execute-a1b2/results",
    ]


async def test_async_execute_job_create_uses_client_workspace_by_default() -> None:
    class _AsyncRecordingPlatform(_RecordingPlatform):
        async def post(self, path: str, *, body: Any = None, cast_to: Any = None) -> Any:
            return super().post(path, body=body, cast_to=cast_to)

        async def get(self, path: str, *, cast_to: Any = None) -> Any:
            return super().get(path, cast_to=cast_to)

    platform = _AsyncRecordingPlatform(workspace="team-a")

    await AsyncAgentsResource(platform).jobs.execute.create(spec={"agent": "calc", "input": "2+2"})

    assert platform.calls[0]["path"] == "/apis/agents/v2/workspaces/team-a/jobs/execute"


async def test_async_execute_job_create_mirrors_sync_shape() -> None:
    class _AsyncRecordingPlatform(_RecordingPlatform):
        async def post(self, path: str, *, body: Any = None, cast_to: Any = None) -> Any:
            return super().post(path, body=body, cast_to=cast_to)

    platform = _AsyncRecordingPlatform()

    result = await AsyncAgentsResource(platform).jobs.execute.create(
        spec={"agent": "calc", "input": "2+2"}, workspace="team-a"
    )

    assert result == {"name": "execute-a1b2"}
    assert platform.calls[0]["path"] == "/apis/agents/v2/workspaces/team-a/jobs/execute"
    assert platform.calls[0]["body"] == {"spec": {"agent": "calc", "input": "2+2"}}


def test_agents_sdk_resources_registers_both_sync_and_async() -> None:
    assert agents_sdk_resources.sync_resource is AgentsResource
    assert agents_sdk_resources.async_resource is AsyncAgentsResource


def test_environment_specs_create_accepts_typed_model() -> None:
    """A typed ``EnvironmentSpecInline`` sends only the fields that were set."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "ben"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    spec = EnvironmentSpecInline(env={"LOG_LEVEL": "debug"}, secrets={"TOK": "default/tok"})
    with _install_mock_transport(handler):
        client.environment_specs.create(name="ben", spec=spec)

    # exclude_unset: provider/description/etc. are NOT sent because the caller
    # never set them — matching the old **spec behavior.
    assert captured["body"] == {"name": "ben", "env": {"LOG_LEVEL": "debug"}, "secrets": {"TOK": "default/tok"}}


def test_environment_specs_create_accepts_dict_spec() -> None:
    """A plain dict passed as ``spec=`` is sent verbatim."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "ben"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    with _install_mock_transport(handler):
        client.environment_specs.create(name="ben", spec={"provider": "local"})

    assert captured["body"] == {"name": "ben", "provider": "local"}


def test_environment_specs_create_name_arg_is_authoritative() -> None:
    """An explicit ``name=`` wins over a ``name`` key smuggled in via ``spec``.

    Regression guard: the payload must apply ``name`` AFTER the spec/kwargs
    expansion so a dict spec carrying its own ``name`` cannot silently create the
    resource under a different name than the caller asked for.
    """
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "wanted"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    with _install_mock_transport(handler):
        client.environment_specs.create(name="wanted", spec={"name": "sneaky", "provider": "local"})

    assert captured["body"]["name"] == "wanted"


def test_environment_specs_create_kwargs_still_work() -> None:
    """Back-compat: loose ``**spec_kwargs`` are still accepted and override ``spec``."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "ben"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    with _install_mock_transport(handler):
        client.environment_specs.create(
            name="ben",
            spec=EnvironmentSpecInline(env={"A": "1"}),
            env={"A": "2"},  # kwarg wins over the typed model
        )

    assert captured["body"] == {"name": "ben", "env": {"A": "2"}}


def test_compute_specs_create_accepts_typed_model() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "big"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="team-a"))
    spec = ComputeSpecInline(resources=ComputeResources(limits={"cpu": "2"}))
    with _install_mock_transport(handler):
        client.compute_specs.create(name="big", spec=spec)

    assert captured["path"] == "/apis/agents/v2/workspaces/team-a/compute-specs"
    assert captured["body"] == {"name": "big", "resources": {"limits": {"cpu": "2"}}}


def test_environments_create_accepts_typed_model() -> None:
    """A typed ``AgentEnvironmentInline`` sends its set fields; ref args override."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read())
        return httpx.Response(201, json={"name": "env1"})

    client = AgentsResource(SimpleNamespace(base_url="http://test", workspace="default"))
    spec = AgentEnvironmentInline(environment_spec="default/ben")
    with _install_mock_transport(handler):
        client.environments.create(name="env1", spec=spec, compute_spec="default/big")

    assert captured["body"]["name"] == "env1"
    assert captured["body"]["environment_spec"] == "default/ben"
    # explicit compute_spec arg is applied on top of the typed spec
    assert captured["body"]["compute_spec"] == "default/big"


def test_default_headers_are_sent_on_every_request() -> None:
    """``platform.default_headers`` (how the CLI threads its token) reach the wire."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured.setdefault("auth", []).append(req.headers.get("authorization"))
        if req.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"name": "big"})

    platform = SimpleNamespace(
        base_url="http://test",
        workspace="team-a",
        default_headers={"Authorization": "Bearer tok-123"},
    )
    client = AgentsResource(platform)
    with _install_mock_transport(handler):
        client.compute_specs.create(name="big", spec=ComputeSpecInline())
        client.compute_specs.get("big")
        client.compute_specs.delete("big")

    assert captured["auth"] == ["Bearer tok-123", "Bearer tok-123", "Bearer tok-123"]
