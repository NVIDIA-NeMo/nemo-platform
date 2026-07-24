# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Agent Toolkit adapter for NeMo Fabric.

One adapter host owns one entered NAT workflow context for the lifetime of a
Fabric runtime. Platform's normalized Fabric config is the source of truth.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import nemo_fabric_adapters.common.utils as common_utils  # ty: ignore[unresolved-import]
from nemo_agents_plugin.agent_config import NatHarnessSettings
from nemo_fabric_adapters.common import lifecycle  # ty: ignore[unresolved-import]
from pydantic import ValidationError
from pydantic_core import to_jsonable_python

LOGGER = logging.getLogger(__name__)
HARNESS = "nat"
MODE = "nat_workflow"
FUNCTION_GROUP_SEPARATOR = "__"
DEFAULT_LLM_NAME = "default"
PROVIDER_TO_NAT_LLM = {
    "nim": "nim",
    "nvidia": "nim",
    "openai": "openai",
}
TOOL_COMPONENTS: dict[str, tuple[str, dict[str, Any]]] = {
    "calculator": ("function_groups", {"_type": "calculator"}),
    "current_datetime": ("functions", {"_type": "current_datetime"}),
    "email_phishing_analyzer": (
        "functions",
        {
            "_type": "email_phishing_analyzer",
            "llm": DEFAULT_LLM_NAME,
        },
    ),
}
RESERVED_MODEL_SETTINGS = frozenset(
    {
        "_type",
        "type",
        "provider",
        "model",
        "model_name",
        "api_key",
        "api_key_env",
        "temperature",
    }
)


def main() -> None:
    """Serve the persistent local-host lifecycle protocol."""

    lifecycle.serve(NatRuntime)


def validate_supported_fabric_config(payload: dict[str, Any]) -> None:
    """Reject normalized config surfaces this adapter cannot map."""

    config = common_utils.fabric_config(payload)
    unsupported = [field for field in ("telemetry", "relay") if config.get(field)]
    skills = config.get("skills") or {}
    if isinstance(skills, dict) and skills.get("paths"):
        unsupported.append("skills")

    unsupported_plan = common_utils.capability_plan(payload).get("unsupported") or {}
    if unsupported_plan.get("mcp_servers"):
        unsupported.append("mcp")
    if unsupported_plan.get("skill_paths") and "skills" not in unsupported:
        unsupported.append("skills")

    if unsupported:
        fields = sorted(set(unsupported))
        raise lifecycle.LifecycleError(
            "nat_unsupported_fabric_config",
            f"NAT adapter does not map normalized Fabric config fields: {', '.join(fields)}",
            metadata={"fields": fields},
        )


def _native_capabilities(payload: dict[str, Any]) -> dict[str, Any]:
    native = common_utils.capability_plan(payload).get("native") or {}
    return native if isinstance(native, dict) else {}


def _fabric_models(payload: dict[str, Any]) -> dict[str, Any]:
    models = common_utils.fabric_config(payload).get("models") or {}
    if not isinstance(models, dict):
        raise lifecycle.LifecycleError(
            "nat_invalid_models",
            "Fabric models must be a mapping",
        )
    return models


def _nat_settings(payload: dict[str, Any]) -> NatHarnessSettings:
    """Validate the Platform-owned NAT harness contract."""

    try:
        return NatHarnessSettings.model_validate(common_utils.settings_payload(payload))
    except ValidationError as error:
        raise lifecycle.LifecycleError(
            "nat_invalid_harness_settings",
            "NAT harness settings are invalid",
        ) from error


