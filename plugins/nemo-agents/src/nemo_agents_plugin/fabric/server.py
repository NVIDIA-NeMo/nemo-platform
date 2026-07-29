# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local HTTP server for Platform-managed Fabric agent runtimes."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Response
from nemo_agents_plugin.agent_config import AgentConfig, load_agent_config
from nemo_agents_plugin.fabric.runtime import (
    FabricInvocationRequest,
    FabricRuntimeExecutionError,
    FabricRuntimeResult,
    FabricRuntimeTimeoutError,
)
from nemo_agents_plugin.fabric.serving_models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseMessage,
)
from nemo_agents_plugin.fabric.session_manager import (
    DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS,
    DEFAULT_MAX_CONCURRENT_INVOCATIONS,
    DEFAULT_SESSION_CLEANUP_INTERVAL_SECONDS,
    FabricSessionManager,
    FabricSessionStartError,
    FabricSessionStopError,
)
from nemo_agents_plugin.fabric.session_registry import FabricSessionNotFoundError, FabricSessionRegistry

logger = logging.getLogger(__name__)

SESSION_ID_HEADER = "X-Nemo-Session-Id"


@dataclass(frozen=True, slots=True)
class FabricServingSettings:
    """Operational settings for the Platform-owned Fabric server."""

    max_concurrent_invocations: int = DEFAULT_MAX_CONCURRENT_INVOCATIONS
    idle_session_timeout_seconds: float = DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS
    session_cleanup_interval_seconds: float = DEFAULT_SESSION_CLEANUP_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        if self.max_concurrent_invocations < 0:
            raise ValueError("max_concurrent_invocations must be greater than or equal to zero.")
        if self.idle_session_timeout_seconds <= 0:
            raise ValueError("idle_session_timeout_seconds must be greater than zero.")
        if self.session_cleanup_interval_seconds <= 0:
            raise ValueError("session_cleanup_interval_seconds must be greater than zero.")


def _to_fabric_invocation_request(
    request: ChatCompletionRequest,
    *,
    session_id: str,
) -> FabricInvocationRequest:
    """Translate the current chat turn into a Platform-owned Fabric request."""
    return FabricInvocationRequest(
        input=request.messages[-1].content,
        caller_context={"session_id": session_id},
    )


def _to_chat_completion_response(result: FabricRuntimeResult) -> ChatCompletionResponse:
    """Convert a successful Fabric result into an OpenAI-compatible response."""
    if not isinstance(result.response, str):
        raise ValueError("Fabric invocation did not return a text response.")

    usage = None
    if isinstance(result.output, Mapping) and isinstance(result.output.get("usage"), Mapping):
        usage = dict(result.output["usage"])

    return ChatCompletionResponse(
        id=result.invocation_id or result.request_id or result.runtime_id or f"chatcmpl-{uuid.uuid4().hex}",
        choices=[
            ChatCompletionChoice(
                message=ChatCompletionResponseMessage(content=result.response),
            )
        ],
        usage=usage,
    )


def _session_headers(session_id: str) -> dict[str, str]:
    return {SESSION_ID_HEADER: session_id}


def _failed_result_detail(result: FabricRuntimeResult) -> str:
    if isinstance(result.error, Mapping):
        message = result.error.get("message")
        if isinstance(message, str):
            return message
    return f"Fabric invocation returned status {result.status!r}."


async def _validate_agent_config(config: AgentConfig, *, base_dir: Path) -> Any:
    from nemo_agents_plugin.fabric.validation import validate_platform_agent_config

    return await validate_platform_agent_config(config, base_dir=base_dir)


async def _run_idle_session_cleanup(
    manager: FabricSessionManager,
    *,
    idle_timeout_seconds: float,
    cleanup_interval_seconds: float,
    shutdown_event: asyncio.Event,
) -> None:
    """Periodically expire inactive logical sessions until shutdown."""
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=cleanup_interval_seconds)
        except TimeoutError:
            try:
                await manager.expire_idle_sessions(idle_timeout_seconds=idle_timeout_seconds)
            except Exception:
                logger.exception("Failed to expire idle Fabric sessions.")


