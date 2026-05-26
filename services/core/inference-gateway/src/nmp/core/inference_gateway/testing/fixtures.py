# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures for the IGW middleware test harnesses.

Importing :func:`igw_plugin_harness` (or :func:`igw_loopback_harness`)
into a test module — or re-exporting from a project ``conftest.py`` —
registers the fixture for the surrounding scope. Both piggyback on
``pytest_httpserver``'s function-scoped ``httpserver`` fixture so each
test gets an isolated socket and clean handler state.

Scope split (AIRCORE-585):

* :func:`_igw_app_context` — **module-scoped**. Wraps the expensive
  ``create_test_client`` call (SQLite DB, FastAPI app + IGW + Models
  services, dependency wiring, ``/health/ready`` polling, workspace +
  project seeding) once per test file. The ``InferenceGatewayService``
  config disables the periodic ``refresh_model_cache_task`` so it
  cannot wake mid-test and re-populate the model cache with stale
  rows from the previous test.
* :func:`_igw_loopback_context` — **module-scoped**. Adds a uvicorn
  thread + ``per_request_http_client`` dependency override + platform
  base URL patch on top of the module app. Only entered when a test
  asks for the loopback variant so plain modules don't pay the
  uvicorn startup cost.
* :func:`igw_plugin_harness` / :func:`igw_loopback_harness` —
  **function-scoped**. Build a fresh :class:`IGWPluginHarness` per
  test on top of the module context: pre/post global-cache resets,
  per-test ``app.state.pending_post_response_tasks`` re-init,
  per-test ``MockChatCompletionsHandler`` mounted on the function-
  scoped ``pytest_httpserver`` socket, and entity teardown via the
  harness's track-and-delete cleanup.

