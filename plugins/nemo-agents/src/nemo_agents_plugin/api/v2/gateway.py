# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent gateway proxy routes.

Proxy by **agent name** (``/agents/{name}/-/{trailing_uri}``) resolves the active
deployment; proxy by **deployment name** (``/deployments/{name}/-/...``) targets one
directly. The ``/-/`` separator avoids conflicts with the CRUD routes. Responses are
streamed chunk by chunk; ``text/event-stream`` bypasses buffering.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncIterator
from urllib.parse import urljoin, urlparse, urlunparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from nemo_agents_plugin.a2a import A2AMessageError, send_a2a_message, stream_a2a_message
from nemo_agents_plugin.api.v2._perms import GatewayPerms
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.authz import scope
from nemo_agents_plugin.entities import (
    Agent,
    AgentDeployment,
    is_container_deployment_mode,
    is_external_agent,
)
from nemo_platform_plugin.authz import CallerKind, path_rule
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()

# Forwarded methods split by scope: read-like need agents:read, mutating need agents:write.
# Both still require the agents.gateway.invoke permission.
_PROXY_READ_METHODS = ["GET", "HEAD", "OPTIONS"]
_PROXY_WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE"]

# Headers we strip before forwarding to the agent process (hop-by-hop + platform-internal)
_HOP_BY_HOP = {
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    # platform-internal headers should not leak to the agent process
    "x-nmp-principal-id",
    "x-nmp-principal-on-behalf-of",
}


# These two helpers are the only place the gateway learns where an agent lives:
# subprocess deployments use the loopback ``endpoint``; container modes (docker/k8s)
# use the routable address the agents controller projects onto ``endpoints``.
def _get_deployment_endpoint(dep: AgentDeployment) -> str | None:
    """Return the address to proxy to for *dep*, or ``None`` if none is available yet."""
    if is_container_deployment_mode(dep.deployment_mode):
        for ep in dep.endpoints:
            if ep.protocol in ("http", "https") and ep.url:
                return ep.url
        return None
    return dep.endpoint or None


def _is_deployment_routable(dep: AgentDeployment) -> bool:
    """Return ``True`` if *dep* is ``running`` and has a resolvable endpoint."""
    return dep.status == "running" and _get_deployment_endpoint(dep) is not None


async def _serve_agent_proxy(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient,
) -> StreamingResponse | JSONResponse:
    """Forward a request addressed by agent name to the agent behind it.

    Managed agents proxy to their first ``running`` deployment (``503`` if none).
    External agents have no deployment; their chat/completions and NAT ``generate``
    traffic is bridged to A2A instead. Shared by the read/write route handlers,
    which differ only in authorization scope.
    """
    try:
        agent = await entity_client.get(Agent, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found in workspace '{workspace}'.") from exc
    except Exception as exc:
        logger.exception("Failed to look up agent '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to look up agent.") from exc

    if is_external_agent(agent):
        return await _serve_external_agent(name, trailing_uri, request, agent)

    endpoint = await _resolve_agent_endpoint(name, workspace, entity_client)
    return await _proxy(request, endpoint, trailing_uri, model_name=name)


@router.api_route(
    "/agents/{name}/-/{trailing_uri:path}",
    methods=_PROXY_READ_METHODS,
    tags=["Agent Gateway"],
    include_in_schema=False,
    response_model=None,
)
@scope.read
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[GatewayPerms.INVOKE],
)
async def proxy_by_agent_name_read(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> StreamingResponse | JSONResponse:
    """Read-scoped (GET/HEAD/OPTIONS) proxy to the active deployment for *agent name*."""
    return await _serve_agent_proxy(workspace, name, trailing_uri, request, entity_client)


@router.api_route(
    "/agents/{name}/-/{trailing_uri:path}",
    methods=_PROXY_WRITE_METHODS,
    tags=["Agent Gateway"],
    include_in_schema=False,
    response_model=None,
)
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[GatewayPerms.INVOKE],
)
async def proxy_by_agent_name_write(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> StreamingResponse | JSONResponse:
    """Write-scoped (POST/PUT/PATCH/DELETE) proxy to the active deployment for *agent name*."""
    return await _serve_agent_proxy(workspace, name, trailing_uri, request, entity_client)


async def _serve_deployment_proxy(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient,
) -> StreamingResponse:
    """Proxy a request directly to the named deployment.

    Returns ``404`` if the deployment doesn't exist, ``503`` if it isn't currently running.
    Shared by the read/write route handlers, which differ only in authorization scope.
    """
    try:
        dep = await entity_client.get(AgentDeployment, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Deployment '{name}' not found in workspace '{workspace}'."
        ) from exc
    except Exception as exc:
        logger.exception("Failed to look up deployment '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to look up deployment.") from exc

    if not _is_deployment_routable(dep):
        raise HTTPException(
            status_code=503,
            detail=f"Deployment '{name}' is not routable (mode='{dep.deployment_mode}', status='{dep.status}').",
        )

    endpoint = _get_deployment_endpoint(dep)
    # _is_deployment_routable guarantees a non-None endpoint, but narrow for the type checker.
    if endpoint is None:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=503,
            detail=f"Deployment '{name}' has no routable endpoint (status='{dep.status}').",
        )

    return await _proxy(request, endpoint, trailing_uri, model_name=name)