def create_fabric_serving_app(
    agent_config_path: str | Path,
    *,
    settings: FabricServingSettings | None = None,
) -> FastAPI:
    """Create a serving app that validates its agent definition at startup."""
    settings = settings or FabricServingSettings()
    config_path = Path(agent_config_path).resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        agent_config = load_agent_config(config_path)
        validation_result = await _validate_agent_config(agent_config, base_dir=config_path.parent)
        app.state.agent_config = agent_config
        app.state.base_dir = config_path.parent
        app.state.validation_result = validation_result
        session_registry = FabricSessionRegistry()
        app.state.session_registry = session_registry
        session_manager = FabricSessionManager(
            agent_config,
            base_dir=config_path.parent,
            session_registry=session_registry,
            max_concurrent_invocations=settings.max_concurrent_invocations,
        )
        app.state.session_manager = session_manager
        cleanup_shutdown = asyncio.Event()
        cleanup_task = asyncio.create_task(
            _run_idle_session_cleanup(
                session_manager,
                idle_timeout_seconds=settings.idle_session_timeout_seconds,
                cleanup_interval_seconds=settings.session_cleanup_interval_seconds,
                shutdown_event=cleanup_shutdown,
            )
        )
        logger.info("Validated Fabric-backed agent config at %s", config_path)
        try:
            yield
        finally:
            cleanup_shutdown.set()
            try:
                await cleanup_task
            finally:
                await session_manager.close_all_sessions()

    app = FastAPI(title="NeMo Agents Fabric Server", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions", response_model_exclude_none=True)
    async def chat_completions(
        request: ChatCompletionRequest,
        response: Response,
        session_id: Annotated[str | None, Header(alias=SESSION_ID_HEADER)] = None,
    ) -> ChatCompletionResponse:
        try:
            session = await app.state.session_manager.resolve_session(session_id)
        except FabricSessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except FabricSessionStartError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        invocation_request = _to_fabric_invocation_request(request, session_id=session.session_id)
        try:
            result = await app.state.session_manager.invoke_session(session, invocation_request)
        except FabricSessionNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
                headers=_session_headers(session.session_id),
            ) from error
        except FabricRuntimeTimeoutError as error:
            raise HTTPException(
                status_code=504,
                detail=str(error),
                headers=_session_headers(session.session_id),
            ) from error
        except FabricRuntimeExecutionError as error:
            raise HTTPException(
                status_code=502,
                detail=str(error),
                headers=_session_headers(session.session_id),
            ) from error

        if result.status != "succeeded":
            raise HTTPException(
                status_code=502,
                detail=_failed_result_detail(result),
                headers=_session_headers(session.session_id),
            )

        try:
            completion = _to_chat_completion_response(result)
        except ValueError as error:
            raise HTTPException(
                status_code=502,
                detail=str(error),
                headers=_session_headers(session.session_id),
            ) from error

        response.headers[SESSION_ID_HEADER] = session.session_id
        return completion

    @app.delete("/v1/sessions/{session_id}", status_code=204)
    async def close_session(session_id: str) -> Response:
        try:
            await app.state.session_manager.close_session(session_id)
        except FabricSessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except FabricSessionStopError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return Response(status_code=204)

    return app


def main(argv: list[str] | None = None) -> int:
    """Run the local Fabric agent server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-config", required=True, type=Path, help="Path to an agent YAML config file.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--max-concurrent-invocations",
        type=int,
        default=DEFAULT_MAX_CONCURRENT_INVOCATIONS,
        help="Maximum concurrent Fabric invocations; use 0 for unlimited.",
    )
    parser.add_argument(
        "--idle-session-timeout-seconds",
        type=float,
        default=DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS,
        help="Seconds of inactivity before a logical session expires.",
    )
    parser.add_argument(
        "--session-cleanup-interval-seconds",
        type=float,
        default=DEFAULT_SESSION_CLEANUP_INTERVAL_SECONDS,
        help="Seconds between idle-session cleanup checks.",
    )
    args = parser.parse_args(argv)

    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        create_fabric_serving_app(
            args.agent_config,
            settings=FabricServingSettings(
                max_concurrent_invocations=args.max_concurrent_invocations,
                idle_session_timeout_seconds=args.idle_session_timeout_seconds,
                session_cleanup_interval_seconds=args.session_cleanup_interval_seconds,
            ),
        ),
        host=args.host,
        port=args.port,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
