"""E2E test fixtures that run against a real ``nemo services`` process.

Usage::

    # Start services, run e2e tests, stop services
    make test-e2e

    # Or manually
    uv run --frozen pytest e2e -v --run-e2e

    # If you already have services running
    NMP_BASE_URL=http://localhost:9090 uv run --frozen pytest e2e -v --run-e2e

When ``NMP_BASE_URL`` is set the harness skips service startup/shutdown and
connects to the given URL.  Otherwise it spawns ``nemo services run`` as a
child process on a free port, polls ``/health/ready`` until ready, and
terminates the process after the session.
"""

import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from nemo_platform import NeMoPlatform

logger = logging.getLogger(__name__)

_HEALTH_TIMEOUT = 60
_HEALTH_POLL_INTERVAL = 1.0


def _find_free_port() -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_healthy(url: str, timeout: float = _HEALTH_TIMEOUT) -> bool:
    """Poll /health/ready until it returns 200 or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/health/ready", timeout=2.0)
            if resp.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(_HEALTH_POLL_INTERVAL)
    return False


@pytest.fixture(scope="session")
def _services() -> Iterator[str]:
    """Spawn ``nemo services run`` and yield the base URL.

    Skipped when ``NMP_BASE_URL`` is already set (external services).
    The process is our direct child — on teardown we just terminate it.
    """
    external_url = os.environ.get("NMP_BASE_URL")
    if external_url:
        yield external_url
        return

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    nemo_bin = str(Path(sys.executable).parent / "nemo")
    args = [
        nemo_bin,
        "services",
        "run",
        "--service-group",
        "all",
        "--port",
        str(port),
    ]

    logger.info("Starting nemo services on port %d", port)

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if not _wait_for_healthy(url):
        # Grab whatever output we have for diagnostics
        proc.terminate()
        stdout, _ = proc.communicate(timeout=10)
        pytest.fail(f"nemo services run did not become healthy within {_HEALTH_TIMEOUT}s.\nstdout:\n{stdout}")

    logger.info("Platform services ready on port %d (pid %d)", port, proc.pid)

    yield url

    logger.info("Terminating nemo services (pid %d)", proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        logger.warning("Process did not exit after SIGTERM, sending SIGKILL")
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def sdk(_services: str) -> NeMoPlatform:
    """Provide an SDK client connected to the running platform."""
    return NeMoPlatform(base_url=_services, max_retries=2)


@pytest.fixture(scope="function")
def workspace(sdk: NeMoPlatform) -> Iterator[str]:
    """Create a unique workspace for each test, deleted on teardown."""
    name = f"e2e-{uuid.uuid4().hex[:8]}"
    sdk.workspaces.create(name=name)
    yield name
    sdk.workspaces.delete(name)