@router.api_route(
    "/deployments/{name}/-/{trailing_uri:path}",
    methods=_PROXY_READ_METHODS,
    tags=["Agent Gateway"],
    include_in_schema=False,
)
@scope.read
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[GatewayPerms.INVOKE],
)
async def proxy_by_deployment_name_read(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> StreamingResponse:
    """Read-scoped (GET/HEAD/OPTIONS) proxy directly to the named deployment."""
    return await _serve_deployment_proxy(workspace, name, trailing_uri, request, entity_client)


@router.api_route(
    "/deployments/{name}/-/{trailing_uri:path}",
    methods=_PROXY_WRITE_METHODS,
    tags=["Agent Gateway"],
    include_in_schema=False,
)
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[GatewayPerms.INVOKE],
)
async def proxy_by_deployment_name_write(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> StreamingResponse:
    """Write-scoped (POST/PUT/PATCH/DELETE) proxy directly to the named deployment."""
    return await _serve_deployment_proxy(workspace, name, trailing_uri, request, entity_client)


async def _resolve_agent_endpoint(name: str, workspace: str, entity_client: NemoEntitiesClient) -> str:
    """Find the endpoint of the first running deployment for the given agent.

    The agent's existence is already validated by the caller (``_serve_agent_proxy``),
    so this only lists deployments — no second entity fetch.
    """
    try:
        result = await entity_client.list(AgentDeployment, workspace=workspace)
    except Exception as exc:
        logger.exception("Failed to list deployments for agent '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to list deployments.") from exc

    running = [d for d in result.data if d.agent == name and _is_deployment_routable(d)]
    if not running:
        raise HTTPException(
            status_code=503,
            detail=f"No running deployment found for agent '{name}' in workspace '{workspace}'.",
        )
    # first-match, no load-balancing across running deployments (out of scope).
    endpoint = _get_deployment_endpoint(running[0])
    # _is_deployment_routable guarantees a non-None endpoint, but narrow for the type checker.
    if endpoint is None:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=503,
            detail=f"No routable endpoint for agent '{name}' in workspace '{workspace}'.",
        )
    return endpoint


