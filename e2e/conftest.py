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
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

import httpx
import pytest
from nemo_platform import NeMoPlatform
from nmp.testing import NemoRun, get_repo_root


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
_AUTH_READY_TIMEOUT = 60
_E2E_ADMIN_EMAIL = "admin@example.com"
_SERVICES_LOG = Path(os.environ.get("E2E_SERVICES_LOG", os.path.join(tempfile.gettempdir(), "services.log")))

# Number of log lines to dump from the services log on test failure.
_TAIL_LINES_ON_FAILURE = 100

_services_log_key = pytest.StashKey[Path]()

NGC_API_KEY_ENV = "NGC_API_KEY"


@pytest.fixture
def ngc_api_key() -> str:
    """Return the NGC API key from the environment."""
    key = os.environ.get(NGC_API_KEY_ENV)
    assert key, f"{NGC_API_KEY_ENV} must be set"
    return key


@pytest.fixture
def ngc_secret(sdk: NeMoPlatform, workspace: str, ngc_api_key: str) -> Iterator[str]:
    """Create a secret containing the NGC API key, cleaned up after test."""
    secret_name = f"e2e-ngc-key-{uuid.uuid4().hex[:8]}"
    sdk.secrets.create(workspace=workspace, name=secret_name, value=ngc_api_key)
    yield secret_name
    try:
        sdk.secrets.delete(workspace=workspace, name=secret_name)
    except Exception:
        pass  # Best-effort cleanup; the workspace is deleted anyway


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


_E2E_REPO_ROOT = Path(__file__).resolve().parents[1]
_E2E_PLATFORM_CONFIG = _E2E_REPO_ROOT / "packages/nmp_platform/config/local.yaml"


def _e2e_services_env() -> dict[str, str]:
    """Environment for the ``nemo services run`` child process.

    ``pytest_configure`` sets ``NMP_INFERENCE_GATEWAY_MOCK_PROVIDER_PREFIX`` on the
    pytest process so ``add_mock_provider()`` can build providers, but the IGW
    must see the same value in *its* process or mock routing and cache refresh
    behave differently from the test client.  Mirror the Docker E2E backend
    (``nmp.testing.e2e.docker``) by setting inference env vars explicitly here
    rather than relying on inherited shell state.

    Use ``packages/nmp_platform/config/local.yaml`` (``inference_gateway: {}``)
    so IGW polls the Models service on the background refresh interval instead
    of the dev-only ``debug_model_providers`` block in
    ``services/core/inference-gateway/config/local.yaml``, which disables that
    loop.
    """
    env = os.environ.copy()
    env["NMP_SEED_ON_STARTUP"] = "true"
    env["NMP_INFERENCE_GATEWAY_MOCK_PROVIDER_PREFIX"] = "igw-mock-"
    env["NMP_CONFIG_FILE_PATH"] = str(_E2E_PLATFORM_CONFIG)
    env["NMP_CONFIG_WARNINGS_DISABLED"] = "1"
    if not _e2e_auth_enabled():
        env["NMP_AUTH_ENABLED"] = "false"
    elif "NMP_AUTH_ENABLED" not in env:
        env["NMP_AUTH_ENABLED"] = "true"
    return env


def _e2e_auth_enabled() -> bool:
    """Return whether the e2e harness should run with authorization enabled.

    Default is disabled so ``make test-e2e`` does not depend on platform-admin
    seeding, PDP refresh, or role propagation timing. Opt in with
    ``E2E_AUTH_ENABLED=true`` (see ``make test-e2e-docker-auth``).
    """
    return os.environ.get("E2E_AUTH_ENABLED", "false").lower() in ("1", "true", "yes")


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


def _admin_headers() -> dict[str, str]:
    return {
        "X-NMP-Principal-Id": _E2E_ADMIN_EMAIL,
        "X-NMP-Principal-Email": _E2E_ADMIN_EMAIL,
    }


