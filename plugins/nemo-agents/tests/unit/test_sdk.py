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
from nemo_agents_plugin.sdk import AgentsResource
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
