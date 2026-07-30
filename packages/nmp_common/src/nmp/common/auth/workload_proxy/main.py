# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Service-principal auth-proxy sidecar.

Runs inside a deployed workload's pod as a loopback forwarder. A co-located
workload whose HTTP client we do not control (e.g. a NAT agent calling the
Inference Gateway) points its platform base URL at this proxy
(``http://127.0.0.1:<port>``) and sends no credentials of its own. The proxy
stamps a service-principal identity header (``X-NMP-Principal-Id: service:<name>``)
on every forwarded request, which the platform authorizes via the ServiceSystem
role. This is the same static service-identity the platform's own SDK clients
use (``get_platform_sdk(as_service=...)``); the proxy exists only for workloads
that cannot set the header themselves.

When ``NMP_AUTH_PROXY_ON_BEHALF_OF`` is set, the proxy additionally stamps
``X-NMP-Principal-On-Behalf-Of`` so the platform authorizes the request as that
delegated principal rather than granting the service principal's full
(ServiceSystem) reach. This scopes a deployed workload's platform access to the
identity that created it (e.g. an agent deployment acting as its creator). The
delegated identity is baked in at deploy time and is *not* taken from the
incoming request — the inbound principal/OBO headers are stripped so a co-located
workload cannot spoof a different identity.

Started via ``nemo services run --sidecars auth-proxy``.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# Loopback host + port the proxy listens on. The workload targets this address.
AUTH_PROXY_HOST_ENVVAR = "NMP_AUTH_PROXY_HOST"
AUTH_PROXY_PORT_ENVVAR = "NMP_AUTH_PROXY_PORT"
# Service-principal name stamped on forwarded requests (e.g. "agents").
AUTH_PROXY_PRINCIPAL_ENVVAR = "NMP_AUTH_PROXY_PRINCIPAL"
# Optional principal id to delegate to via on-behalf-of (e.g. the workload's
# creator). When set, the service principal acts on behalf of this identity so
# the platform scopes access to what that principal can reach.
AUTH_PROXY_ON_BEHALF_OF_ENVVAR = "NMP_AUTH_PROXY_ON_BEHALF_OF"
DEFAULT_AUTH_PROXY_HOST = "127.0.0.1"
DEFAULT_AUTH_PROXY_PORT = 8090

_READ_TIMEOUT_ENVVAR = "NMP_AUTH_PROXY_READ_TIMEOUT"
_PRINCIPAL_ID_HEADER = "x-nmp-principal-id"
_ON_BEHALF_OF_HEADER = "x-nmp-principal-on-behalf-of"

# Minimal request-header sanitization. We only drop what would be actively wrong:
# - the workload's own credential / principal / on-behalf-of headers (we set the
#   identity), so they can't be spoofed or conflict with what we stamp;
# - host and content-length, which httpx recomputes for the upstream request
#   (a stale value corrupts routing / the body).
_STRIP_REQUEST_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "authorization",
        _PRINCIPAL_ID_HEADER,
        _ON_BEHALF_OF_HEADER,
    }
)
# We stream the response, so the upstream's framing headers no longer apply.
_STRIP_RESPONSE_HEADERS = frozenset(
    {
        "content-length",
        "transfer-encoding",
    }
)


def _upstream_base_url() -> str:
    """Return the platform base URL to forward to (env override or platform config)."""
    from nemo_platform_plugin.config import get_platform_config

    return (os.environ.get("NEMO_BASE_URL") or os.environ.get("NMP_BASE_URL") or get_platform_config().base_url).rstrip(
        "/"
    )


def build_app(*, base_url: str, principal: str, on_behalf_of: str | None = None) -> FastAPI:
    """Build the forwarding FastAPI app for the given upstream and service principal.

    When *on_behalf_of* is provided, every forwarded request also carries
    ``X-NMP-Principal-On-Behalf-Of``, delegating to that principal so the
    platform scopes access to what it can reach rather than the service
    principal's full ServiceSystem reach.
    """
    principal_id = principal if principal.startswith("service:") else f"service:{principal}"
    read_timeout = float(os.environ.get(_READ_TIMEOUT_ENVVAR, "300"))
    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=60.0, pool=10.0)
    client = httpx.AsyncClient(base_url=base_url, timeout=timeout, follow_redirects=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(title="nmp-auth-proxy", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def forward(request: Request, path: str) -> StreamingResponse:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _STRIP_REQUEST_HEADERS}
        headers[_PRINCIPAL_ID_HEADER] = principal_id
        if on_behalf_of:
            headers[_ON_BEHALF_OF_HEADER] = on_behalf_of
        url = httpx.URL(path="/" + path, query=request.url.query.encode("utf-8"))
        body = await request.body()
        upstream = client.build_request(request.method, url, headers=headers, content=body)
        response = await client.send(upstream, stream=True)

        async def _body() -> AsyncIterator[bytes]:
            # The finally runs on normal completion, exception, and client
            # disconnect (Starlette closes the generator), so this is the only
            # cleanup the response needs.
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()

        resp_headers = {k: v for k, v in response.headers.items() if k.lower() not in _STRIP_RESPONSE_HEADERS}
        return StreamingResponse(
            _body(),
            status_code=response.status_code,
            headers=resp_headers,
        )

    return app


def run(parent_stop_signal: threading.Event | None = None) -> None:
    """Sidecar entrypoint. Serves the loopback auth-proxy until stopped."""
    base_url = _upstream_base_url()
    principal = os.environ.get(AUTH_PROXY_PRINCIPAL_ENVVAR)
    if not principal:
        raise RuntimeError(f"{AUTH_PROXY_PRINCIPAL_ENVVAR} is required for the auth-proxy sidecar")
    on_behalf_of = os.environ.get(AUTH_PROXY_ON_BEHALF_OF_ENVVAR) or None
    host = os.environ.get(AUTH_PROXY_HOST_ENVVAR, DEFAULT_AUTH_PROXY_HOST)
    port = int(os.environ.get(AUTH_PROXY_PORT_ENVVAR, str(DEFAULT_AUTH_PROXY_PORT)))
    app = build_app(base_url=base_url, principal=principal, on_behalf_of=on_behalf_of)

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)

    logger.info(
        "Starting auth-proxy sidecar on %s:%s -> %s (principal=service:%s, on_behalf_of=%s)",
        host,
        port,
        base_url,
        principal,
        on_behalf_of or "<none>",
    )
    if parent_stop_signal is None:
        server.run()
        return

    thread = threading.Thread(target=server.run, name="auth-proxy-uvicorn", daemon=True)
    thread.start()
    try:
        while not parent_stop_signal.is_set():
            parent_stop_signal.wait(timeout=1)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        logger.info("auth-proxy sidecar stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    run()
