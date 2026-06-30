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
child process on a free port, polls ``/status`` until ready, and
terminates the process after the session.

Config selection::

    # Default local platform config
    pytestmark = [pytest.mark.e2e_config()]

    # Single repo-root-relative config file
    pytestmark = [pytest.mark.e2e_config("e2e/configs/local-subprocess.yaml")]

    # Ordered config layers: files first, then inline overlays
    pytestmark = [
        pytest.mark.e2e_config(
            "e2e/configs/local-subprocess.yaml",
            {"auth": {"enabled": True}},
        )
    ]

Why this exists:

- E2E modules should be able to declare the platform shape they need rather
  than inheriting one global config from ``conftest.py``.
- Different modules can exercise different backends or auth modes in the same
  pytest session.
- Identical effective configs are pooled and reused, so config selection does
  not imply one fresh ``nemo services`` process per module.

How pooling works:

- The harness resolves the ordered ``e2e_config(...)`` layers into one
  effective config dict.
- That config is normalized into a canonical form and hashed.
- Modules that resolve to the same hash share one running services instance for
  the session.
- The pooled instance is shut down as soon as the last module using that hash
  finishes, so mixed-config runs do not keep every started platform alive until
  the end of the session.

The pool implementation itself lives in ``e2e.services_pool`` so this file can
stay focused on pytest hooks and fixtures.
"""

import logging
import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from nemo_platform import NeMoPlatform

from e2e.services_pool import E2EServicesPool, RunningServices, admin_headers

_services_pool_manager_key = pytest.StashKey[E2EServicesPool]()
_services_metadata_key = pytest.StashKey[dict[str, str]]()


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
    config.stash[_services_pool_manager_key] = E2EServicesPool()


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list[pytest.Item]) -> None:
    """Register collected E2E modules with the services pool manager."""
    config.stash[_services_pool_manager_key].register_collected_items(items)


logger = logging.getLogger(__name__)
_E2E_HARNESS_DEBUG = os.environ.get("E2E_HARNESS_DEBUG") == "1"

_SERVICES_LOG = Path(os.environ.get("E2E_SERVICES_LOG", os.path.join(tempfile.gettempdir(), "services.log")))

# Number of log lines to dump from the services log on test failure.
_TAIL_LINES_ON_FAILURE = 100

_services_log_key = pytest.StashKey[Path]()
_active_services_log_key = pytest.StashKey[Path]()
_active_services_metadata_key = pytest.StashKey[dict[str, str]]()

NGC_API_KEY_ENV = "NGC_API_KEY"


@pytest.fixture
def ngc_api_key() -> str:
    """Return the NGC API key from the environment.

    Skips the test when the key is missing or set to a CI placeholder
    value (e.g. ``not-used-for-ghcr-cpu-*``).
    """
    key = os.environ.get(NGC_API_KEY_ENV, "")
    if not key or key.startswith("not-used"):
        pytest.skip(f"{NGC_API_KEY_ENV} not set or is a placeholder")
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

    log_path = item.stash.get(_active_services_log_key, None) or item.session.stash.get(_services_log_key, None)
    if log_path and log_path.exists():
        lines = log_path.read_text().splitlines(keepends=True)
        tail = lines[-_TAIL_LINES_ON_FAILURE:]
        if tail:
            header = f"--- services log (last {len(tail)} lines) [{log_path}] ---"
            report.sections.append(("Services Log", f"{header}\n{''.join(tail)}"))
    metadata = item.stash.get(_active_services_metadata_key, None)
    if metadata:
        report.sections.append(
            (
                "E2E Services Binding",
                "\n".join(f"{key}: {value}" for key, value in sorted(metadata.items())),
            )
        )


# ---- Fixtures --------------------------------------------------------------
@pytest.fixture(scope="session")
def _services_pool_manager(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[E2EServicesPool]:
    manager = request.config.stash[_services_pool_manager_key]
    manager.bind_tmp_path_factory(tmp_path_factory)
    yield manager
    manager.shutdown_all()


@pytest.fixture(scope="module")
def _services_instance(
    request: pytest.FixtureRequest,
    _services_pool_manager: E2EServicesPool,
) -> Iterator[RunningServices]:
    """Return the running services instance for the current module's config.

    Skipped when ``NMP_BASE_URL`` is already set (external services).

    Modules do not each get a dedicated services process. Instead, the harness
    computes the effective config hash for the module and reuses any existing
    process already started for that hash within the pytest session. A new
    process is started only when the module resolves to a config that no prior
    module has used.
    """
    module = request.node.getparent(pytest.Module)
    if module is None:
        raise RuntimeError("Expected module-scoped E2E fixture to have a pytest module parent")
    services = _services_pool_manager.acquire_for_module(module)
    if services.log_path is not None:
        request.session.stash[_services_log_key] = services.log_path
    try:
        yield services
    finally:
        _services_pool_manager.release_for_module(module)


@pytest.fixture(autouse=True)
def _bind_services_log_to_test(request: pytest.FixtureRequest, _services_instance: RunningServices) -> None:
    if _services_instance.log_path is not None:
        request.node.stash[_active_services_log_key] = _services_instance.log_path
    module = request.node.getparent(pytest.Module)
    if module is None:
        return
    manager = request.config.stash[_services_pool_manager_key]
    metadata = {
        key: str(value)
        for key, value in manager.describe_module_binding(module.nodeid, _services_instance).items()
        if value is not None
    }
    request.node.stash[_active_services_metadata_key] = metadata
    if _E2E_HARNESS_DEBUG:
        logger.info(
            "E2E test binding",
            extra={
                **metadata,
                "test": request.node.nodeid,
            },
        )


@pytest.fixture(scope="module")
def _services(_services_instance: RunningServices) -> Iterator[str]:
    yield _services_instance.url


@pytest.fixture(scope="module")
def sdk(_services: str, _services_instance: RunningServices) -> NeMoPlatform:
    """Provide an SDK client connected to the running platform.

    When connecting to an external cluster (via ``NMP_BASE_URL``), authentication
    can be provided through:
    - ``NMP_ACCESS_TOKEN`` env var (e.g. from ``nemo auth token``)
    - ``NMP_CONTEXT_NAME`` env var (e.g. ``tot``) to read credentials from CLI config

    For local auth-enabled deployments, admin headers are injected via
    ``default_headers`` based on the rendered platform config.
    """
    access_token = os.environ.get("NMP_ACCESS_TOKEN")
    context_name = os.environ.get("NMP_CONTEXT_NAME")
    headers = admin_headers() if _services_instance.auth_enabled else {}
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
