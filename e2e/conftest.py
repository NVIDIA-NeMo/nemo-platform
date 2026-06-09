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

import contextlib
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

import httpx
import pytest
from nemo_platform import NeMoPlatform


def pytest_configure(config: pytest.Config) -> None:
    """Enable mock inference provider for e2e tests.

    Sets the env var and clears the Configuration cache so that
    InferenceGatewayConfig picks up the new value. The cache must be
    cleared because the config module evaluates ``get_service_config()``
    at import time, which may run before this hook.
    """
    os.environ.setdefault("NMP_INFERENCE_GATEWAY_MOCK_PROVIDER_PREFIX", "igw-mock-")

    from nemo_platform_plugin.config import Configuration

    Configuration.clear_cache()


logger = logging.getLogger(__name__)

_HEALTH_TIMEOUT = 60
_HEALTH_POLL_INTERVAL = 1.0

# Number of log lines to dump from the services log on test failure.
_TAIL_LINES_ON_FAILURE = 100

_services_log_key = pytest.StashKey[Path]()


@pytest.fixture(scope="session")
def services_log_path(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a unique services log path for this session.

    ``E2E_SERVICES_LOG_DIR`` (if set) is treated as a **directory**; in CI
    the job uploads everything under it as artifacts.  When unset we
    fall back to a pytest-managed temp directory.  Either way, each
    session writes to a UUID-named file inside the directory so
    parallel workers never clobber each other.

    The path is stashed on the session so the
    ``pytest_runtest_makereport`` hook can read it without requesting
    the fixture.
    """
    log_dir = os.environ.get("E2E_SERVICES_LOG_DIR")
    if log_dir:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
    else:
        directory = tmp_path_factory.mktemp("e2e-services-logs")
    path = directory / f"services-{uuid.uuid4().hex[:8]}.log"
    request.session.stash[_services_log_key] = path
    return path


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
            pass  # Server not up yet, keep polling
        time.sleep(_HEALTH_POLL_INTERVAL)
    return False


@contextlib.contextmanager
def background_process(args: list[str], stdout: IO[Any] | None = None) -> Iterator[subprocess.Popen]:
    """Run a subprocess, yield the ``Popen``, and terminate on exit.

    Unlike ``Popen``'s built-in context manager (which only waits for the
    process), this sends SIGTERM/SIGKILL so long-running servers are
    cleaned up.
    """
    proc = subprocess.Popen(args, stdout=stdout, stderr=subprocess.STDOUT)
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Process %d did not exit after SIGTERM, sending SIGKILL", proc.pid)
            proc.kill()
            proc.wait(timeout=5)


# ---- Services log tail on failure ------------------------------------------


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):  # noqa: ARG001
    """Append the services log tail to the report when a test fails.

    This hook is the pytest-sanctioned way to add extra sections to test
    reports (``report.sections``).  Fixtures cannot do this because they
    don't have access to the report object.
    """
    outcome = yield
    report = outcome.get_result()

    if not report.failed:
        return

    log_path = item.session.stash.get(_services_log_key, None)
    if log_path and log_path.exists():
        lines = log_path.read_text().splitlines(keepends=True)
        tail = lines[-_TAIL_LINES_ON_FAILURE:]
        if tail:
            header = f"--- services log (last {len(tail)} lines) [{log_path}] ---"
            report.sections.append(("Services Log", f"{header}\n{''.join(tail)}"))


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture(scope="session")
def _services(services_log_path: Path) -> Iterator[str]:
    """Spawn ``nemo services run`` and yield the base URL.

    Skipped when ``NMP_BASE_URL`` is already set (external services).

    This is the "subprocess" backend.  When we add Docker and Kubernetes
    backends, this fixture should be replaced by a backend-selection layer
    (e.g. ``--docker`` / ``--kubernetes`` CLI flags) that dispatches to the
    appropriate setup while yielding the same base URL interface.  Tests
    should remain agnostic to the backend.
    """
    external_url = os.environ.get("NMP_BASE_URL")
    if external_url:
        yield external_url
        return

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    nemo_bin = str(Path(sys.executable).parent / "nemo")
    args = [nemo_bin, "services", "run", "--port", str(port)]

    logger.info("Starting nemo services on port %d", port)

    log_path = services_log_path
    with open(log_path, "w") as log_file, background_process(args, stdout=log_file) as proc:
        if not _wait_for_healthy(url):
            pytest.fail(
                f"nemo services run did not become healthy within {_HEALTH_TIMEOUT}s.\nlog:\n{log_path.read_text()}"
            )

        logger.info("Platform services ready on port %d (pid %d)", port, proc.pid)
        yield url
        logger.info("Terminating nemo services (pid %d)", proc.pid)


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
