# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for the AIPerf shim.

We stand up the shim on a real local port and a stub upstream HTTP server, then
exercise the three routes AIPerf and the harness rely on.
"""

from __future__ import annotations

import json
import socket
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Generator

import httpx
import pytest
from nemo_guardrails_plugin.benchmarks import shim as shim_module


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _UpstreamHandler(BaseHTTPRequestHandler):
    received_body: bytes = b""

    def log_message(self, *args: object, **kwargs: object) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or "0")
        type(self).received_body = self.rfile.read(length) if length else b""
        body = json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def upstream_server() -> Generator[str, None, None]:
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/chat"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def shim_server(upstream_server: str) -> Generator[str, None, None]:
    port = _free_port()
    # Override the class attr so the shim proxies to our stub upstream.
    previous = shim_module._ShimHandler.upstream_url
    shim_module._ShimHandler.upstream_url = upstream_server
    server = ThreadingHTTPServer(("127.0.0.1", port), shim_module._ShimHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        shim_module._ShimHandler.upstream_url = previous
        server.shutdown()
        server.server_close()


def test_models_returns_200_with_openai_shape(shim_server: str) -> None:
    response = httpx.get(f"{shim_server}/v1/models", timeout=2.0)
    assert response.status_code == 200
    body = response.json()
    assert body == {"object": "list", "data": []}


def test_health_endpoint_returns_200(shim_server: str) -> None:
    response = httpx.get(f"{shim_server}/__shim/health", timeout=2.0)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_completions_proxies_to_upstream(shim_server: str) -> None:
    payload = {"model": "x", "messages": [{"role": "user", "content": "hi"}]}
    response = httpx.post(
        f"{shim_server}/v1/chat/completions",
        json=payload,
        timeout=5.0,
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "hi"
    # Body should be forwarded byte-for-byte (ignoring possible whitespace).
    assert json.loads(_UpstreamHandler.received_body) == payload


def test_unknown_path_returns_404(shim_server: str) -> None:
    response = httpx.get(f"{shim_server}/something/else", timeout=2.0)
    assert response.status_code == 404
