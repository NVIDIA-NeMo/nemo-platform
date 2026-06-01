"""E2E test fixtures that run against a real ``nemo services`` process.

Usage::

    # Start services, run e2e tests, stop services
    make test-e2e

    # Or manually
    uv run --frozen pytest e2e -v --run-e2e

    # If you already have services running
    NMP_BASE_URL=http://localhost:9090 uv run --frozen pytest e2e -v --run-e2e

When ``NMP_BASE_URL`` is set the harness skips service startup/shutdown and
connects to the given URL.  Otherwise it starts ``nemo services start`` on a
free port, waits for ``/health/ready``, and tears the instance down after the
session.
"""

import logging
import os
import socket
import subprocess
import uuid
from collections.abc import Iterator

import pytest
from nemo_platform import NeMoPlatform

logger = logging.getLogger(__name__)


def _find_free_port() -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def _services() -> Iterator[str]:
    """Start ``nemo services`` and yield the base URL.

    Skipped when ``NMP_BASE_URL`` is already set (external services).
    """
    external_url = os.environ.get("NMP_BASE_URL")
    if external_url:
        yield external_url
        return

    port = _find_free_port()
    instance = f"e2e-test-{port}"
    url = f"http://127.0.0.1:{port}"

    logger.info("Starting nemo services on port %d (instance=%s)", port, instance)

    result = subprocess.run(
        [
            "nemo",
            "services",
            "start",
            "--service-group",
            "all",
            "--port",
            str(port),
            "--instance",
            instance,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        pytest.fail(
            f"nemo services start failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    logger.info("Platform services started: %s", result.stdout.strip())

    # Set NMP_BASE_URL so the SDK picks it up automatically
    os.environ["NMP_BASE_URL"] = url

    yield url

    logger.info("Stopping nemo services (instance=%s)", instance)
    stop_result = subprocess.run(
        [
            "nemo",
            "services",
            "stop",
            "--instance",
            instance,
            "--port",
            str(port),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if stop_result.returncode != 0:
        logger.warning(
            "nemo services stop failed (exit %d): %s",
            stop_result.returncode,
            stop_result.stderr,
        )


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