xdist note: module scope is preserved under ``--dist=loadfile`` and
``--dist=loadscope``; the default ``--dist=load`` distributes individual
tests across workers and would defeat the optimization (each worker
would still rebuild the ASGI stack from scratch). See the testing
README for the required pytest command line.
"""

from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from typing import cast

import pytest
from fastapi import FastAPI
from nmp.core.inference_gateway.testing.harness import IGWLoopbackHarness, IGWPluginHarness
from nmp.testing.client import ClientContext, ServiceFactory, create_test_client
from pytest_httpserver import HTTPServer


def _app_from(client_context: ClientContext) -> FastAPI:
    """Narrow ``client_context.test_client.app`` from ``ASGIApp`` to :class:`FastAPI`.

    :class:`TestClient` types ``app`` as a bare ``ASGIApp`` callable;
    every caller in this module needs to reach ``app.state`` or
    ``app.dependency_overrides``, so the cast is unavoidable. Centralised
    here so the assumption is documented once and the per-site noise is
    a single function call.
    """
    return cast(FastAPI, client_context.test_client.app)


def _enable_post_response_task_tracking(client_context: ClientContext) -> None:
    """Initialise ``app.state.pending_post_response_tasks`` so ``proxy.py`` records them.

    ``proxy.py`` checks for this attribute on every request that schedules a
    fire-and-forget post-response task; production never sets it, so the
    list-or-None guard keeps the production hot path free of test-only
    state. Only the test harness initialises it here, and only the harness's
    :meth:`IGWPluginHarness.aflush_post_response` reads it.

    Re-initialising the list (rather than letting it accumulate across tests
    in a module-scoped app) is the function-scoped fixture's job — a stale
    list would pin completed tasks in memory and ``aflush_post_response``
    would re-await them on the next test.
    """
    _app_from(client_context).state.pending_post_response_tasks = []


@contextmanager
def _build_app_context(
    *extra_services: ServiceFactory,
) -> Generator[ClientContext, None, None]:
    """Yield an IGW + Models + extras :class:`ClientContext`.

    ``igw_mock_provider_mode=False`` keeps the proxy step routing to the
    mock NIM (test harness goes through real HTTP), matching production
    behavior for non-mock providers.

    The periodic ``refresh_model_cache_task`` is disabled for the
    lifetime of the module: ``InferenceGatewayService.on_startup`` reads
    ``refresh_model_cache_interval_sec`` from the **module-level
    snapshot** ``nmp.core.inference_gateway.config.config`` (captured at
    first import via :func:`get_service_config`), so a
    ``service_configs`` override to ``create_test_client`` alone has no
    effect — the snapshot was taken before any override could be set.
    We patch the snapshot's field directly via
    :func:`unittest.mock.patch.object` so :func:`on_startup` sees 0 and
    never schedules the background coroutine. Without this, the 3-second
    loop runs in the background for the whole module, lists providers
    cross-workspace between tests, and may fire plugin
    ``notify_destroyed`` / ``notify_upserted`` callbacks on a torn-down
    test's resources during the gap between tests.

    The shared SDK HTTP client (``async_http_client`` in
    :func:`create_test_client`) has its ``aclose`` monkey-patched to a
    no-op for the lifetime of the module. The
    ``nemo-guardrails`` plugin's ``on_shutdown`` calls
    ``await sdk.close()`` which would otherwise close that shared
    client, breaking every subsequent test in the same module.
    ``ASGITransport`` uses in-process connections, so skipping
    ``aclose`` has no real-resource leak — the actual close runs at
    module teardown when the patch is restored and the plugin's
    on_shutdown fires for the last time.
    """
    from unittest.mock import patch

    from nmp.common import sdk_factory as sdk_factory_module
    from nmp.core.inference_gateway import config as igw_config_module
    from nmp.core.inference_gateway.service import InferenceGatewayService
    from nmp.core.models.service import ModelsService

    service_types: list[ServiceFactory] = [InferenceGatewayService, ModelsService, *extra_services]

    # Patch the module-level config snapshot *before* create_test_client
    # enters — on_startup runs inside that with-block and reads the
    # snapshot's ``refresh_model_cache_interval_sec`` exactly once.
    with patch.object(igw_config_module.config, "refresh_model_cache_interval_sec", 0):
        with create_test_client(
            *service_types,
            client_type=ClientContext,
            igw_mock_provider_mode=False,
        ) as client_context:
            shared_async_client = sdk_factory_module._test_http_client
            if shared_async_client is not None:
                original_aclose = shared_async_client.aclose

                async def _noop_aclose() -> None:
                    return None

                shared_async_client.aclose = _noop_aclose  # type: ignore[method-assign]
                try:
                    yield client_context
                finally:
                    shared_async_client.aclose = original_aclose  # type: ignore[method-assign]
            else:
                yield client_context


@pytest.fixture(scope="module")
def _igw_extra_services() -> tuple[ServiceFactory, ...]:
    """Extra services to mount on the module-scoped IGW + Models app.

    Override at the plugin's ``conftest.py`` to include services whose
    routes the plugin's integration tests need (e.g.
    ``GuardrailsService`` for entity-backed guardrail configs)::

        @pytest.fixture(scope="module")
        def _igw_extra_services() -> tuple[ServiceFactory, ...]:
            from nmp.guardrails.service import GuardrailsService

            return (GuardrailsService,)

    Module-scoped because the app context is module-scoped — the
    service list cannot change mid-module.
    """
    return ()


@pytest.fixture(scope="module")
def _igw_app_context(
    _igw_extra_services: tuple[ServiceFactory, ...],
) -> Generator[ClientContext, None, None]:
    """Module-scoped IGW + Models ASGI stack.

    Single source of the expensive ``create_test_client`` call per test
    file. Function-scoped fixtures consume this context and add only
    per-test concerns (cache resets, mock NIM handler, entity teardown).

    Auth (``auth_enabled=False``) and mock-provider mode
    (``igw_mock_provider_mode=False``) are hard-coded at module scope —
    a test needing different settings should use a sibling fixture
    rather than parametrising this one. Extra service classes flow in
    through :func:`_igw_extra_services` so plugin conftests can declare
    their needs without rebuilding the app per-test.
    """
    with _build_app_context(*_igw_extra_services) as client_context:
        yield client_context


@pytest.fixture(scope="module")
def _igw_loopback_context(
    _igw_app_context: ClientContext,
) -> Generator[str, None, None]:
    """Module-scoped uvicorn loopback wrapper around :func:`_igw_app_context`.

    Yields the loopback base URL (``http://127.0.0.1:<port>``). Only
    enters when a test in the module actually requests
    :func:`igw_loopback_harness`, so plain modules never pay the
    uvicorn startup cost.

    Does **not** install the ``per_request_http_client`` dependency
    override or the ``get_platform_config`` patch — those are scoped
    per-test inside :func:`igw_loopback_harness` so mixed modules
    (plain + loopback tests) don't impose loopback's per-request
    session overhead on plain tests in the same module.

    ``TestClient`` lifespan and uvicorn coexist at module scope: the
    TestClient owns the app's startup/shutdown (uvicorn is configured
    with ``lifespan="off"``), so the lifecycle ordering matches the
    previous per-test build (startup before uvicorn comes up, uvicorn
    down before lifespan teardown).
    """
    from nmp.core.inference_gateway.testing._loopback import serve_app_in_thread

    with serve_app_in_thread(_app_from(_igw_app_context)) as loopback_base_url:
        yield loopback_base_url


@contextmanager
def _per_test_plugin_setup(
    client_context: ClientContext,
    httpserver: HTTPServer,
) -> Generator[IGWPluginHarness, None, None]:
    """Per-test setup/teardown shared by plain + loopback function fixtures.

    The module-scoped app lifespan is **not** torn down between tests, so
    this fixture deliberately avoids the original per-test
    ``reset_global_*`` calls — nulling the globals would crash the next
    request (``InferenceGatewayService.on_startup`` only runs once per
    app and is the only thing that re-initialises them). The harness's
    :meth:`IGWPluginHarness._cleanup` does the actual per-test work:
    delete this test's entities from the store, then rebuild the
    in-memory caches without disturbing the cache objects themselves.

    Order matters:

    1. Re-initialise ``app.state.pending_post_response_tasks`` so
       ``proxy.py`` appends to a fresh list rather than the previous
       test's accumulated tasks. The list accumulates per-request in
       production, and the previous test may have left finished tasks
       on it.
    2. Build the harness and yield. The harness mounts a fresh
       :class:`MockChatCompletionsHandler` on the per-test
       ``pytest_httpserver`` socket (the socket itself is fresh because
       ``httpserver`` is function-scoped).
    3. On teardown, run ``harness._cleanup`` (track-and-delete entities,
       rebuild caches). Plugin registrations from
       :meth:`use_plugin` / :meth:`load_plugin` self-clean via their
       context-manager ``finally`` blocks; the per-test list only
       tracks what we explicitly created.
    """
    _enable_post_response_task_tracking(client_context)
    harness = IGWPluginHarness._build(client_context=client_context, mock_nim=httpserver)
    try:
        yield harness
    finally:
        harness._cleanup()


@pytest.fixture
def igw_plugin_harness(
    _igw_app_context: ClientContext,
    httpserver: HTTPServer,
) -> Generator[IGWPluginHarness, None, None]:
    """Function-scoped IGW + Models harness; no real port for IGW.

    Cheap to enter: the heavy ASGI stack comes from the module-scoped
    :func:`_igw_app_context`; this fixture only pays for the per-test
    global-cache reset, post-response-task list re-init, harness
    construction, and the function-scoped ``pytest_httpserver`` socket.
    """
    with _per_test_plugin_setup(_igw_app_context, httpserver) as harness:
        yield harness


@contextmanager
def _build_loopback_harness(
    client_context: ClientContext,
    httpserver: HTTPServer,
    igw_loopback_base_url: str,
    *extra_services: ServiceFactory,
) -> Generator[IGWLoopbackHarness, None, None]:
    """Per-test setup/teardown for the loopback harness.

    Performs the same pre-test work as :func:`_per_test_plugin_setup`
    (re-initialising ``app.state.pending_post_response_tasks``), and on
    top of that installs the two loopback-only patches scoped to this
    test:

    * ``per_request_http_client`` as the :func:`global_http_client`
      dependency override — loop-bound :class:`aiohttp.ClientSession`
      instances don't survive the two-loop split between
      :class:`TestClient` and uvicorn, so a singleton would fail with
      "attached to a different loop" on whichever loop didn't
      originate it.
    * ``get_platform_config`` patched at IGW's middleware-registry
      import site so the plugin resolver
      (:meth:`get_openai_compatible_inference_url_and_model`) returns
      URLs reachable from the test process.

    Both teardowns run before the next test's setup, so a plain
    ``igw_plugin_harness`` test running after a loopback test in the
    same module doesn't observe either patch — module-scoped uvicorn
    keeps running (idle) but its loop sees no traffic from plain
    tests.

    Raises:
        TypeError: If *extra_services* is non-empty. Mounting extra
            services per-call is incompatible with the module-scoped
            app context (built before this function runs); a
            :class:`DeprecationWarning` would be too quiet because
            pytest swallows it by default and a developer copying the
            previous ``igw_loopback_harness(GuardrailsService)``
            pattern would see their routes silently missing. Override
            the ``_igw_extra_services`` module fixture in the plugin's
            ``conftest.py`` to mount additional services for the whole
            module.
    """
    if extra_services:
        names = ", ".join(getattr(s, "__name__", repr(s)) for s in extra_services)
        raise TypeError(
            f"igw_loopback_harness({names}) — extra service args are no longer "
            "accepted under module-scoped fixtures. Override the "
            "`_igw_extra_services` module fixture in your conftest to mount "
            "additional services for the whole module."
        )
    from nmp.core.inference_gateway.api.dependencies import global_http_client
    from nmp.core.inference_gateway.testing._loopback import (
        override_platform_base_url,
        per_request_http_client,
    )

    _enable_post_response_task_tracking(client_context)

    app = _app_from(client_context)

    with ExitStack() as stack:
        previous_override = app.dependency_overrides.get(global_http_client)
        app.dependency_overrides[global_http_client] = per_request_http_client

        def _restore_http_client_override() -> None:
            if previous_override is None:
                app.dependency_overrides.pop(global_http_client, None)
            else:
                app.dependency_overrides[global_http_client] = previous_override

        stack.callback(_restore_http_client_override)
        stack.enter_context(override_platform_base_url(igw_loopback_base_url))

        harness = cast(
            IGWLoopbackHarness,
            IGWLoopbackHarness._build(
                client_context=client_context,
                mock_nim=httpserver,
                igw_loopback_base_url=igw_loopback_base_url,
            ),
        )
        try:
            yield harness
        finally:
            harness._cleanup()


@pytest.fixture
def igw_loopback_harness(
    _igw_app_context: ClientContext,
    _igw_loopback_context: str,
    httpserver: HTTPServer,
) -> Generator[Callable[..., IGWLoopbackHarness], None, None]:
    """Factory for an IGW loopback harness.

    Call with no arguments for the default IGW + Models app:
    ``harness = igw_loopback_harness()``.

    Passing extra service classes (``igw_loopback_harness(GuardrailsService)``)
    raises :class:`TypeError` — the module-scoped app is already built
    with a fixed service list by the time the factory runs. Mount extra
    services for the whole module by overriding the
    ``_igw_extra_services`` module fixture in the plugin's
    ``conftest.py``.
    """
    with ExitStack() as stack:

        def factory(*extra_services: ServiceFactory) -> IGWLoopbackHarness:
            return stack.enter_context(
                _build_loopback_harness(
                    _igw_app_context,
                    httpserver,
                    _igw_loopback_context,
                    *extra_services,
                )
            )

        yield factory


__all__ = [
    "_igw_app_context",
    "_igw_extra_services",
    "_igw_loopback_context",
    "igw_loopback_harness",
    "igw_plugin_harness",
]
