# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Agent Toolkit adapter for NeMo Fabric.

One adapter host owns one entered NAT workflow context for the lifetime of a
Fabric runtime. The NAT configuration file remains the workflow source of truth.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import nemo_fabric_adapters.common.utils as common_utils  # ty: ignore[unresolved-import]
from nemo_fabric_adapters.common import lifecycle  # ty: ignore[unresolved-import]
from pydantic_core import to_jsonable_python

LOGGER = logging.getLogger(__name__)
HARNESS = "nat"
MODE = "nat_workflow"


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
    """Reject normalized config surfaces this config-file adapter does not map."""

    config = common_utils.fabric_config(payload)
    unsupported = [field for field in ("models", "mcp", "skills", "tools", "telemetry", "relay") if config.get(field)]
    if unsupported:
        fields = ", ".join(sorted(unsupported))
        raise lifecycle.LifecycleError(
            "nat_unsupported_fabric_config",
            f"NAT adapter does not map normalized Fabric config fields: {fields}; "
            "configure them in the NAT config file",
            metadata={"fields": sorted(unsupported)},
        )


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
            from nat.runtime.loader import load_workflow

            sessions = await stack.enter_async_context(load_workflow(config_file))
        except asyncio.CancelledError:
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