def _wait_for_auth_ready(url: str, timeout: float = _AUTH_READY_TIMEOUT) -> bool:
    """Poll until platform admin can create entities in a fresh workspace.

    Workspace create/list alone is insufficient: entity CRUD requires
    PlatformAdmin (or entities.create, which workspace Admin lacks). The first
    entity e2e test was flaky when only workspace visibility was probed.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe_name = f"auth-probe-{uuid.uuid4().hex[:8]}"
        entity_name = f"auth-probe-entity-{uuid.uuid4().hex[:8]}"
        try:
            create_resp = httpx.post(
                f"{url}/apis/entities/v2/workspaces",
                json={"name": probe_name},
                headers=_admin_headers(),
                timeout=5.0,
            )
            if create_resp.status_code != 201:
                time.sleep(_HEALTH_POLL_INTERVAL)
                continue

            entity_resp = httpx.post(
                f"{url}/apis/entities/v2/workspaces/{probe_name}/entities/e2e-auth-probe",
                json={"name": entity_name, "data": {"ready": True}},
                headers=_admin_headers(),
                timeout=5.0,
            )
            if entity_resp.status_code != 201:
                httpx.delete(
                    f"{url}/apis/entities/v2/workspaces/{probe_name}",
                    headers=_admin_headers(),
                    timeout=5.0,
                )
                time.sleep(_HEALTH_POLL_INTERVAL)
                continue

            httpx.delete(
                f"{url}/apis/entities/v2/workspaces/{probe_name}/entities/e2e-auth-probe/{entity_name}",
                headers=_admin_headers(),
                timeout=5.0,
            )
            httpx.delete(
                f"{url}/apis/entities/v2/workspaces/{probe_name}",
                headers=_admin_headers(),
                timeout=5.0,
            )
            return True
        except httpx.RequestError as exc:
            logger.debug("Auth readiness probe failed; will retry: %s", exc)
        time.sleep(_HEALTH_POLL_INTERVAL)
    return False


@contextlib.contextmanager
def background_process(
    args: list[str],
    stdout: IO[Any] | None = None,
    env: dict[str, str] | None = None,
) -> Iterator[subprocess.Popen]:
    """Run a subprocess, yield the ``Popen``, and terminate on exit.

    Unlike ``Popen``'s built-in context manager (which only waits for the
    process), this sends SIGTERM/SIGKILL so long-running servers are
    cleaned up.
    """
    proc = subprocess.Popen(args, stdout=stdout, stderr=subprocess.STDOUT, env=env)
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
    args = [
        nemo_bin,
        "services",
        "run",
        "--service-group",
        "all",
        "--controller-group",
        "all",
        "--port",
        str(port),
    ]
    env = _e2e_services_env()

    logger.info("Starting nemo services on port %d", port)

    log_path = services_log_path or _SERVICES_LOG
    with open(log_path, "w") as log_file, background_process(args, stdout=log_file, env=env) as proc:
        if not _wait_for_healthy(url):
            pytest.fail(
                f"nemo services run did not become healthy within {_HEALTH_TIMEOUT}s.\nlog:\n{log_path.read_text()}"
            )
        if _e2e_auth_enabled() and not _wait_for_auth_ready(url):
            pytest.fail(
                f"Platform auth seed did not become ready within {_AUTH_READY_TIMEOUT}s.\nlog:\n{log_path.read_text()}"
            )

        logger.info("Platform services ready on port %d (pid %d)", port, proc.pid)
        yield url
        logger.info("Terminating nemo services (pid %d)", proc.pid)


@pytest.fixture(scope="session")
def sdk(_services: str) -> NeMoPlatform:
    """Provide an SDK client connected to the running platform.

    When connecting to an external cluster (via ``NMP_BASE_URL``), authentication
    can be provided through:
    - ``NMP_ACCESS_TOKEN`` env var (e.g. from ``nemo auth token``)
    - ``NMP_CONTEXT_NAME`` env var (e.g. ``tot``) to read credentials from CLI config

    For local auth-enabled deployments (``E2E_AUTH_ENABLED=true``), admin headers
    are injected via ``default_headers``.
    """
    access_token = os.environ.get("NMP_ACCESS_TOKEN")
    context_name = os.environ.get("NMP_CONTEXT_NAME")
    headers = _admin_headers() if _e2e_auth_enabled() else {}
    return NeMoPlatform(
        base_url=_services,
        access_token=access_token,
        context_name=context_name,
        max_retries=2,
        default_headers=headers,
    )


@pytest.fixture(scope="function")
def workspace(sdk: NeMoPlatform) -> Iterator[str]:
    """Create a unique workspace for each test, deleted on teardown."""
    name = f"e2e-{uuid.uuid4().hex[:8]}"
    sdk.workspaces.create(name=name)
    yield name
    sdk.workspaces.delete(name)


@pytest.fixture(scope="session")
def nemo_run(_services: str) -> NemoRun:
    """Run the NeMo CLI from the repo root with the E2E base URL and workspace env when set."""
    base_url = _services.rstrip("/")
    repo_root = get_repo_root()

    def run(
        *args: str,
        workspace: str | None = None,
        env_extra: dict[str, str] | None = None,
        timeout: int | None = 60,
        capture_output: bool = True,
        stdin: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["NMP_BASE_URL"] = base_url
        if workspace is not None:
            env["NMP_WORKSPACE"] = workspace
        if env_extra:
            env.update(env_extra)
        cmd = ["uv", "run", "--project", str(repo_root), "--frozen", "nemo", "-f", "json", *args]
        return subprocess.run(
            cmd,
            cwd=repo_root,
            env=env,
            timeout=timeout,
            capture_output=capture_output,
            stdin=stdin,
            text=True,
        )

    return run