async def _proxy(
    request: Request, endpoint: str, trailing_uri: str, *, model_name: str | None = None
) -> StreamingResponse:
    """Forward *request* to ``{endpoint}/{trailing_uri}`` and stream the response.

    Agent 5xx and connection failures become 502; 4xx pass through. SSE is
    supported; ``content-length`` is stripped since chunked encoding invalidates it.
    """
    # SSRF guard: reject any trailing_uri that escapes the resolved endpoint's origin.
    endpoint_parsed = urlparse(endpoint)
    if not endpoint_parsed.scheme or not endpoint_parsed.netloc:
        raise HTTPException(status_code=500, detail="Deployment endpoint is misconfigured.")
    joined = urlparse(urljoin(endpoint.rstrip("/") + "/", trailing_uri))
    if joined.scheme != endpoint_parsed.scheme or joined.netloc != endpoint_parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid proxy target URI.")
    target_url = urlunparse(
        (endpoint_parsed.scheme, endpoint_parsed.netloc, joined.path, joined.params, joined.query, "")
    )
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    # Build forwarded headers — strip hop-by-hop and platform-internal headers
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}

    body = await request.body()

    # Headers are needed before constructing StreamingResponse, so prime one chunk
    # up front and _buffered() re-yields it before continuing the stream.
    response_headers: dict[str, str] = {}
    status_code_holder: list[int] = [200]

    async def _stream_with_headers() -> AsyncIterator[bytes]:
        read_timeout = float(os.environ.get("NEMO_AGENTS_GATEWAY_READ_TIMEOUT", "300"))
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=read_timeout, write=60.0, pool=10.0),
            # SSRF defense in depth: never let an agent's 3xx response redirect
            # us off the validated origin.
            follow_redirects=False,
        ) as client:
            async with client.stream(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            ) as response:
                status_code_holder[0] = response.status_code
                for k, v in response.headers.items():
                    if k.lower() not in _HOP_BY_HOP:
                        response_headers[k] = v
                # Agent 5xx → 502; aread() drains the body so the connection closes cleanly.
                if response.status_code >= 500:
                    error_body = await response.aread()
                    raise HTTPException(
                        status_code=502,
                        detail=(f"Agent returned {response.status_code}: {error_body.decode(errors='replace')[:500]}"),
                    )
                async for chunk in response.aiter_bytes():
                    yield chunk

    stream_gen = _stream_with_headers()
    chunks: list[bytes] = []

    async def _buffered() -> AsyncIterator[bytes]:
        for c in chunks:
            yield c
        async for c in stream_gen:
            yield c

    # Prime: triggers the HTTP request, populates response_headers / status_code_holder,
    # and catches the most common failure modes before we commit to a StreamingResponse.
    try:
        first_chunk = await stream_gen.__anext__()
        chunks.append(first_chunk)
    except StopAsyncIteration:
        pass  # empty body — still valid (e.g. 204)
    except HTTPException:
        raise  # 5xx → 502 translation raised inside the generator; propagate as-is
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not connect to agent: {exc}") from exc

    content_type = response_headers.get("content-type", "application/json")

    # NAT defaults model to "unknown-model" when the wrapper can't see the platform
    # entity name; patch non-streaming JSON responses to the addressed agent/deployment.
    if model_name and not content_type.startswith("text/event-stream"):
        async for remaining in stream_gen:
            chunks.append(remaining)
        raw = b"".join(chunks)
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("model") == "unknown-model":
                data["model"] = model_name
                raw = json.dumps(data).encode()
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        chunks = [raw]

    return StreamingResponse(
        _buffered(),
        status_code=status_code_holder[0],
        headers={k: v for k, v in response_headers.items() if k.lower() != "content-length"},
        media_type=content_type,
    )