def _nat_llm_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate the normalized default Fabric model into a native NAT LLM config."""

    models = _fabric_models(payload)
    if set(models) != {DEFAULT_LLM_NAME}:
        raise lifecycle.LifecycleError(
            "nat_invalid_models",
            "NAT react workflows require exactly one Fabric model named 'default'",
            metadata={"models": sorted(models)},
        )

    model = models[DEFAULT_LLM_NAME]
    if not isinstance(model, dict):
        raise lifecycle.LifecycleError(
            "nat_invalid_models",
            "Fabric model 'default' must be a mapping",
        )

    provider = model.get("provider")
    if not isinstance(provider, str) or provider not in PROVIDER_TO_NAT_LLM:
        raise lifecycle.LifecycleError(
            "nat_model_provider_unsupported",
            "NAT supports Fabric model providers: nim, nvidia, openai",
            metadata={"provider": provider},
        )

    model_name = model.get("model")
    if not isinstance(model_name, str) or not model_name:
        raise lifecycle.LifecycleError(
            "nat_invalid_models",
            "Fabric model 'default' requires a non-empty model",
        )

    settings = model.get("settings") or {}
    if not isinstance(settings, dict):
        raise lifecycle.LifecycleError(
            "nat_invalid_models",
            "Fabric model 'default' settings must be a mapping",
        )
    reserved = sorted(RESERVED_MODEL_SETTINGS.intersection(settings))
    if reserved:
        raise lifecycle.LifecycleError(
            "nat_model_settings_reserved",
            "Fabric model 'default' settings cannot replace normalized or NAT type fields",
            metadata={"llm": DEFAULT_LLM_NAME, "fields": reserved},
        )

    values = dict(settings)
    values["_type"] = PROVIDER_TO_NAT_LLM[provider]
    values["model_name"] = model_name

    temperature = model.get("temperature")
    if temperature is not None:
        values["temperature"] = temperature

    api_key_env = model.get("api_key_env")
    if api_key_env is not None:
        if not isinstance(api_key_env, str) or not api_key_env:
            raise lifecycle.LifecycleError(
                "nat_invalid_models",
                "Fabric model 'default' api_key_env must be a non-empty string",
            )
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise lifecycle.LifecycleError(
                "nat_model_api_key_missing",
                f"Fabric model 'default' requires environment variable {api_key_env!r}",
                metadata={"llm": DEFAULT_LLM_NAME, "api_key_env": api_key_env},
            )
        values["api_key"] = api_key
    return values


def build_nat_config(payload: dict[str, Any]) -> Any:
    """Translate normalized Fabric config into a validated typed NAT Config."""

    settings = _nat_settings(payload)
    raw_config: dict[str, Any] = {}

    if settings.workflow == "current_timezone":
        if _fabric_models(payload):
            raise lifecycle.LifecycleError(
                "nat_invalid_models",
                "NAT current_timezone workflow does not accept Fabric models",
            )
        raw_config["workflow"] = {"_type": "current_timezone"}
    else:
        functions: dict[str, Any] = {}
        function_groups: dict[str, Any] = {}
        for tool_name in settings.tools:
            section, component = TOOL_COMPONENTS[tool_name]
            target = functions if section == "functions" else function_groups
            target[tool_name] = dict(component)

        raw_config.update(
            {
                "functions": functions,
                "function_groups": function_groups,
                "llms": {
                    DEFAULT_LLM_NAME: _nat_llm_config(payload),
                },
                "workflow": {
                    "_type": "react_agent",
                    "tool_names": list(settings.tools),
                    "llm_name": DEFAULT_LLM_NAME,
                    "verbose": False,
                    "parse_agent_response_max_retries": 3,
                    "use_native_tool_calling": True,
                },
            }
        )
        if settings.instructions is not None:
            raw_config["workflow"]["additional_instructions"] = settings.instructions

    from nat.data_models.config import Config
    from nat.runtime.loader import PluginTypes, discover_and_register_plugins
    from nat.utils.data_models.schema_validator import validate_schema

    discover_and_register_plugins(PluginTypes.CONFIG_OBJECT)
    try:
        return validate_schema(raw_config, Config)
    except ValueError as error:
        raise lifecycle.LifecycleError(
            "nat_config_translation_failed",
            "Normalized Fabric config could not be translated into a valid NAT config",
        ) from error


def _nat_mcp_server_config(name: str, server: Any) -> Any:
    if not isinstance(server, dict):
        raise lifecycle.LifecycleError(
            "nat_invalid_mcp_server",
            f"NAT MCP server {name!r} must be a mapping",
        )

    transport = str(server.get("transport") or "").strip().lower().replace("_", "-")
    target = os.path.expandvars(str(server.get("url") or "")).strip()
    if not target:
        raise lifecycle.LifecycleError(
            "nat_invalid_mcp_server",
            f"NAT MCP server {name!r} requires a non-empty url",
        )

    try:
        from nat.plugins.mcp.client.client_config import MCPServerConfig
    except ImportError as error:
        raise lifecycle.LifecycleError(
            "nat_mcp_dependency_missing",
            "NAT MCP mapping requires the nvidia-nat-mcp package",
        ) from error

    if transport in {"stdio", "command", "process"}:
        try:
            command = shlex.split(target)
        except ValueError as error:
            raise lifecycle.LifecycleError(
                "nat_invalid_mcp_server",
                f"NAT MCP server {name!r} has an invalid stdio command",
            ) from error
        if not command:
            raise lifecycle.LifecycleError(
                "nat_invalid_mcp_server",
                f"NAT MCP server {name!r} has an empty stdio command",
            )
        return MCPServerConfig(transport="stdio", command=command[0], args=command[1:])

    if transport in {"", "http", "streamable-http", "streamablehttp"}:
        transport = "streamable-http"
    if transport not in {"sse", "streamable-http"}:
        raise lifecycle.LifecycleError(
            "nat_unsupported_mcp_transport",
            f"NAT MCP server {name!r} has unsupported transport {transport!r}",
        )
    return MCPServerConfig.model_validate({"transport": transport, "url": target})


def _workflow_tool_names(config: Any) -> list[Any]:
    tool_names = getattr(config.workflow, "tool_names", None)
    if not isinstance(tool_names, list):
        raise lifecycle.LifecycleError(
            "nat_workflow_tools_unsupported",
            "NAT MCP mapping requires a workflow with a tool_names field",
        )
    return tool_names


def _apply_mcp_servers(config: Any, payload: dict[str, Any]) -> None:
    servers = _native_capabilities(payload).get("mcp_servers") or {}
    if not servers:
        return
    if not isinstance(servers, dict):
        raise lifecycle.LifecycleError(
            "nat_invalid_mcp_config",
            "NAT native MCP capability plan must be a mapping",
        )

    try:
        from nat.plugins.mcp.client.client_config import MCPClientConfig
    except ImportError as error:
        raise lifecycle.LifecycleError(
            "nat_mcp_dependency_missing",
            "NAT MCP mapping requires the nvidia-nat-mcp package",
        ) from error

    tool_names = _workflow_tool_names(config)
    for name, server in sorted(servers.items()):
        if not isinstance(name, str) or not name:
            raise lifecycle.LifecycleError(
                "nat_invalid_mcp_server",
                "NAT MCP server names must be non-empty strings",
            )
        if name in config.functions or name in config.function_groups:
            raise lifecycle.LifecycleError(
                "nat_mcp_name_conflict",
                f"NAT MCP server {name!r} conflicts with an existing function or function group",
            )
        config.function_groups[name] = MCPClientConfig(server=_nat_mcp_server_config(name, server))
        if name not in {str(tool_name) for tool_name in tool_names}:
            tool_names.append(name)


def _exclude_group_member(config: Any, group_name: str, member_name: str, tool_names: list[Any] | None) -> None:
    group = config.function_groups.get(group_name)
    if group is None:
        return

    included = list(getattr(group, "include", []))
    if included:
        if member_name not in included:
            return
        remaining = [name for name in included if name != member_name]
        if remaining:
            group.include = remaining
            return
        config.function_groups.pop(group_name, None)
        if tool_names is not None:
            tool_names[:] = [tool_name for tool_name in tool_names if str(tool_name) != group_name]
        return

    excluded = list(getattr(group, "exclude", []))
    if member_name not in excluded:
        group.exclude = [*excluded, member_name]


def _apply_blocked_tools(config: Any, payload: dict[str, Any]) -> None:
    blocked = set(common_utils.blocked_tools(payload))
    if not blocked:
        return

    tool_names = getattr(config.workflow, "tool_names", None)
    if isinstance(tool_names, list):
        tool_names[:] = [tool_name for tool_name in tool_names if str(tool_name) not in blocked]
    else:
        tool_names = None

    for name in blocked:
        config.functions.pop(name, None)
        config.function_groups.pop(name, None)
        if FUNCTION_GROUP_SEPARATOR in name:
            group_name, member_name = name.split(FUNCTION_GROUP_SEPARATOR, 1)
            _exclude_group_member(config, group_name, member_name, tool_names)


def apply_nat_capabilities(config: Any, payload: dict[str, Any]) -> None:
    """Map routed Fabric capabilities into a loaded NAT config."""

    _apply_mcp_servers(config, payload)
    _apply_blocked_tools(config, payload)


@asynccontextmanager
async def load_nat_workflow(payload: dict[str, Any]) -> AsyncIterator[Any]:
    """Build one NAT workflow from normalized Fabric config."""

    from nat.builder.workflow_builder import WorkflowBuilder
    from nat.runtime.session import SessionManager

    config = build_nat_config(payload)
    apply_nat_capabilities(config, payload)
    async with WorkflowBuilder.from_config(config=config) as builder:
        sessions = await SessionManager.create(config=config, shared_builder=builder)
        try:
            yield sessions
        finally:
            await sessions.shutdown()


def _runtime_id(payload: dict[str, Any]) -> str:
    try:
        return common_utils.runtime_id(payload)
    except ValueError as error:
        raise lifecycle.LifecycleError(
            "nat_invalid_runtime_context",
            "NAT lifecycle payload is missing a runtime ID",
        ) from error


def _session_kwargs(request: dict[str, Any]) -> dict[str, str]:
    context = request.get("context") or {}
    if not isinstance(context, dict):
        raise ValueError("request.context must be a mapping")

    values = {
        "user_id": context.get("user_id"),
        "conversation_id": context.get("conversation_id"),
        "user_message_id": context.get("user_message_id") or request.get("request_id"),
    }
    session_kwargs: dict[str, str] = {}
    for name, value in values.items():
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(f"request context {name} must be a non-empty string")
        session_kwargs[name] = value
    return session_kwargs


def _success_output(response: Any) -> dict[str, Any]:
    return {
        "harness": HARNESS,
        "adapter": "python",
        "mode": MODE,
        "response": response,
        "completed": True,
        "failed": False,
        "error": None,
    }


def _failure_output(code: str, message: str) -> dict[str, Any]:
    return {
        "harness": HARNESS,
        "adapter": "python",
        "mode": MODE,
        "response": None,
        "completed": False,
        "failed": True,
        "error": {
            "code": code,
            "message": message,
            "retryable": False,
        },
    }


async def _close_after_failed_start(stack: AsyncExitStack) -> None:
    try:
        await stack.aclose()
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("NAT workflow cleanup failed after start error")


class NatRuntime:
    """One entered NAT workflow and session manager owned by a Fabric runtime."""

    def __init__(self) -> None:
        self._runtime_id: str | None = None
        self._sessions: Any = None
        self._exit_stack: AsyncExitStack | None = None

    async def start(self, payload: dict[str, Any]) -> None:
        if self._exit_stack is not None:
            raise lifecycle.LifecycleError(
                "nat_runtime_already_started",
                "NAT runtime is already started",
            )

        runtime_id = _runtime_id(payload)
        validate_supported_fabric_config(payload)
        stack = AsyncExitStack()

        try:
            sessions = await stack.enter_async_context(load_nat_workflow(payload))
        except asyncio.CancelledError:
            await _close_after_failed_start(stack)
            raise
        except lifecycle.LifecycleError:
            await _close_after_failed_start(stack)
            raise
        except Exception as error:
            LOGGER.exception("NAT workflow failed to load")
            await _close_after_failed_start(stack)
            raise lifecycle.LifecycleError(
                "nat_workflow_start_failed",
                "NAT workflow failed to load; inspect adapter stderr for details",
            ) from error

        self._runtime_id = runtime_id
        self._sessions = sessions
        self._exit_stack = stack

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._sessions is None or self._runtime_id is None:
            raise lifecycle.LifecycleError(
                "nat_runtime_not_started",
                "NAT runtime is not started",
            )
        if _runtime_id(payload) != self._runtime_id:
            raise lifecycle.LifecycleError(
                "nat_runtime_mismatch",
                "NAT invocation does not match the active runtime",
            )

        request = common_utils.request_payload(payload)
        try:
            from nat.data_models.runtime_enum import RuntimeTypeEnum

            async with self._sessions.session(**_session_kwargs(request)) as session:
                async with session.run(
                    request.get("input", ""),
                    runtime_type=RuntimeTypeEnum.RUN_OR_SERVE,
                ) as runner:
                    result = await runner.result()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("NAT workflow invocation failed")
            return _failure_output(
                "nat_workflow_invoke_failed",
                "NAT workflow invocation failed; inspect adapter stderr for details",
            )

        try:
            response = to_jsonable_python(result, serialize_unknown=False)
        except (TypeError, ValueError):
            LOGGER.exception("NAT workflow returned a non-JSON result")
            return _failure_output(
                "nat_result_not_json_serializable",
                "NAT workflow returned a result that cannot be represented as JSON",
            )
        return _success_output(response)

    async def stop(self) -> None:
        stack = self._exit_stack
        self._runtime_id = None
        self._sessions = None
        self._exit_stack = None

        if stack is None:
            return
        try:
            await stack.aclose()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOGGER.exception("NAT workflow failed to stop cleanly")
            raise lifecycle.LifecycleError(
                "nat_runtime_stop_failed",
                "NAT runtime failed to stop cleanly",
            ) from error


if __name__ == "__main__":
    main()
