# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Agent Toolkit adapter for NeMo Fabric.

One adapter host owns one entered NAT workflow context for the lifetime of a
Fabric runtime. The NAT configuration file remains the workflow source of truth.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

import nemo_fabric_adapters.common.utils as common_utils  # ty: ignore[unresolved-import]
from nemo_fabric_adapters.common import lifecycle  # ty: ignore[unresolved-import]
from pydantic_core import to_jsonable_python

LOGGER = logging.getLogger(__name__)
HARNESS = "nat"
MODE = "nat_workflow"
FUNCTION_GROUP_SEPARATOR = "__"


def main() -> None:
    """Serve the persistent local-host lifecycle protocol."""

    lifecycle.serve(NatRuntime)


def resolve_config_file(payload: dict[str, Any]) -> Path:
    """Resolve and validate the NAT config selected by harness settings."""

    settings = common_utils.settings_payload(payload)
    configured = settings.get("config_file")
    if not isinstance(configured, str) or not configured.strip():
        raise lifecycle.LifecycleError(
            "nat_config_file_required",
            "harness.settings.config_file must be a non-empty string",
        )

    base_dir = Path(common_utils.base_dir(payload)).resolve()
    candidate = Path(configured.strip())
    if not candidate.is_absolute():
        candidate = base_dir / candidate

    try:
        config_file = candidate.resolve(strict=True)
    except OSError as error:
        raise lifecycle.LifecycleError(
            "nat_config_file_not_found",
            "NAT config file does not exist",
            metadata={"config_file": configured},
        ) from error

    try:
        config_file.relative_to(base_dir)
    except ValueError as error:
        raise lifecycle.LifecycleError(
            "nat_config_file_outside_base_dir",
            "NAT config file must resolve within the agent config directory",
            metadata={"config_file": configured},
        ) from error

    if not config_file.is_file():
        raise lifecycle.LifecycleError(
            "nat_config_file_not_file",
            "NAT config file must be a regular file",
            metadata={"config_file": configured},
        )
    return config_file


def validate_supported_fabric_config(payload: dict[str, Any]) -> None:
    """Reject normalized config surfaces this adapter cannot map."""

    config = common_utils.fabric_config(payload)
    unsupported = [field for field in ("models", "telemetry", "relay") if config.get(field)]
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
            f"NAT adapter does not map normalized Fabric config fields: {', '.join(fields)}; "
            "configure them in the NAT config file",
            metadata={"fields": fields},
        )


def _native_capabilities(payload: dict[str, Any]) -> dict[str, Any]:
    native = common_utils.capability_plan(payload).get("native") or {}
    return native if isinstance(native, dict) else {}


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
async def load_nat_workflow(config_file: Path, payload: dict[str, Any]) -> AsyncIterator[Any]:
    """Load one NAT workflow, applying Fabric capabilities before it is built."""

    native = _native_capabilities(payload)
    if not native.get("mcp_servers") and not common_utils.blocked_tools(payload):
        from nat.runtime.loader import load_workflow

        async with load_workflow(config_file) as sessions:
            yield sessions
        return

    from nat.builder.workflow_builder import WorkflowBuilder
    from nat.runtime.loader import load_config
    from nat.runtime.session import SessionManager

    config = load_config(config_file)
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
        config_file = resolve_config_file(payload)
        stack = AsyncExitStack()

        try:
            sessions = await stack.enter_async_context(load_nat_workflow(config_file, payload))
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
                metadata={"config_file": str(config_file)},
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
