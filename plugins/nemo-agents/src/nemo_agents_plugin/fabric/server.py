# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local HTTP server for Platform-managed Fabric agent runtimes."""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Response
from nemo_agents_plugin.agent_config import AgentConfig, load_agent_config
from nemo_agents_plugin.fabric.runtime import (
    FabricInvocationRequest,
    FabricRuntimeExecutionError,
    FabricRuntimeResult,
    FabricRuntimeTimeoutError,
    invoke_fabric_runtime,
)
from nemo_agents_plugin.fabric.serving_models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseMessage,
)
from nemo_agents_plugin.fabric.session_manager import FabricSessionManager, FabricSessionStartError
from nemo_agents_plugin.fabric.session_registry import FabricSessionNotFoundError, FabricSessionRegistry

logger = logging.getLogger(__name__)

SESSION_ID_HEADER = "X-Nemo-Session-Id"


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


def create_fabric_serving_app(agent_config_path: str | Path) -> FastAPI:
    """Create a serving app that validates its agent definition at startup."""
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
        app.state.session_manager = FabricSessionManager(
            agent_config,
            base_dir=config_path.parent,
            session_registry=session_registry,
        )
        logger.info("Validated Fabric-backed agent config at %s", config_path)
        yield

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
            result = await invoke_fabric_runtime(session.runtime, invocation_request)
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

    return app


def main(argv: list[str] | None = None) -> int:
    """Run the local Fabric agent server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-config", required=True, type=Path, help="Path to an agent YAML config file.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args(argv)

    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        create_fabric_serving_app(args.agent_config),
        host=args.host,
        port=args.port,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
