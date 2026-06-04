# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent gateway proxy routes.

Two proxy routes:

``/v2/workspaces/{workspace}/agents/{name}/-/{trailing_uri}``
    Proxy by **agent name** — gateway resolves the active deployment and
    forwards the request.  This is the primary user-facing path, analogous to
    how IGW routes by model name.

``/v2/workspaces/{workspace}/deployments/{name}/-/{trailing_uri}``
    Proxy by **deployment name** — for direct targeting of a specific
    deployment (e.g. A/B testing).

The ``/-/`` separator prevents URL conflicts with the CRUD routes
(``/agents/{name}`` and ``/deployments/{name}``).  This mirrors the pattern
used by the Inference Gateway.

Streaming and SSE are supported: the response is streamed back to the client
chunk by chunk.  ``text/event-stream`` responses bypass buffering.
"""

from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.entities import Agent, AgentDeployment
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()

# HTTP methods to forward through the proxy
_PROXY_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

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


@router.api_route(
    "/agents/{name}/-/{trailing_uri:path}",
    methods=_PROXY_METHODS,
    tags=["Agent Gateway"],
    include_in_schema=False,
)
async def proxy_by_agent_name(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> StreamingResponse:
    """Proxy a request to the active deployment for *agent name*.

    The gateway finds the first ``running`` deployment for the named agent
    and forwards the request to it.  Returns ``503`` if no running deployment
    is found.
    """
    endpoint = await _resolve_agent_endpoint(name, workspace, entity_client)
    return await _proxy(request, endpoint, trailing_uri, model_name=name)


@router.api_route(
    "/deployments/{name}/-/{trailing_uri:path}",
    methods=_PROXY_METHODS,
    tags=["Agent Gateway"],
    include_in_schema=False,
)
async def proxy_by_deployment_name(
    workspace: str,
    name: str,
    trailing_uri: str,
    request: Request,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> StreamingResponse:
    """Proxy a request directly to the named deployment.

    Returns ``404`` if the deployment doesn't exist, ``503`` if it isn't
    currently running.
    """
    try:
        dep = await entity_client.get(AgentDeployment, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Deployment '{name}' not found in workspace '{workspace}'."
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if dep.status != "running" or not dep.endpoint:
        raise HTTPException(
            status_code=503,
            detail=f"Deployment '{name}' is not running (status='{dep.status}').",
        )

    return await _proxy(request, dep.endpoint, trailing_uri, model_name=name)


async def _resolve_agent_endpoint(name: str, workspace: str, entity_client: NemoEntitiesClient) -> str:
    """Find the endpoint of the first running deployment for the given agent."""
    try:
        await entity_client.get(Agent, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found in workspace '{workspace}'.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        result = await entity_client.list(AgentDeployment, workspace=workspace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    running = [d for d in result.data if d.agent == name and d.status == "running" and d.endpoint]
    if not running:
        raise HTTPException(
            status_code=503,
            detail=f"No running deployment found for agent '{name}' in workspace '{workspace}'.",
        )
    return running[0].endpoint


async def _proxy(
    request: Request, endpoint: str, trailing_uri: str, *, model_name: str | None = None
) -> StreamingResponse:
    """Forward *request* to ``{endpoint}/{trailing_uri}`` and stream the response.

    Error handling policy:
    - **4xx** from the agent: transparent pass-through (client error, agent's response).
    - **5xx** from the agent: translated to **502 Bad Gateway** (upstream fault).
    - **Connection failure** (httpx.RequestError): 502 Bad Gateway.

    All responses are streamed, including SSE (``text/event-stream``).
    ``content-length`` is stripped from forwarded headers because chunked
    transfer encoding makes the original value invalid.
    """
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

    # We need the upstream response headers before we can construct StreamingResponse
    # (to forward content-type, etc.).  Use a two-phase approach:
    # 1. Open the stream and capture headers — this triggers the HTTP round-trip.
    # 2. Prime the generator with one __anext__() call so headers are populated.
    # 3. Wrap in _buffered() to re-yield the primed chunk before continuing the stream.
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
                # Translate agent 5xx responses into 502 Bad Gateway.
                # aread() consumes the full body before raising so the connection
                # is cleanly closed rather than reset mid-stream.
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

    # NAT's ChatResponse.from_string() defaults model to "unknown-model" when
    # the agent wrapper doesn't supply one (the wrapper code lives in
    # nvidia-nat-core and doesn't have access to the platform entity name).
    # For non-streaming JSON responses, patch the model field to the
    # agent/deployment name the client addressed.  This is a gateway-level
    # workaround; the proper upstream fix belongs in nvidia-nat-core's
    # NemoAgentWrapperFunction.convert_to_chat_response where the LLM's
    # response_metadata carries the real model name.
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
