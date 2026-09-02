# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""In-process episode broker HTTP server (Ray-free)."""

from __future__ import annotations

import asyncio
import logging
import secrets
import socket
import threading
import time
from typing import Any
from urllib.parse import urlparse

from sandboxed_gym.backends.registry import build_backend
from sandboxed_gym.config import BrokerEndpoint, EpisodeBrokerConfig
from sandboxed_gym.http_app import begin_shutdown, build_broker_app, close_all_episodes
from sandboxed_gym.netutil import (
    DEFAULT_BROKER_PORT_RANGE_HIGH,
    DEFAULT_BROKER_PORT_RANGE_LOW,
    bind_socket_in_range,
    get_node_ip,
)

LOGGER = logging.getLogger(__name__)

STARTUP_TIMEOUT_S = 30.0
SHUTDOWN_DRAIN_TIMEOUT_S = 60.0
SHUTDOWN_JOIN_TIMEOUT_S = 30.0


class EpisodeBrokerServer:
    """Trusted, job-scoped provisioner of episode sandboxes (no Ray).

    Holds the episode backend credential in this process so the job sandbox never
    has one. HTTP runs on a background thread with its own asyncio loop.
    """

    def __init__(self, config: EpisodeBrokerConfig | dict[str, Any]) -> None:
        self._config = config if isinstance(config, EpisodeBrokerConfig) else EpisodeBrokerConfig.model_validate(config)
        self._endpoint: BrokerEndpoint | None = None
        self._app = None
        self._server = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None

    def _reserve_socket(self) -> tuple[socket.socket, int]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self._config.port is not None:
            sock.bind(("", self._config.port))
            port = self._config.port
        else:
            port = bind_socket_in_range(
                sock,
                self._config.port_range_low or DEFAULT_BROKER_PORT_RANGE_LOW,
                self._config.port_range_high or DEFAULT_BROKER_PORT_RANGE_HIGH,
            )
        sock.listen(128)
        sock.setblocking(False)
        return sock, port

    def _resolve_advertise(self, bind_port: int) -> tuple[str, str, int]:
        """Return ``(url, host, port)`` published to the Gym host.

        Prefer ``advertise_url`` (cluster Service DNS), then ``host``, then node IP.
        """
        if self._config.advertise_url:
            parsed = urlparse(self._config.advertise_url)
            if not parsed.hostname:
                raise ValueError(f"advertise_url must include a hostname: {self._config.advertise_url!r}")
            port = parsed.port or bind_port
            host = parsed.hostname
            url = self._config.advertise_url.rstrip("/")
            if parsed.port is None:
                url = f"{parsed.scheme}://{host}:{port}{parsed.path.rstrip('/')}"
            return url, host, port

        host = self._config.host or get_node_ip()
        return f"http://{host}:{bind_port}", host, bind_port

    def start(self) -> BrokerEndpoint:
        if self._endpoint is not None:
            raise RuntimeError("Episode broker is already started")

        import uvicorn

        backend = build_backend(self._config)
        token = secrets.token_urlsafe(32)
        self._socket, bind_port = self._reserve_socket()
        url, host, port = self._resolve_advertise(bind_port)

        self._app = build_broker_app(backend=backend, config=self._config, token=token)
        server = uvicorn.Server(config=uvicorn.Config(self._app, host="0.0.0.0", port=bind_port, access_log=False))
        self._server = server

        reserved_socket = self._socket
        self._socket = None

        def _serve() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                loop.run_until_complete(server.serve(sockets=[reserved_socket]))
            finally:
                loop.close()

        self._thread = threading.Thread(target=_serve, name="sandboxed-gym-episode-broker", daemon=True)
        self._thread.start()

        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while not self._server.started:
            if not self._thread.is_alive():
                raise RuntimeError("Episode broker HTTP server exited during startup")
            if time.monotonic() > deadline:
                raise RuntimeError(f"Episode broker HTTP server did not start within {STARTUP_TIMEOUT_S:g}s")
            time.sleep(0.05)

        self._endpoint = BrokerEndpoint(url=url, host=host, port=port, token=token)
        LOGGER.info(
            "Episode broker for job %s listening on bind=:%s advertise=%s backend=%s",
            self._config.job_id,
            bind_port,
            url,
            self._config.backend,
        )
        return self._endpoint

    def get_endpoint(self) -> BrokerEndpoint:
        if self._endpoint is None:
            raise RuntimeError("Episode broker has not been started")
        return self._endpoint

    def shutdown(self) -> None:
        if self._app is not None:
            begin_shutdown(self._app)

        if self._loop is not None and self._app is not None:
            future = asyncio.run_coroutine_threadsafe(close_all_episodes(self._app), self._loop)
            try:
                future.result(timeout=SHUTDOWN_DRAIN_TIMEOUT_S)
            except Exception:
                LOGGER.exception("Episode broker failed to drain episodes during shutdown")

        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=SHUTDOWN_JOIN_TIMEOUT_S)
            if self._thread.is_alive():
                LOGGER.warning("Episode broker HTTP thread did not stop within the shutdown timeout")

        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._endpoint = None
