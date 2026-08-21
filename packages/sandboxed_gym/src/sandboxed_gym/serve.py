# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Serve entrypoints: orchestrator proxy and host-urls modes."""

from __future__ import annotations

import json
import logging
import signal
import threading
from pathlib import Path
from typing import Literal

import uvicorn

from sandboxed_gym.orchestrator import SandboxedGymOrchestrator, SandboxedGymSession
from sandboxed_gym.proxy_app import build_proxy_app
from sandboxed_gym.serve_config import SandboxedGymServeConfig


LOGGER = logging.getLogger(__name__)


def write_session_file(path: Path, session: SandboxedGymSession, *, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    desc = session.descriptor(mode=mode, orchestrator_url=session.orchestrator_url)
    path.write_text(desc.model_dump_json(indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Wrote session descriptor to %s", path)


def _wait_forever() -> None:
    event = threading.Event()

    def _stop(signum: int, _frame: object) -> None:
        LOGGER.info("Received signal %s; shutting down", signum)
        event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    event.wait()


def serve(
    cfg: SandboxedGymServeConfig,
    *,
    mode: Literal["orchestrator", "host-urls"] | None = None,
    bind: str = "0.0.0.0:8090",
    session_file: Path | None = None,
) -> None:
    """Start broker + Gym host, then either proxy or print host URLs."""
    mode = mode or cfg.serve_mode
    orch = SandboxedGymOrchestrator()
    session = orch.start(cfg)

    try:
        if mode == "orchestrator":
            host, _, port_s = bind.partition(":")
            if not port_s:
                raise ValueError(f"bind must be host:port, got {bind!r}")
            port = int(port_s)
            public_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
            session.orchestrator_url = f"http://{public_host}:{port}"
            if session_file is not None:
                write_session_file(session_file, session, mode=mode)
            print(
                session.descriptor(mode=mode).model_dump_json(indent=2),
                flush=True,
            )
            app = build_proxy_app(session)
            LOGGER.info("Orchestrator proxy listening on %s", bind)
            uvicorn.run(app, host=host, port=port, log_level="info")
        elif mode == "host-urls":
            if session_file is not None:
                write_session_file(session_file, session, mode=mode)
            print(
                session.descriptor(mode=mode).model_dump_json(indent=2),
                flush=True,
            )
            LOGGER.info("Host URLs published; waiting for SIGTERM/SIGINT")
            _wait_forever()
        else:
            raise ValueError(f"unknown mode: {mode!r}")
    finally:
        session.shutdown()
