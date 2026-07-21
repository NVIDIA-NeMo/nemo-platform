# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from nemo_agents_plugin.cli import AgentsCLI
from typer.testing import CliRunner


class _ValidatedAgentConfig:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        return self._config


def _install_mock_transport(
    handler, *, on_create: Callable[[dict[str, Any]], None] | None = None
) -> AbstractContextManager[Any]:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _factory(*args, **kwargs):
        if on_create is not None:
            on_create(kwargs)
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    return patch("nemo_agents_plugin.cli.httpx.Client", _factory)


def test_no_args_prints_help_successfully() -> None:
    app = AgentsCLI().get_cli()
    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "Agent lifecycle management" in result.stdout


def test_list_404_prints_request_context_and_hint() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    app = AgentsCLI().get_cli()
    with _install_mock_transport(handler):
        result = CliRunner().invoke(app, ["list", "--base-url", "http://test"])

    assert result.exit_code == 1
    assert "Error: GET agent API failed: HTTP 404 Not Found" in result.stderr
    assert "Request: GET http://test/apis/agents/v2/workspaces/default/agents" in result.stderr
    assert "Target: agents API route /apis/agents/v2/workspaces/default/agents" in result.stderr
    assert "route may not be deployed" in result.stderr


@pytest.mark.parametrize("placeholder", ["${NEMO_DEFAULT_MODEL}", "$NEMO_DEFAULT_MODEL"])
def test_create_resolves_default_model_placeholder(tmp_path, placeholder: str) -> None:
    """`nemo agents create` resolves NEMO_DEFAULT_MODEL before POST.

    Regression for AIRCORE-613: the agents service has no user context at
    deploy time, so an unresolved literal would be persisted on the Agent.
    Covers both braced ``${VAR}`` and bare ``$VAR`` forms supported by
    ``expand_env_vars``.
    """
    import json as _json

    config = tmp_path / "agent.yml"
    config.write_text(f"llms:\n  llm:\n    _type: openai\n    model_name: {placeholder}\n")

    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.read()
        return httpx.Response(200, json={"name": "calc"})

    app = AgentsCLI().get_cli()
    with (
        _install_mock_transport(handler),
        patch("nemo_agents_plugin.utils.get_default_model", return_value="nvidia-nemotron-3-super-v3"),
    ):
        result = CliRunner().invoke(
            app, ["create", "--name", "calc", "--agent-config", str(config), "--base-url", "http://test"]
        )

    assert result.exit_code == 0, result.stderr
    sent = _json.loads(captured["body"])
    assert sent["config"]["llms"]["llm"]["model_name"] == "nvidia-nemotron-3-super-v3"
    assert sent["config_format"] == "nat-workflow-v1"


def test_create_validates_platform_agent_config_before_post(tmp_path) -> None:
    import json as _json

    config = tmp_path / "agent.yaml"
    config.write_text(
        "\n".join(
            [
                "config_format: nemo-agents-spec-v1",
                "name: fabric-agent",
                "default_harness: hermes",
                "harnesses:",
                "  hermes:",
                "    kind: hermes",
                "",
            ]
        )
    )
    normalized_config = {
        "config_format": "nemo-agents-spec-v1",
        "name": "fabric-agent",
        "default_harness": "hermes",
        "harnesses": {"hermes": {"kind": "hermes", "settings": {}}},
        "environment": {"provider": "local"},
    }
    captured: dict[str, Any] = {}

    async def _validate_platform_agent_config(config_dict: dict[str, Any], *, base_dir: Path):
        captured["validated_config"] = config_dict
        captured["base_dir"] = base_dir
        return type("ValidationResult", (), {"agent_config": _ValidatedAgentConfig(normalized_config)})()

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.read()
        return httpx.Response(200, json={"name": "fabric-agent"})

    app = AgentsCLI().get_cli()
    with (
        _install_mock_transport(handler),
        patch("nemo_agents_plugin.fabric.validation.validate_platform_agent_config", _validate_platform_agent_config),
    ):
        result = CliRunner().invoke(
            app,
            ["create", "--name", "fabric-agent", "--agent-config", str(config), "--base-url", "http://test"],
        )

    assert result.exit_code == 0, result.stderr
    sent = _json.loads(captured["body"])
    assert captured["base_dir"] == tmp_path
    assert captured["validated_config"]["config_format"] == "nemo-agents-spec-v1"
    assert sent["config"] == normalized_config
    assert sent["config_format"] == "nemo-agents-spec-v1"