# External agents speak A2A JSON-RPC, not OpenAI chat. These helpers bridge an
# OpenAI chat/completions request to ``message/send`` and back to OpenAI shape.
def _message_text(message: Any) -> str:
    """Extract text from one OpenAI message (``content`` may be str or parts)."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part["text"] for part in content if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def _conversation_prompt(messages: Any) -> str:
    """Build a single A2A message that carries the conversation so far.

    NAT's A2A executor is message-only, so prior turns are folded into a transcript
    ahead of the latest user message. A single turn is sent verbatim.
    """
    if not isinstance(messages, list):
        return ""
    turns = [
        (m.get("role"), _message_text(m))
        for m in messages
        if isinstance(m, dict) and m.get("role") in ("system", "user", "assistant")
    ]
    turns = [(role, text) for role, text in turns if text]
    # Anchor on the last user turn; everything before it becomes the transcript.
    last_user = next((i for i in range(len(turns) - 1, -1, -1) if turns[i][0] == "user"), None)
    if last_user is None:
        return ""
    latest = turns[last_user][1]
    prior = turns[:last_user]
    if not prior:
        return latest

    labels = {"system": "System", "user": "User", "assistant": "Assistant"}
    transcript = "\n".join(f"{labels.get(str(role), 'User')}: {text}" for role, text in prior)
    return f"Continue this conversation.\n\n{transcript}\n\nUser: {latest}"


def _openai_completion(text: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
    }


def _openai_chunk(completion_id: str, created: int, model: str, delta: dict[str, Any], finish: str | None) -> bytes:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def _card_supports_streaming(agent: Agent) -> bool:
    """False only when the card explicitly disables streaming; default True."""
    caps = (agent.card or {}).get("capabilities")
    return not (isinstance(caps, dict) and caps.get("streaming") is False)


async def _single_chunk_sse(text: str, model: str) -> AsyncIterator[bytes]:
    """Wrap a complete (non-streamed) reply as one OpenAI SSE completion."""
    created = int(time.time())
    completion_id = f"chatcmpl-{uuid4().hex}"
    yield _openai_chunk(completion_id, created, model, {"role": "assistant", "content": text}, None)
    yield _openai_chunk(completion_id, created, model, {}, "stop")
    yield b"data: [DONE]\n\n"


async def _stream_openai_from_a2a(
    agen: AsyncIterator[str],
    first: str,
    has_first: bool,
    model: str,
    name: str,
    endpoint: str,
) -> AsyncIterator[bytes]:
    """Stream a *primed* A2A reply as OpenAI chat.completion.chunk SSE.

    Status is already 200, so a mid-stream failure ends the stream without a
    normal ``stop`` finish to mark it abnormal.
    """
    created = int(time.time())
    completion_id = f"chatcmpl-{uuid4().hex}"
    role_sent = False
    if has_first:
        yield _openai_chunk(completion_id, created, model, {"role": "assistant", "content": first}, None)
        role_sent = True
    try:
        async for delta in agen:
            payload = {"content": delta} if role_sent else {"role": "assistant", "content": delta}
            role_sent = True
            yield _openai_chunk(completion_id, created, model, payload, None)
    except A2AMessageError as exc:
        logger.warning(
            "External agent '%s' chat stream failed mid-stream (%s): %s", name, _endpoint_host(endpoint), exc
        )
        note = f"[external agent error: {exc}]"
        payload = {"content": f"\n{note}"} if role_sent else {"role": "assistant", "content": note}
        yield _openai_chunk(completion_id, created, model, payload, None)
        yield b"data: [DONE]\n\n"  # no ``stop`` finish — signals abnormal termination
        return
    if not role_sent:
        yield _openai_chunk(completion_id, created, model, {"role": "assistant", "content": ""}, None)
    yield _openai_chunk(completion_id, created, model, {}, "stop")
    yield b"data: [DONE]\n\n"


@router.post(
    "/agents/{name}/chat/completions",
    tags=["Agent Gateway"],
    include_in_schema=False,
    response_model=None,
)
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[GatewayPerms.INVOKE],
)
async def external_agent_chat_completions(
    workspace: str,
    name: str,
    request: Request,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> StreamingResponse | JSONResponse:
    """Bridge an OpenAI chat/completions call to an external agent's A2A endpoint."""
    try:
        agent = await entity_client.get(Agent, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found in workspace '{workspace}'.") from exc
    except Exception as exc:
        logger.exception("Failed to look up agent '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to look up agent.") from exc

    if not is_external_agent(agent):
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{name}' is managed; chat through its deployment, not this endpoint.",
        )

    endpoint = _external_a2a_endpoint(agent, name)
    body = await _read_json_object(request)
    return await _external_openai_chat(name, endpoint, body, _card_supports_streaming(agent))


# External agents have no deployment, so agent-name proxy requests land in
# _serve_external_agent, which bridges OpenAI chat/completions and NAT generate to A2A.
def _endpoint_host(url: str) -> str:
    """Host of *url* for logging — never the full URL (may carry embedded creds)."""
    try:
        return urlparse(url).hostname or "unknown"
    except ValueError:
        return "unknown"


