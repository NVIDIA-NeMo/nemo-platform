# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local HTTP server for Platform-managed Fabric agent runtimes."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from nemo_agents_plugin.agent_config import AgentConfig, load_agent_config
from nemo_agents_plugin.fabric.environment import release_runtime_base_dir, resolve_runtime_base_dir
from nemo_agents_plugin.fabric.runtime import (
    FabricInvocationRequest,
    FabricRuntimeExecutionError,
    FabricRuntimeResult,
    FabricRuntimeStream,
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
from nemo_agents_plugin.fabric.streaming import (
    iter_fabric_assistant_text_deltas,
    iter_openai_chat_completion_sse,
    openai_chat_completion_error_sse,
)
from nemo_agents_plugin.session_protocol import SESSION_ID_HEADER

logger = logging.getLogger(__name__)


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
    session_id: str | None,
) -> FabricInvocationRequest:
    """Translate the chat transcript into a Platform-owned Fabric request."""
    messages = request.messages
    # Interim behavior to get multi-turn in Studio chat.
    input_text = (
        messages[0].content
        if len(messages) == 1
        else "\n\n".join(f"{message.role}: {message.content}" for message in messages)
    )
    caller_context = {"session_id": session_id} if session_id is not None else {}
    return FabricInvocationRequest(
        input=input_text,
        caller_context=caller_context,
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


def _request_model_name(request: ChatCompletionRequest) -> str:
    model = getattr(request, "model", None)
    return model if isinstance(model, str) and model else "unknown-model"


def _failed_result_detail(result: FabricRuntimeResult) -> str:
    if isinstance(result.error, Mapping):
        message = result.error.get("message")
        if isinstance(message, str):
            return message
    return f"Fabric invocation returned status {result.status!r}."


async def _validate_agent_config(config: AgentConfig, *, base_dir: Path) -> Any:
    from nemo_agents_plugin.fabric.validation import validate_platform_agent_config

    return await validate_platform_agent_config(config, base_dir=base_dir)


def _iter_streaming_chat_completion(
    stream_context: AbstractAsyncContextManager[FabricRuntimeStream],
    fabric_stream: FabricRuntimeStream,
    *,
    completion_id: str,
    model: str,
) -> AsyncIterator[str]:
    return _StreamingChatCompletionIterator(
        stream_context,
        fabric_stream,
        completion_id=completion_id,
        model=model,
    )


class _StreamingChatCompletionIterator:
    """Async iterator that owns cleanup even when response iteration never starts."""

    def __init__(
        self,
        stream_context: AbstractAsyncContextManager[FabricRuntimeStream],
        fabric_stream: FabricRuntimeStream,
        *,
        completion_id: str,
        model: str,
    ) -> None:
        self._stream_context = stream_context
        self._fabric_stream = fabric_stream
        self._completion_id = completion_id
        self._model = model
        self._events: AsyncGenerator[str, None] | None = None
        self._close_fabric_stream_on_exit = True
        self._closed = False

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        if self._closed:
            raise StopAsyncIteration
        if self._events is None:
            self._events = self._iter_events()
        try:
            return await self._events.__anext__()
        except StopAsyncIteration:
            await self.aclose()
            raise
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._events is not None:
            await self._events.aclose()
        if self._close_fabric_stream_on_exit:
            await _close_interrupted_stream(self._fabric_stream)
        await self._stream_context.__aexit__(None, None, None)

    async def _iter_events(self) -> AsyncGenerator[str, None]:
        try:
            text_deltas = iter_fabric_assistant_text_deltas(self._fabric_stream)
            async for event in iter_openai_chat_completion_sse(
                completion_id=self._completion_id,
                content_chunks=text_deltas,
                model=self._model,
            ):
                yield event
            self._close_fabric_stream_on_exit = False
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Fabric streaming chat completion failed.")
            yield openai_chat_completion_error_sse(error)


async def _close_interrupted_stream(fabric_stream: FabricRuntimeStream) -> None:
    try:
        await fabric_stream.aclose()
    except Exception:
        logger.exception("Failed to finalize interrupted Fabric stream.")


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
        runtime_base_dir = await asyncio.to_thread(resolve_runtime_base_dir, config_path)
        base_dir = runtime_base_dir.path
        # Startup can still fail past this point, and a staged root must not outlive
        # the process that made it even when the runtime never comes up.
        try:
            validation_result = await _validate_agent_config(agent_config, base_dir=base_dir)
            app.state.agent_config = agent_config
            app.state.base_dir = base_dir
            app.state.validation_result = validation_result
            session_registry = FabricSessionRegistry()
            app.state.session_registry = session_registry
            session_manager = FabricSessionManager(
                agent_config,
                base_dir=base_dir,
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
                    # A staged root is only safe to remove once no runtime can still write to it.
                    await session_manager.close_all_sessions()
        finally:
            await asyncio.to_thread(release_runtime_base_dir, runtime_base_dir)

    app = FastAPI(title="NeMo Agents Fabric Server", lifespan=lifespan)
    runtime_instance_id = str(uuid.uuid4())
    runtime_started_at = datetime.now(UTC)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "runtime_instance_id": runtime_instance_id,
            "runtime_started_at": runtime_started_at.isoformat(),
        }

    @app.post("/v1/chat/completions", response_model=None, response_model_exclude_none=True)
    async def chat_completions(
        request: ChatCompletionRequest,
        response: Response,
        session_id: Annotated[str | None, Header(alias=SESSION_ID_HEADER)] = None,
    ) -> ChatCompletionResponse | StreamingResponse:
        response_headers: dict[str, str] | None = None
        if session_id is None:
            invocation_request = _to_fabric_invocation_request(request, session_id=None)
            invoke = app.state.session_manager.invoke_once
            stream = app.state.session_manager.stream_once
        else:
            try:
                session = await app.state.session_manager.resolve_session(session_id)
            except FabricSessionNotFoundError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            except FabricSessionStartError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
            invocation_request = _to_fabric_invocation_request(request, session_id=session.session_id)
            response_headers = _session_headers(session.session_id)
            invoke = partial(app.state.session_manager.invoke_session, session)
            stream = partial(app.state.session_manager.stream_session, session)

        if request.stream:
            stream_context = stream(invocation_request)
            try:
                fabric_stream = await stream_context.__aenter__()
            except FabricSessionStartError as error:
                raise HTTPException(status_code=503, detail=str(error), headers=response_headers) from error
            except FabricSessionNotFoundError as error:
                raise HTTPException(
                    status_code=404,
                    detail=str(error),
                    headers=response_headers,
                ) from error
            except FabricRuntimeExecutionError as error:
                raise HTTPException(
                    status_code=502,
                    detail=str(error),
                    headers=response_headers,
                ) from error
            return StreamingResponse(
                _iter_streaming_chat_completion(
                    stream_context,
                    fabric_stream,
                    completion_id=f"chatcmpl-{uuid.uuid4().hex}",
                    model=_request_model_name(request),
                ),
                media_type="text/event-stream",
                headers=response_headers,
            )

        try:
            result = await invoke(invocation_request)
        except FabricSessionStartError as error:
            raise HTTPException(status_code=503, detail=str(error), headers=response_headers) from error
        except FabricSessionNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
                headers=response_headers,
            ) from error
        except FabricRuntimeTimeoutError as error:
            raise HTTPException(
                status_code=504,
                detail=str(error),
                headers=response_headers,
            ) from error
        except FabricRuntimeExecutionError as error:
            raise HTTPException(
                status_code=502,
                detail=str(error),
                headers=response_headers,
            ) from error

        if result.status != "succeeded":
            raise HTTPException(
                status_code=502,
                detail=_failed_result_detail(result),
                headers=response_headers,
            )

        try:
            completion = _to_chat_completion_response(result)
        except ValueError as error:
            raise HTTPException(
                status_code=502,
                detail=str(error),
                headers=response_headers,
            ) from error

        if response_headers is not None:
            response.headers.update(response_headers)
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
    # Overrides must stay aligned with the gateway timeout used to compute
    # persisted ``expires_at``; ideally both come from the deployment config.
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