def test_create_rejects_unsupported_config_format(tmp_path) -> None:
    config = tmp_path / "agent.yaml"
    config.write_text("config_format: custom-v2\nname: custom-agent\n")

    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("should not POST unsupported config_format")

    app = AgentsCLI().get_cli()
    with _install_mock_transport(handler):
        result = CliRunner().invoke(
            app,
            ["create", "--name", "custom-agent", "--agent-config", str(config), "--base-url", "http://test"],
        )

    assert result.exit_code == 1
    assert "unsupported config_format 'custom-v2'" in result.stderr


@pytest.mark.parametrize("placeholder", ["${NEMO_DEFAULT_MODEL}", "$NEMO_DEFAULT_MODEL"])
def test_create_aborts_when_default_model_missing(tmp_path, placeholder: str) -> None:
    """If no default model is selected, refuse to POST a config with an unresolved
    NEMO_DEFAULT_MODEL placeholder (braced or bare). Regression for AIRCORE-613."""
    config = tmp_path / "agent.yml"
    config.write_text(f"llms:\n  llm:\n    _type: openai\n    model_name: {placeholder}\n")

    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("should not POST when placeholder is unresolved")

    app = AgentsCLI().get_cli()
    with (
        _install_mock_transport(handler),
        patch("nemo_agents_plugin.utils.get_default_model", return_value=None),
    ):
        result = CliRunner().invoke(
            app, ["create", "--name", "calc", "--agent-config", str(config), "--base-url", "http://test"]
        )

    assert result.exit_code == 1
    assert "${NEMO_DEFAULT_MODEL}" in result.stderr
    assert "nemo setup" in result.stderr


def test_invoke_with_custom_timeout() -> None:
    """--timeout is threaded through to the httpx client."""
    captured_timeout: list[float | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "test", "choices": []})

    app = AgentsCLI().get_cli()
    with _install_mock_transport(handler, on_create=lambda kw: captured_timeout.append(kw.get("timeout"))):
        result = CliRunner().invoke(
            app,
            ["invoke", "--agent", "calc", "--input", "hi", "--base-url", "http://test", "--timeout", "42"],
        )

    assert result.exit_code == 0, result.stderr
    assert captured_timeout[0] == 42.0


def test_invoke_timeout_error_message() -> None:
    """Timeout errors print actionable guidance mentioning --timeout."""

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=req)

    app = AgentsCLI().get_cli()
    with _install_mock_transport(handler):
        result = CliRunner().invoke(
            app, ["invoke", "--agent", "calc", "--input", "hi", "--base-url", "http://test", "--timeout", "5"]
        )

    assert result.exit_code == 1
    assert "timed out" in result.stderr.lower()
    assert "--timeout" in result.stderr


def test_local_invoke_runs_fabric_config_once(tmp_path: Path) -> None:
    import json as _json

    from nemo_agents_plugin.fabric.runtime import FabricRuntimeResult

    config = tmp_path / "agent.yaml"
    config.write_text(
        "\n".join(
            [
                "config_format: nemo-agents-spec-v1",
                "name: fabric-agent",
                "default_harness: hermes",
                "harnesses:",
                "  hermes:",
                "    kind: hermes",
                "models:",
                "  default:",
                "    provider: openai",
                "    model: openai/gpt-5.4",
                "",
            ]
        )
    )
    captured: dict[str, Any] = {}

    async def _invoke_agent_config_once(config_dict: dict[str, Any], inputs: list[Any], *, base_dir: Path):
        captured["config"] = config_dict
        captured["inputs"] = inputs
        captured["base_dir"] = base_dir
        return [
            FabricRuntimeResult(
                status="succeeded",
                output={"response": "hello"},
                response="hello",
                runtime_id="runtime-1",
                invocation_id="invocation-1",
                request_id="request-1",
            )
        ]

    app = AgentsCLI().get_cli()
    with patch("nemo_agents_plugin.fabric.invocation.invoke_agent_config_once", _invoke_agent_config_once):
        result = CliRunner().invoke(app, ["invoke", "--agent-config", str(config), "--input", "hello"])

    assert result.exit_code == 0, result.stderr
    assert captured["base_dir"] == tmp_path
    assert captured["inputs"] == ["hello"]
    assert captured["config"]["config_format"] == "nemo-agents-spec-v1"
    parsed = _json.loads(result.stdout)
    assert parsed["status"] == "succeeded"
    assert parsed["response"] == "hello"
    assert parsed["runtime_id"] == "runtime-1"


