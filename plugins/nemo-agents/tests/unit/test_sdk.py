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