def _external_a2a_endpoint(agent: Agent, name: str) -> str:
    """Return the vetted URL to reach an external agent.

    Always the registered ``endpoint`` — never the card's self-reported ``url``,
    which is remote-controlled content and would let a registered agent redirect
    all subsequent traffic to an arbitrary (e.g. internal) host.
    """
    if not agent.endpoint:
        raise HTTPException(status_code=400, detail=f"External agent '{name}' has no endpoint.")
    return agent.endpoint


async def _read_json_object(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


async def _external_openai_chat(
    name: str, endpoint: str, body: dict[str, Any], supports_streaming: bool
) -> StreamingResponse | JSONResponse:
    """Translate an OpenAI chat/completions body to A2A and return OpenAI shape."""
    text = _conversation_prompt(body.get("messages"))
    if not text:
        raise HTTPException(status_code=400, detail="Request has no user message to send.")

    model = body.get("model") or name
    wants_stream = bool(body.get("stream"))

    if wants_stream and supports_streaming:
        # Prime the first delta before returning so an early failure is a 502, not a 200.
        agen = stream_a2a_message(endpoint, text)
        try:
            first, has_first = await anext(agen), True
        except StopAsyncIteration:
            first, has_first = "", False
        except A2AMessageError as exc:
            logger.warning("External agent '%s' chat stream failed (%s): %s", name, _endpoint_host(endpoint), exc)
            raise HTTPException(status_code=502, detail=f"External agent chat failed: {exc}") from exc
        return StreamingResponse(
            _stream_openai_from_a2a(agen, first, has_first, model, name, endpoint),
            media_type="text/event-stream",
        )

    # Non-streaming (or streaming-disabled card): one message/send, returned as JSON or one SSE chunk.
    try:
        reply = await send_a2a_message(endpoint, text)
    except A2AMessageError as exc:
        logger.warning("External agent '%s' chat failed (%s): %s", name, _endpoint_host(endpoint), exc)
        raise HTTPException(status_code=502, detail=f"External agent chat failed: {exc}") from exc
    if wants_stream:
        return StreamingResponse(_single_chunk_sse(reply, model), media_type="text/event-stream")
    return JSONResponse(_openai_completion(reply, model))


async def _generate_full_stream(text: str) -> AsyncIterator[bytes]:
    # nat eval joins the ``value`` fields of every ``data:`` line; one line is enough.
    yield f"data: {json.dumps({'value': text})}\n\n".encode()


async def _serve_external_generate_full(name: str, endpoint: str, request: Request) -> StreamingResponse:
    body = await _read_json_object(request)
    question = body.get("input_message")
    if not isinstance(question, str) or not question:
        raise HTTPException(status_code=400, detail="Request has no 'input_message' to send.")
    try:
        reply = await send_a2a_message(endpoint, question)
    except A2AMessageError as exc:
        logger.warning("External agent '%s' generate failed (%s): %s", name, _endpoint_host(endpoint), exc)
        raise HTTPException(status_code=502, detail=f"External agent generate failed: {exc}") from exc
    return StreamingResponse(_generate_full_stream(reply), media_type="text/event-stream")


async def _serve_external_agent(
    name: str, trailing_uri: str, request: Request, agent: Agent
) -> StreamingResponse | JSONResponse:
    """Bridge an agent-name proxy request for an external agent to A2A.

    ``chat/completions`` (Studio / CLI invoke / SDK) → OpenAI↔A2A translation;
    ``generate`` (nat eval) → NAT-generate↔A2A translation. Anything else 400s —
    external agents have no deployment to proxy arbitrary paths to.
    """
    endpoint = _external_a2a_endpoint(agent, name)
    if trailing_uri.endswith("chat/completions"):
        body = await _read_json_object(request)
        return await _external_openai_chat(name, endpoint, body, _card_supports_streaming(agent))
    if trailing_uri.startswith("generate"):
        return await _serve_external_generate_full(name, endpoint, request)
    raise HTTPException(
        status_code=400,
        detail=(
            f"External agent '{name}' supports chat/completions and generate only; "
            f"'{trailing_uri}' is not available (the agent runs outside NeMo Platform)."
        ),
    )