def test_local_invoke_fabric_config_exits_nonzero_on_failed_result(tmp_path: Path) -> None:
    from nemo_agents_plugin.fabric.runtime import FabricRuntimeResult

    config = tmp_path / "agent.yaml"
    config.write_text(
        "\n".join(
            [
                "config_format: nemo-agents-spec-v1",
                "name: fabric-agent",
                "default_harness: hermes",
                "harnesses:",
                "  hermes:",
                "    kind: hermes",
                "models:",
                "  default:",
                "    provider: openai",
                "    model: openai/gpt-5.4",
                "",
            ]
        )
    )

    async def _invoke_agent_config_once(config_dict: dict[str, Any], inputs: list[Any], *, base_dir: Path):
        del config_dict, inputs, base_dir
        return [
            FabricRuntimeResult(
                status="failed",
                error={"stage": "invoke", "message": "adapter failed"},
                events=[{"kind": "invocation_end"}],
            )
        ]

    app = AgentsCLI().get_cli()
    with patch("nemo_agents_plugin.fabric.invocation.invoke_agent_config_once", _invoke_agent_config_once):
        result = CliRunner().invoke(app, ["invoke", "--agent-config", str(config), "--input", "hello"])

    assert result.exit_code == 1
    assert '"status": "failed"' in result.stdout
    assert "adapter failed" in result.stdout


def test_platform_invoke_writes_clean_json_to_stdout() -> None:
    """`nemo agents invoke --agent` returns JSON on stdout with no spinner bleed.

    AIRCORE-574: the spinner must render only on stderr so consumers can pipe
    stdout to `jq`. CliRunner's non-TTY stderr auto-disables the spinner, so
    here we just verify the response JSON is intact on stdout.
    """
    import json as _json

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    app = AgentsCLI().get_cli()
    with _install_mock_transport(handler):
        result = CliRunner().invoke(app, ["invoke", "--agent", "calc", "--input", "ping", "--base-url", "http://test"])

    assert result.exit_code == 0, result.stderr
    parsed = _json.loads(result.stdout)
    assert parsed["choices"][0]["message"]["content"] == "hi"


def test_platform_invoke_accepts_no_progress_flag() -> None:
    """`--no-progress` is wired through and doesn't break invocation."""
    import json as _json

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    app = AgentsCLI().get_cli()
    with _install_mock_transport(handler):
        result = CliRunner().invoke(
            app,
            ["invoke", "--agent", "calc", "--input", "ping", "--no-progress", "--base-url", "http://test"],
        )

    assert result.exit_code == 0, result.stderr
    assert _json.loads(result.stdout)["choices"][0]["message"]["content"] == "hi"


def test_list_connection_error_prints_request_context_and_hint() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    app = AgentsCLI().get_cli()
    with _install_mock_transport(handler):
        result = CliRunner().invoke(app, ["list", "--base-url", "http://test"])

    assert result.exit_code == 1
    assert "Error: GET agent API failed: connection refused" in result.stderr
    assert "Request: GET http://test/apis/agents/v2/workspaces/default/agents" in result.stderr
    assert "Target: agents API route /apis/agents/v2/workspaces/default/agents" in result.stderr
    assert "nemo config view" in result.stderr
