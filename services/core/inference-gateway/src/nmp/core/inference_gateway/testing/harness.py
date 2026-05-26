# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration harness for IGW middleware plugin tests.

Design:

- One real HTTP boundary owned by ``pytest_httpserver``. The IGW + Models
  app runs in-process via ``httpx.ASGITransport`` (no uvicorn, no real
  port). Both the proxy step's outbound HTTP and any plugin-side outbound
  HTTP terminate at the same socket.
- Providers are plain (not ``igw-mock-`` prefixed) — their ``host_url``
  points at the mock NIM so IGW issues real HTTP that the mock answers.
- Assertions read the mock NIM's per-call request log rather than
  matching response IDs through the proxy.

Sync entry points (:meth:`IGWPluginHarness.add_virtual_model`, etc.) call
``asyncio.run`` internally, so they must not run inside a live event
loop. Async tests use the ``a``-prefixed siblings
(:meth:`aadd_virtual_model`, :meth:`achat_completions`,
:meth:`ause_plugin`).

Companion fixture: :mod:`nmp.core.inference_gateway.testing.fixtures`.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Generator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, cast

from fastapi.testclient import TestClient
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform, omit
from nemo_platform.types.inference import ModelProvider
from nemo_platform.types.inference.middleware_call_param import MiddlewareCallParam
from nemo_platform.types.inference.virtual_model import VirtualModel as SDKVirtualModel
from nemo_platform.types.inference.virtual_model_inference_config_param import VirtualModelInferenceConfigParam
from nemo_platform_plugin.discovery import discover_inference_middleware
from nemo_platform_plugin.inference_middleware import NemoInferenceMiddleware
from nmp.common.entities.client import EntityClient
from nmp.core.inference_gateway.api.dependencies import (
    global_middleware_registry,
    global_model_cache,
    global_virtual_model_cache,
)
from nmp.core.inference_gateway.api.middleware_registry import (
    InferenceMiddlewareCacheAccessorImpl,
    MiddlewareRegistry,
)
from nmp.core.inference_gateway.api.model_cache import ModelCache, ModelProviderInfo
from nmp.core.inference_gateway.api.virtual_model_cache import (
    VirtualModelCache,
    refresh_virtual_model_cache,
)
from nmp.testing.client import ClientContext
from nmp.testing.mock_chat_completions import (
    BodyPredicate,
    ChatCompletion,
    ChatCompletionStream,
    MockChatCompletionsHandler,
    MockResponse,
    RecordedRequest,
)
from pytest_httpserver import HTTPServer

logger = logging.getLogger(__name__)

DEFAULT_MOCK_CHAT_PATH = "/v1/chat/completions"

DEFAULT_WORKSPACE = "default"
"""Workspace seeded by :func:`~nmp.testing.client.create_test_client` at
module-fixture setup. Exposed on the harness as :attr:`IGWPluginHarness.workspace`
so test bodies can read it without hardcoding ``"default"`` — when the
fixture migrates to per-test workspaces (Option B in AIRCORE-585), only
the harness internals change and existing test bodies keep working."""


@dataclass
class IGWPluginHarness:
    """Integration harness for IGW middleware plugins.

    Owns a :class:`~nmp.testing.client.ClientContext` (sync + async SDK,
    :class:`TestClient`, :class:`EntityClient`) backed by an in-process
    ASGI IGW + Models app, a :class:`HTTPServer` (``mock_nim``) — the
    only real listening socket — and a
    :class:`MockChatCompletionsHandler` pre-mounted at
    ``POST /v1/chat/completions`` on it.

    Construct via :func:`igw_plugin_harness` (the pytest fixture).
    """

    sdk: NeMoPlatform
    async_sdk: AsyncNeMoPlatform
    test_client: TestClient
    entity_client: EntityClient

    mock_nim: HTTPServer
    """The single real socket in the test process. Tests can register
    extra routes on it (e.g. ``/v1/embeddings``) beyond the auto-mounted
    chat-completions handler.

    The auto-mounted handler uses ``expect_request`` (a *permanent*
    matcher). A test mounting a oneshot matcher for
    ``/v1/chat/completions`` wins for the first call; subsequent calls
    fall back to the permanent handler — usually what tests want."""

    handler: MockChatCompletionsHandler
    """Mounted chat-completions handler. Tests register responses via
    :meth:`mock_chat_completions` and assert via :meth:`assert_call_count`
    and friends rather than touching this directly."""

    workspace: str
    """Workspace seeded by the module-scoped app context. Reach for this
    instead of a literal ``"default"`` so test bodies stay portable if
    the fixture later issues a per-test workspace (Option B)."""

    _registry: MiddlewareRegistry
    _model_cache: ModelCache
    _vm_cache: VirtualModelCache
    _cache_accessor: InferenceMiddlewareCacheAccessorImpl
    _virtual_models: list[tuple[str, str]]
    """``(workspace, name)`` of VMs created by this harness — torn down on cleanup."""
    _providers: list[tuple[str, str]]
    """``(workspace, name)`` of providers created via :meth:`add_provider` —
    deleted from the entity store on cleanup so a stale row can't re-enter
    the model cache on the next test in a module-scoped fixture."""
    _secrets: list[tuple[str, str]]
    """``(workspace, name)`` of secrets created via :meth:`create_secret` —
    deleted on cleanup in dependency order after providers."""

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------

    @classmethod
    def _build(
        cls,
        *,
        client_context: ClientContext,
        mock_nim: HTTPServer,
        workspace: str = DEFAULT_WORKSPACE,
        **extra_fields: Any,
    ) -> "IGWPluginHarness":
        """Construct a harness around an already-running IGW + Models app.

        Subclasses (e.g. :class:`IGWLoopbackHarness`) pass their extra
        dataclass fields through *extra_fields* so the same ``cls(...)``
        call wires up parent + subclass fields together.
        """
        registry = global_middleware_registry()
        model_cache = global_model_cache()
        vm_cache = global_virtual_model_cache()
        cache_accessor = InferenceMiddlewareCacheAccessorImpl(
            _model_cache=model_cache,
            _virtual_model_cache=vm_cache,
        )

        handler = MockChatCompletionsHandler()
        # Permanent matcher; the handler dispatches by body["model"].
        mock_nim.expect_request(DEFAULT_MOCK_CHAT_PATH, method="POST").respond_with_handler(handler)

        return cls(
            sdk=client_context.sdk,
            async_sdk=client_context.async_sdk,
            test_client=client_context.test_client,
            entity_client=client_context.entity_client,
            mock_nim=mock_nim,
            handler=handler,
            workspace=workspace,
            _registry=registry,
            _model_cache=model_cache,
            _vm_cache=vm_cache,
            _cache_accessor=cache_accessor,
            _virtual_models=[],
            _providers=[],
            _secrets=[],
            **extra_fields,
        )

    def _cleanup(self) -> None:
        """Delete this test's entities from the entity store and runtime state.

        Order matters: VMs first (they reference provider-derived model
        entities via ``default_model_entity``), then providers (they
        reference secrets via ``api_key_secret_name``), then secrets.
        Each step is ``try/except``-guarded with ``logger.warning`` so a
        single delete failure can't mask the test's own failure.

        Module-scoped fixtures rely on this to keep the entity store
        clean between tests; a stray provider row would otherwise
        re-enter ``ModelCache`` on the next ``refresh_model_cache`` and
        trigger plugin ``notify_upserted`` callbacks on a dead VM. The
        runtime caches are still rebuilt after entity deletion so a
        plugin observing the registry between tests doesn't see ghost
        VMs.

        **Scope of guaranteed cleanup.**

        * **Plugins loaded via** :meth:`use_plugin` / :meth:`load_plugin`
          (the supported pattern for per-test plugin registration) are
          already removed from the registry by the time ``_cleanup``
          runs — the test body's ``with`` block exits before fixture
          teardown — so the plugin instance is unreachable and its
          internal per-VM state goes with it.
        * **Plugins registered persistently at app startup** (via
          :func:`load_middleware_plugins` and the
          ``nemo.inference_middleware`` entry-point group) survive the
          whole module. ``_cleanup`` calls ``registry.evict(key)`` for
          each tracked VM but does **not** call
          ``registry.notify_destroyed(vm)`` — the
          ``on_virtual_model_destroyed`` hook only fires from inside
          :func:`refresh_virtual_model_cache`. Any per-VM state such a
          plugin tracks (warmed caches, indexes, etc.) leaks across
          tests in the module. Persistent plugins that need cleanup
          notifications should subscribe to their own cache invalidation
          path rather than depend on this teardown.
        * ``registry.broken_vms`` (set on resolve failure) and
          :attr:`VirtualModelCache.config_ref_versions` are not pruned
          here; they self-heal on the next
          :func:`refresh_virtual_model_cache` triggered by
          :meth:`add_virtual_model` / :meth:`refresh_caches`. Tests that
          neither create a VM nor call ``refresh_caches`` after a
          previous test's failures may observe stale entries; in
          practice every test that exercises the registry creates a
          fresh VM and the next refresh cleans up.
        """
        for workspace, name in reversed(self._virtual_models):
            try:
                self.sdk.inference.virtual_models.delete(name=name, workspace=workspace)
            except Exception:
                logger.warning(
                    "Failed to delete VirtualModel %r in workspace %r during harness cleanup",
                    name,
                    workspace,
                    exc_info=True,
                )

        for workspace, name in reversed(self._providers):
            try:
                self.sdk.inference.providers.delete(name=name, workspace=workspace)
            except Exception:
                logger.warning(
                    "Failed to delete ModelProvider %r in workspace %r during harness cleanup",
                    name,
                    workspace,
                    exc_info=True,
                )

        for workspace, name in reversed(self._secrets):
            try:
                self.sdk.secrets.delete(name=name, workspace=workspace)
            except Exception:
                logger.warning(
                    "Failed to delete Secret %r in workspace %r during harness cleanup",
                    name,
                    workspace,
                    exc_info=True,
                )

        # Rebuild caches so they reflect the post-delete entity store
        # state. The middleware registry's per-VM factories are removed
        # via evict; the VM cache rebuild drops the same set.
        for key in self._virtual_models:
            self._registry.evict(key)
        removed = set(self._virtual_models)
        if removed:
            self._vm_cache.rebuild(
                [vm for vm in self._vm_cache.virtual_model_map.values() if (vm.workspace, vm.name) not in removed]
            )
        # Drop provider rows from the model cache too — without this,
        # the next ``add_provider`` fast-path would see stale
        # ``ModelProviderInfo`` entries from the deleted providers (and
        # the rebuilt entity map would still resolve through them).
        for workspace, name in self._providers:
            self._model_cache.workspace_name_provider_map.pop((workspace, name), None)
        self._model_cache.rebuild_model_entity_map()

        self._virtual_models.clear()
        self._providers.clear()
        self._secrets.clear()

    # ------------------------------------------------------------------
    # Public conveniences
    # ------------------------------------------------------------------

    @property
    def nim_base_url(self) -> str:
        """OpenAI-compatible base URL — pass as ``parameters.base_url``.

        Resolves to ``http://<host>:<port>/v1``. Both the IGW proxy step
        and an OpenAI client built from this URL hit the auto-mounted
        handler.
        """
        return self.mock_nim.url_for("/v1")

    @property
    def nim_host_url(self) -> str:
        """Bare ``http://host:port`` — what providers want as ``host_url``."""
        return self.mock_nim.url_for("").rstrip("/")

    # ------------------------------------------------------------------
    # Plugin registration (context-managed)
    # ------------------------------------------------------------------

    @contextmanager
    def use_plugin(
        self,
        name: str,
        plugin: NemoInferenceMiddleware,
        *,
        call_lifecycle: bool = True,
    ) -> Generator[NemoInferenceMiddleware, None, None]:
        """Register *plugin* under *name*; restore the prior entry on exit.

        The cache accessor is injected before yield, so plugin cache
        methods (``get_inference_url_and_model``, ``get_virtual_model``,
        ...) work inside the context.

        **Production parity:** prefer :meth:`load_plugin` when the plugin's
        package is pip-installed in the test venv — it discovers the plugin
        via the same ``nemo.inference_middleware`` entry-point group IGW
        uses in production. Reach for ``use_plugin`` when the plugin isn't
        installable (workspace-only, like the example plugin) or when you
        need to substitute a :class:`MagicMock` /
        :class:`AsyncMock`-spec'd instance.

        ``call_lifecycle=True`` (the default) runs ``on_startup`` /
        ``on_shutdown`` via :func:`asyncio.run`, which spins up a **fresh
        disposable event loop** for each. This matches what production does
        (lifespan startup + shutdown) and is what plugins like Guardrails
        require to wire up their SDK / cache; the previous
        ``call_lifecycle=False`` default silently 503'd every request for
        such plugins.

        Loop-bound resources (``aiohttp.ClientSession``, ``asyncio.Lock`` /
        ``Queue``, long-lived Tasks) created in ``on_startup`` will be torn
        down on a different loop in ``on_shutdown`` and may emit "attached
        to a different loop"; if the plugin *uses* such resources during
        :meth:`process_request` / :meth:`process_response`, the request
        will fail with the same error because the request loop differs from
        the loop ``on_startup`` ran on. Drive those tests from an
        ``async def`` and use :meth:`ause_plugin` instead — both lifecycle
        hooks then run on the test's own loop, matching the request loop.

        Pass ``call_lifecycle=False`` to skip the hooks entirely (useful
        for ``MagicMock(spec=Plugin)`` substitutions or for tests that
        manually drive the lifecycle).
        """
        original_present = name in self._registry.plugins
        original = self._registry.plugins.get(name)

        plugin._inject_cache(self._cache_accessor)
        if call_lifecycle:
            asyncio.run(plugin.on_startup())
        self._registry.plugins[name] = plugin
        try:
            yield plugin
        finally:
            if original_present:
                self._registry.plugins[name] = original  # type: ignore[assignment]
            else:
                self._registry.plugins.pop(name, None)
            if call_lifecycle:
                # Log instead of raising so cleanup failures are visible
                # without masking the test outcome.
                try:
                    asyncio.run(plugin.on_shutdown())
                except Exception:
                    logger.warning(
                        "Plugin %r on_shutdown raised during use_plugin teardown",
                        name,
                        exc_info=True,
                    )

    @asynccontextmanager
    async def ause_plugin(
        self,
        name: str,
        plugin: NemoInferenceMiddleware,
        *,
        call_lifecycle: bool = True,
    ) -> AsyncGenerator[NemoInferenceMiddleware, None]:
        """Async variant of :meth:`use_plugin`.

        Both lifecycle hooks run on the test's own running loop (the same
        loop the request will execute on), so loop-bound resources created
        in ``on_startup`` stay valid through ``on_shutdown``. This is the
        loop-safe alternative to :meth:`use_plugin` for plugins whose
        startup builds long-lived loop-bound resources.
        """
        original_present = name in self._registry.plugins
        original = self._registry.plugins.get(name)

        plugin._inject_cache(self._cache_accessor)
        if call_lifecycle:
            await plugin.on_startup()
        self._registry.plugins[name] = plugin
        try:
            yield plugin
        finally:
            if original_present:
                self._registry.plugins[name] = original  # type: ignore[assignment]
            else:
                self._registry.plugins.pop(name, None)
            if call_lifecycle:
                try:
                    await plugin.on_shutdown()
                except Exception:
                    logger.warning(
                        "Plugin %r on_shutdown raised during ause_plugin teardown",
                        name,
                        exc_info=True,
                    )

    @contextmanager
    def load_plugin(
        self,
        name: str,
        *,
        call_lifecycle: bool = True,
    ) -> Generator[NemoInferenceMiddleware, None, None]:
        """Load *name* via the production ``nemo.inference_middleware`` entry-point group.

        This is the production-parity path — IGW's
        :func:`~nmp.core.inference_gateway.api.middleware_registry.load_middleware_plugins`
        uses the same :func:`~nemo_platform_plugin.discovery.discover_inference_middleware`
        function to walk the same entry-point group. A test that goes through
        ``load_plugin`` therefore exercises the entry-point declaration in
        the plugin's ``pyproject.toml`` and catches misconfigurations
        (missing entry-point key, wrong import path, broken class import)
        that :meth:`use_plugin` silently glosses over.

        Use :meth:`use_plugin` only when:

        - The plugin isn't pip-installed in the test venv (workspace-only
          plugins like the example plugin are not discoverable).
        - You need to substitute a :class:`MagicMock` /
          :class:`AsyncMock`-spec'd instance.
        - You need to pre-configure plugin instance state before
          ``on_startup`` runs.

        ``call_lifecycle`` defaults to ``True`` — same as :meth:`use_plugin`;
        see that method's docstring for the loop-binding caveat. For plugins
        that build loop-bound resources in ``on_startup``, drive the test
        from an ``async def`` and use :meth:`aload_plugin`.

        Raises:
            ValueError: If no plugin is registered under *name* in the
                ``nemo.inference_middleware`` entry-point group.
        """
        instance = _instantiate_discovered_plugin(name)
        with self.use_plugin(name, instance, call_lifecycle=call_lifecycle) as plugin:
            yield plugin

    @asynccontextmanager
    async def aload_plugin(
        self,
        name: str,
        *,
        call_lifecycle: bool = True,
    ) -> AsyncGenerator[NemoInferenceMiddleware, None]:
        """Async variant of :meth:`load_plugin`."""
        instance = _instantiate_discovered_plugin(name)
        async with self.ause_plugin(name, instance, call_lifecycle=call_lifecycle) as plugin:
            yield plugin

    # ------------------------------------------------------------------
    # Secret / Provider / VirtualModel creation (refresh hidden)
    # ------------------------------------------------------------------

    def create_secret(
        self,
        *,
        workspace: str,
        name: str,
        value: str,
        description: str | None = None,
    ) -> str:
        """Create a Secret via the SDK and track it for harness cleanup.

        Prefer this over a direct ``self.sdk.secrets.create(...)`` call —
        only harness-mediated entities are tracked, and a secret created
        directly will leak across tests when the fixture is module-scoped
        (and may then keep a deleted provider's ``api_key_secret_name``
        reference alive on the next ``refresh_model_cache``).

        Args:
            workspace: Workspace the secret lives in.
            name: Secret name. Must be unique within the workspace.
            value: Secret payload (returned by the secrets SDK as
                ``secret_value`` during model-cache refresh).
            description: Optional human-readable description.

        Returns:
            *name* unchanged — useful when chaining into
            :meth:`add_provider` (``api_key_secret_name=harness.create_secret(...)``).
        """
        kwargs: dict[str, Any] = {"workspace": workspace, "name": name, "value": value}
        if description is not None:
            kwargs["description"] = description
        self.sdk.secrets.create(**kwargs)
        self._secrets.append((workspace, name))
        return name

    def add_provider(
        self,
        *,
        workspace: str,
        served_models: Mapping[str, str],
        name: str | None = None,
        host_url: str | None = None,
        enabled_models: Sequence[str] | None = None,
        api_key_secret_name: str | None = None,
    ) -> ModelProvider:
        """Register a (real, non-mock) ModelProvider routed at the mock NIM.

        Plain provider — no ``igw-mock-`` prefix — so the proxy step
        issues a real HTTP request, terminating at ``mock_nim`` because
        ``host_url`` defaults to :attr:`nim_host_url`.

        Call this **before** :meth:`add_virtual_model` for any VM that
        references the provider — the VM-cache refresh resolves
        middleware configs against the model cache, and an unknown
        ``default_model_entity`` silently produces an empty
        pre-resolved-call list for that VM.

        **Auth-aware refresh:** when *api_key_secret_name* is set, the
        method runs the full :func:`refresh_model_cache` after creation
        so the provider's ``secret_value`` is resolved via the secrets
        SDK; without that, the proxy would reject inference with HTTP
        424. Without *api_key_secret_name*, the method takes a fast path
        that updates the model cache in-place without secret-resolution
        plumbing.

        Args:
            workspace: Provider workspace.
            served_models: ``model_entity_name`` → ``served_model_name``.
                The served name is what arrives at the upstream — register
                handler responses under the same key.
            name: Provider name. Auto-generated if omitted (recommended;
                fixture isolation guarantees uniqueness). An explicit
                duplicate name raises ``ConflictError`` so isolation
                breakage fails loudly rather than masked by delete+recreate.
            host_url: Override the default mock NIM URL.
            enabled_models: Optional enabled-models list for the SDK.
            api_key_secret_name: Name of an existing platform Secret to
                attach as the provider's bearer token. The secret must
                already exist in *workspace* — create it via
                ``self.sdk.secrets.create(...)`` before calling this
                method. When set, triggers a full cache refresh so the
                secret value is resolved.

        Returns:
            The created ``ModelProvider`` (read back via ``retrieve``
            after ``update_status``, so its ``id`` and ``served_models``
            reflect entity-store state).

        Raises:
            ConflictError: If a provider with *name* already exists in
                *workspace*.
        """
        from nmp.testing.utils import short_unique_name

        provider_name = name or short_unique_name("provider")
        host = host_url or self.nim_host_url

        self.sdk.inference.providers.create(
            workspace=workspace,
            name=provider_name,
            host_url=host,
            enabled_models=list(enabled_models) if enabled_models is not None else omit,
            api_key_secret_name=api_key_secret_name if api_key_secret_name is not None else omit,
        )
        # Track immediately after ``create`` succeeds so a later raise from
        # ``update_status`` or ``retrieve`` still leaves the provider
        # eligible for teardown — module-scoped fixtures rely on every
        # row being deleted between tests, even partial-failure rows.
        self._providers.append((workspace, provider_name))

        # served_models persisted via update_status (the create path
        # doesn't accept them) so they survive future cache refreshes.
        self.sdk.inference.providers.update_status(
            name=provider_name,
            workspace=workspace,
            served_models=[
                {
                    "model_entity_id": f"{workspace}/{entity_name}",
                    "served_model_name": served_name,
                }
                for entity_name, served_name in served_models.items()
            ],
        )

        # Read authoritative state back so the cache stays in sync with
        # whatever id / served_models shape / timestamps the entity store
        # actually assigned.
        provider = self.sdk.inference.providers.retrieve(name=provider_name, workspace=workspace)

        if api_key_secret_name is not None:
            # Full refresh resolves the secret via the secrets SDK.
            asyncio.run(self._refresh_model_cache())
        else:
            # Fast path: in-place cache update; skips secrets plumbing.
            self._model_cache.update_model_info(ModelProviderInfo(model_provider=provider))
            self._model_cache.rebuild_model_entity_map()

        return provider

    def add_virtual_model(
        self,
        *,
        workspace: str,
        name: str,
        default_model_entity: str | None = None,
        models: Sequence[VirtualModelInferenceConfigParam] = (),
        request_middleware: Sequence[MiddlewareCallParam] = (),
        response_middleware: Sequence[MiddlewareCallParam] = (),
        post_response_middleware: Sequence[MiddlewareCallParam] = (),
    ) -> SDKVirtualModel:
        """Create a VirtualModel and refresh IGW's VM cache so it routes immediately.

        Sync entry point — the cache refresh runs via :func:`asyncio.run`,
        so this must not run inside a live event loop. Use
        :meth:`aadd_virtual_model` from async tests.

        Call :meth:`add_provider` first for any provider this VM
        references; otherwise middleware-config pre-resolution sees an
        empty model cache.

        ``models`` is the per-VM list of model entity references with
        optional ``backend_format`` overrides. Plugins like
        ``nemo-switchyard`` read ``virtual_model.models`` in
        :meth:`on_virtual_model_upserted` to build their format-aware
        routing tables; pass an entry per backend the test needs.
        Format::

            models=[
                {"model": "default/main", "backend_format": "OPENAI_CHAT"},
                {"model": "default/claude", "backend_format": "ANTHROPIC_MESSAGES"},
            ]

        .. note::
            **Plugin-raised errors during VM upsert are swallowed.** Both
            :meth:`NemoInferenceMiddleware.validate_middleware_config` and
            :meth:`NemoInferenceMiddleware.on_virtual_model_upserted`
            failures are caught by IGW's
            :class:`MiddlewareRegistry` (logged-and-continued, never
            re-raised). So a plugin that rejects a VM at upsert time
            (e.g. switchyard's ``translate``-in-``response_middleware``
            400) will *not* cause this method to raise — the VM lands in
            the entity store, the phase-list ends up empty, and the
            rejection only manifests when the first inference request
            against that VM gets back "no factory registered for VM ..."
            from the plugin. Tests that want to assert a rejection
            should fire a request via :meth:`chat_completions` and check
            for the error there, not assert that ``add_virtual_model``
            itself raises.
        """
        vm = self._create_virtual_model(
            workspace=workspace,
            name=name,
            default_model_entity=default_model_entity,
            models=models,
            request_middleware=request_middleware,
            response_middleware=response_middleware,
            post_response_middleware=post_response_middleware,
        )
        asyncio.run(self._refresh_vm_cache())
        return vm

    async def aadd_virtual_model(
        self,
        *,
        workspace: str,
        name: str,
        default_model_entity: str | None = None,
        models: Sequence[VirtualModelInferenceConfigParam] = (),
        request_middleware: Sequence[MiddlewareCallParam] = (),
        response_middleware: Sequence[MiddlewareCallParam] = (),
        post_response_middleware: Sequence[MiddlewareCallParam] = (),
    ) -> SDKVirtualModel:
        """Async sibling of :meth:`add_virtual_model`."""
        vm = self._create_virtual_model(
            workspace=workspace,
            name=name,
            default_model_entity=default_model_entity,
            models=models,
            request_middleware=request_middleware,
            response_middleware=response_middleware,
            post_response_middleware=post_response_middleware,
        )
        await self._refresh_vm_cache()
        return vm

    def refresh_caches(self) -> None:
        """Refresh model cache **and** VM cache (sync).

        Model cache first — VM-cache resolution depends on the
        served-model topology. The model-cache refresh resolves provider
        secrets via the SDK; call this rather than relying on
        :meth:`add_provider`'s fast path when ``api_key_secret_name`` is set.
        """
        asyncio.run(self._refresh_all_caches())

    async def arefresh_caches(self) -> None:
        """Async sibling of :meth:`refresh_caches`."""
        await self._refresh_all_caches()

    async def _refresh_all_caches(self) -> None:
        await self._refresh_model_cache()
        await self._refresh_vm_cache()

    def _create_virtual_model(
        self,
        *,
        workspace: str,
        name: str,
        default_model_entity: str | None,
        models: Sequence[VirtualModelInferenceConfigParam],
        request_middleware: Sequence[MiddlewareCallParam],
        response_middleware: Sequence[MiddlewareCallParam],
        post_response_middleware: Sequence[MiddlewareCallParam],
    ) -> SDKVirtualModel:
        create_kwargs: dict[str, Any] = {
            "workspace": workspace,
            "name": name,
            "request_middleware": list(request_middleware),
            "response_middleware": list(response_middleware),
            "post_response_middleware": list(post_response_middleware),
        }
        if default_model_entity is not None:
            create_kwargs["default_model_entity"] = default_model_entity
        if models:
            # SDK expects an Iterable of VirtualModelInferenceConfigParam
            # (TypedDict). Skip when empty so we don't send an empty list
            # that some validators treat as "explicitly clear models".
            create_kwargs["models"] = list(models)
        vm = self.sdk.inference.virtual_models.create(**create_kwargs)
        self._virtual_models.append((workspace, name))
        return vm

    async def _refresh_vm_cache(self) -> None:
        await refresh_virtual_model_cache(
            self._vm_cache,
            self.async_sdk,
            registry=self._registry,
        )

    async def _refresh_model_cache(self) -> None:
        # Local import keeps module load cheap; refresh_model_cache pulls
        # in secrets SDK plumbing only needed when explicitly invoked.
        from nmp.core.inference_gateway.api.model_cache import (
            model_provider_getter_from_sdk,
            refresh_model_cache,
        )

        await refresh_model_cache(
            model_cache=self._model_cache,
            model_provider_getter=model_provider_getter_from_sdk(self.async_sdk),
            secrets_sdk=self.async_sdk,
            virtual_model_cache=self._vm_cache,
            middleware_registry=self._registry,
        )

    # ------------------------------------------------------------------
    # Mock NIM convenience
    # ------------------------------------------------------------------

    def mock_chat_completions(self, model: str, responses: Sequence[MockResponse]) -> None:
        """Queue *responses* for chat-completion calls whose ``body["model"] == model``.

        ``model`` is the value that arrives at the upstream. For a
        provider with ``served_models={"main": "main"}`` and an entity
        ``"default/main"``, the upstream receives ``"model": "main"``,
        so register under ``"main"``.

        Plugins issuing their own outbound calls (e.g. Guardrails' rail
        calls) typically send the workspace-qualified entity id —
        ``"default/main"``. Register a separate queue under the entity
        id for those.

        Repeated calls for the same model append; the queue consumes in
        order, reusing the last response if drained.

        Response bodies built with :func:`chat_completion` or
        :func:`chat_completion_chunk` that left ``model`` at the default
        are automatically stamped with the dispatch key so the response
        body's ``"model"`` field matches the routing key without the
        caller having to repeat it.

        Raises:
            ValueError: If *responses* is empty.
        """
        for resp in responses:
            if isinstance(resp, ChatCompletion) and resp.body.get("model") is None:
                resp.body["model"] = model
            elif isinstance(resp, ChatCompletionStream):
                for chunk in resp.chunks:
                    if isinstance(chunk, dict) and chunk.get("model") is None:
                        chunk["model"] = model
        self.handler.add_responses(model, responses)

    # ------------------------------------------------------------------
    # Convenience callers
    # ------------------------------------------------------------------

    def chat_completions(
        self,
        *,
        workspace: str,
        body: dict[str, Any],
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Call IGW's OpenAI-compatible chat completions endpoint via the SDK."""
        result = self.sdk.inference.gateway.openai.post(
            "v1/chat/completions",
            workspace=workspace,
            body=body,
            extra_headers=dict(extra_headers) if extra_headers is not None else None,
        )
        return _coerce_dict(result)

    async def achat_completions(
        self,
        *,
        workspace: str,
        body: dict[str, Any],
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Async sibling of :meth:`chat_completions`."""
        result = await self.async_sdk.inference.gateway.openai.post(
            "v1/chat/completions",
            workspace=workspace,
            body=body,
            extra_headers=dict(extra_headers) if extra_headers is not None else None,
        )
        return _coerce_dict(result)

    def stream_chat_completions(
        self,
        *,
        workspace: str,
        body: dict[str, Any],
        extra_headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Call IGW's chat completions endpoint with streaming and return the parsed body.

        Forces ``stream=True`` on *body* and uses :class:`TestClient` directly
        because the SDK's ``post(...)`` buffers the full body before returning,
        which would defeat the purpose of streaming.

        Returns one of two shapes, depending on the response's ``Content-Type``:

        - ``text/event-stream`` → ``list[dict]`` of parsed SSE chunks in
          order (the terminating ``data: [DONE]`` is dropped). This is the
          normal case: upstream returned a stream and IGW relayed it.
        - ``application/json`` → the raw JSON dict. This happens when a
          plugin short-circuits the proxy with an :class:`ImmediateResponse`
          (e.g. an input rail blocks before any tokens stream); the proxy
          step never runs, so there's nothing to encode as SSE. Callers
          that want to demand SSE can ``isinstance(result, list)`` at the
          call site.

        Use this to integration-test ``process_response`` with an
        :class:`AsyncIterator[dict]` payload, or to assert the JSON body
        a plugin emits when it blocks a streaming request. Pair with a
        :class:`~nmp.testing.mock_chat_completions.ChatCompletionStream`
        mock response for the upstream model on the SSE branch.

        The ``/apis/inference-gateway`` prefix mirrors the production mount
        path (see :func:`nmp.platform_runner.server.create_app`), which is
        what :class:`create_test_client` uses too — without the prefix the
        TestClient returns 404.

        Raises:
            httpx.HTTPStatusError: If IGW returns a non-2xx status.
        """
        streaming_body = {**body, "stream": True}
        path = f"/apis/inference-gateway/v2/workspaces/{workspace}/openai/-/v1/chat/completions"
        response = self.test_client.post(
            path,
            json=streaming_body,
            headers=dict(extra_headers) if extra_headers else None,
        )
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            return _parse_sse_text(response.text)
        return response.json()

    # ------------------------------------------------------------------
    # First-class assertions
    # ------------------------------------------------------------------

    def requests_for(self, model: str) -> list[RecordedRequest]:
        """Return all recorded requests whose ``body["model"] == model``, in order."""
        return [r for r in self.handler.request_log if r.model == model]

    def assert_call_count(self, model: str, n: int) -> None:
        """Assert *model* received exactly *n* requests."""
        actual = self.handler.call_counts.get(model, 0)
        assert actual == n, (
            f"Expected {n} call(s) to model={model!r}, got {actual}. All counts: {dict(self.handler.call_counts)}."
        )

    def assert_called_once(self, model: str) -> None:
        """Assert *model* received exactly one request."""
        self.assert_call_count(model, 1)

    def assert_request_messages_contain(
        self,
        model: str,
        substring: str,
        *,
        index: int = 0,
    ) -> None:
        """Assert the *index*-th recorded request to *model* contains *substring*.

        Searches across the ``content`` field of every message in the
        request body. Raises ``AssertionError`` if no request at *index*
        exists or the substring is missing.
        """
        recorded_for_model = self.requests_for(model)
        if index < 0 or index >= len(recorded_for_model):
            raise AssertionError(
                f"No request at index {index} for model={model!r}; saw {len(recorded_for_model)} call(s)."
            )
        recorded = recorded_for_model[index]
        haystack = " ".join(str(m.get("content", "")) for m in recorded.body.get("messages", []))
        assert substring in haystack, (
            f"Expected {substring!r} in messages for model={model!r} (call #{index}), "
            f"got messages={recorded.body.get('messages')!r}."
        )

    def assert_call_order(self, models: Sequence[str]) -> None:
        """Assert the recorded sequence of model values equals *models*."""
        actual = list(self.handler.call_order)
        expected = list(models)
        assert actual == expected, f"Expected call order {expected!r}, got {actual!r}."

    def assert_no_calls_to(self, model: str) -> None:
        """Assert *model* received zero requests."""
        actual = self.handler.call_counts.get(model, 0)
        assert actual == 0, f"Expected zero calls to model={model!r}, got {actual}."

    def assert_request_body_for(
        self,
        model: str,
        predicate: BodyPredicate,
        *,
        index: int = 0,
    ) -> None:
        """Assert *predicate(body)* is true for the *index*-th recorded request to *model*.

        Generalises :meth:`assert_request_messages_contain` to any property of
        the request body — tool calls, response_format, embedding inputs,
        custom plugin-injected fields, etc. The predicate receives the parsed
        JSON body verbatim.

        Raises:
            AssertionError: If no request at *index* exists for *model*, or
                if the predicate returns falsy.
        """
        recorded_for_model = self.requests_for(model)
        if index < 0 or index >= len(recorded_for_model):
            raise AssertionError(
                f"No request at index {index} for model={model!r}; saw {len(recorded_for_model)} call(s)."
            )
        recorded = recorded_for_model[index]
        if not predicate(recorded.body):
            raise AssertionError(f"Predicate failed for model={model!r} (call #{index}); body={recorded.body!r}.")

    def assert_request_path_for(
        self,
        model: str,
        path: str,
        *,
        index: int = 0,
    ) -> None:
        """Assert the *index*-th recorded request to *model* arrived on *path*.

        Path comparison is exact — a leading slash counts. The mock NIM
        records the path verbatim from the inbound request, so callers
        comparing against IGW-rewritten paths should include the leading
        ``/`` (e.g. ``"/v1/messages"`` not ``"v1/messages"``).

        Useful for plugins that rewrite ``InferenceRequest.path``
        mid-pipeline — most prominently switchyard's ``translate``
        factory, which routes OpenAI Chat requests to the Anthropic
        ``v1/messages`` endpoint by stamping
        :data:`CTX_PATH_UPDATE` into the proxy context. Without a path
        assertion the test only proves the in-memory rewrite happened,
        not that it actually reached the upstream socket.

        Raises:
            AssertionError: If no request at *index* exists for *model*,
                or the recorded path doesn't match *path*.
        """
        recorded_for_model = self.requests_for(model)
        if index < 0 or index >= len(recorded_for_model):
            raise AssertionError(
                f"No request at index {index} for model={model!r}; saw {len(recorded_for_model)} call(s)."
            )
        recorded = recorded_for_model[index]
        if recorded.path != path:
            raise AssertionError(f"Path on call #{index} to model={model!r} was {recorded.path!r}, expected {path!r}.")

    def assert_request_headers_contain(
        self,
        model: str,
        header: str,
        value: str | None = None,
        *,
        index: int = 0,
    ) -> None:
        """Assert the *index*-th recorded request to *model* carries header *header*.

        Header lookup is case-insensitive (matches HTTP semantics). When
        *value* is ``None``, only the header's presence is asserted; when
        *value* is given, an exact match is required. Use
        :meth:`requests_for` directly for substring or duplicate-header
        assertions.

        Raises:
            AssertionError: If no request at *index* exists for *model*, the
                header is absent, or *value* doesn't match.
        """
        recorded_for_model = self.requests_for(model)
        if index < 0 or index >= len(recorded_for_model):
            raise AssertionError(
                f"No request at index {index} for model={model!r}; saw {len(recorded_for_model)} call(s)."
            )
        recorded = recorded_for_model[index]
        actual = recorded.header(header)
        if actual is None:
            header_names = sorted({name for name, _ in recorded.headers})
            raise AssertionError(
                f"Header {header!r} not present on call #{index} to model={model!r}. Headers seen: {header_names}."
            )
        if value is not None and actual != value:
            raise AssertionError(
                f"Header {header!r} on call #{index} to model={model!r} was {actual!r}, expected {value!r}."
            )

    # ------------------------------------------------------------------
    # Post-response (fire-and-forget) flushing
    # ------------------------------------------------------------------

    async def aflush_post_response(self) -> None:
        """Await every fire-and-forget post-response task IGW has scheduled so far.

        IGW schedules :func:`execute_post_response_middleware` via
        :func:`asyncio.create_task` after the response has been sent to the
        caller (see ``proxy.py``). The fixture initialises
        ``app.state.pending_post_response_tasks = []`` and ``proxy.py``
        appends each scheduled task to that list, giving tests a
        deterministic way to await them before asserting.

        **Loop constraint:** post-response tasks are bound to whichever
        event loop scheduled them — typically the loop driving the inbound
        request. ``aflush_post_response`` must run on the same loop.
        That means tests should drive the request via :meth:`achat_completions`
        (so the request and the post-response tasks share the loop) and
        await this method directly. Calling it after a sync
        :meth:`chat_completions` is unsupported because the SDK runs the
        request on a transient loop that's already torn down by the time
        the call returns; the post-response task is unreachable.

        Exceptions raised by post-response middleware are **not** raised
        from here — they're swallowed inside
        :func:`execute_post_response_middleware` (matching production's
        fire-and-forget contract), but task results are awaited via
        ``asyncio.gather(..., return_exceptions=True)`` so a single failure
        doesn't stop the flush.
        """
        pending = self._pending_post_response_tasks()
        if pending is None:
            raise RuntimeError(
                "Post-response task tracking is not enabled. "
                "The fixture must initialise `app.state.pending_post_response_tasks = []` "
                "before any request runs."
            )
        if not pending:
            return
        in_flight = list(pending)
        pending.clear()
        await asyncio.gather(*in_flight, return_exceptions=True)

    def _pending_post_response_tasks(self) -> list[asyncio.Task[None]] | None:
        # ``TestClient.app`` is typed as a bare ``ASGIApp`` callable; cast so
        # ``state`` (a :class:`FastAPI` attribute) is reachable to the type
        # checker. The fixture is responsible for initialising the list.
        from fastapi import FastAPI

        app = cast(FastAPI, self.test_client.app)
        return getattr(app.state, "pending_post_response_tasks", None)


def _coerce_dict(value: Any) -> dict[str, Any]:
    """Cast an SDK response (dict or Pydantic model) to ``dict``.

    Anything else is a programming error — a string error body shouldn't
    pretend to be a dict.
    """
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(
        f"chat_completions returned {type(value).__name__!r}; expected dict or a Pydantic model. Value: {value!r}"
    )


def _parse_sse_text(text: str) -> list[dict[str, Any]]:
    """Parse a buffered SSE response string into a list of chunk dicts.

    Skips ``data: [DONE]`` and silently drops malformed JSON lines (matching
    IGW's own ``_parse_sse_stream`` permissiveness — real upstreams
    occasionally emit keep-alives or comments that aren't JSON).
    """
    import json

    chunks: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            break
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            chunks.append(parsed)
    return chunks


def _instantiate_discovered_plugin(name: str) -> NemoInferenceMiddleware:
    """Locate *name* in the ``nemo.inference_middleware`` entry-point group and instantiate.

    Discovery is cached at the :func:`~nemo_platform_plugin.discovery.discover` layer
    for the process lifetime; tests adding/removing entry points dynamically
    must call ``discover.cache_clear()`` themselves. Raises a verbose
    :class:`ValueError` on miss to nudge callers toward the most common fix
    (install the plugin's package, or fall back to :meth:`use_plugin`).
    """
    discovered = discover_inference_middleware()
    cls = discovered.get(name)
    if cls is None:
        available = sorted(discovered)
        raise ValueError(
            f"No plugin registered under entry-point name {name!r} in the "
            f"'nemo.inference_middleware' group. Available: {available}.\n"
            "Install the plugin's package as a test dependency (so its "
            "pyproject.toml entry point is discoverable via importlib.metadata), "
            "or fall back to use_plugin(name, instance) with a directly-instantiated "
            "plugin object."
        )
    return cls()


@dataclass
class IGWLoopbackHarness(IGWPluginHarness):
    """:class:`IGWPluginHarness` plus IGW served on a real ``127.0.0.1`` port.

    Most plugin tests should prefer :class:`IGWPluginHarness` and pin
    ``parameters.base_url`` directly to :attr:`nim_base_url`. Reach for
    this harness only when the test specifically needs the in-process
    app reachable over a real socket — e.g. when the plugin calls
    :meth:`~nemo_platform_plugin.inference_middleware.InferenceMiddlewareCacheAccessor.get_openai_compatible_inference_url_and_model`
    and the resulting URL must be reachable, or when plugin outbound
    HTTP needs to traverse IGW's full request pipeline (VirtualModel
    resolution + middleware) instead of terminating directly at the
    upstream mock.

    Costs: a uvicorn thread, two extra context-manager levels, and an
    HTTP hop on every plugin-side outbound request. Opt-in for that reason.

    .. warning::

        **Two-loop limitation.** This harness drives the same FastAPI app
        from *two* event loops simultaneously: the :class:`TestClient`'s
        loop (used by the SDK's ASGI transport) and the uvicorn thread's
        loop (used for plugin-originated outbound HTTP that hits the
        loopback URL). Loop-bound resources are tricky here:

        * The fixture overrides :func:`global_http_client` with a
          per-request :class:`aiohttp.ClientSession` so the proxy step's
          HTTP client is always created on the loop handling the inbound
          request. Production uses a process-singleton client tied to
          service lifespan and is unaffected.
        * If a plugin's :meth:`on_startup` builds a long-lived
          loop-bound resource (``aiohttp.ClientSession``, ``asyncio.Lock``,
          long-running ``Task``) and uses it during
          :meth:`process_request`, the resource will be bound to the
          startup loop and likely fail with "attached to a different loop"
          when the request runs on the other loop. Such plugins should
          wire their long-lived resources lazily (per-request, or behind a
          loop-aware factory) — or be tested via the default
          :class:`IGWPluginHarness` where only one loop is in play.
        * Other production shared resources that aren't per-request
          overridable (connection pools, async caches, custom
          ``asyncio.Queue``) carry the same risk and may need similar
          dependency overrides.

        The fixture's three patches (``per_request_http_client``,
        ``override_platform_base_url``, ``serve_app_in_thread``) document
        their individual reasons; the harness-level summary lives here so
        callers see it at point of use.
    """

    igw_loopback_base_url: str
    """``http://<host>:<port>`` — bare loopback root, no path. For
    workspace-scoped openai-compatible URLs use
    :meth:`igw_openai_loopback_url`."""

    def igw_openai_loopback_url(self, workspace: str) -> str:
        """Workspace-scoped OpenAI-compatible loopback URL.

        Pass as ``parameters.base_url`` when plugin outbound HTTP should
        traverse IGW's openai-compatible proxy for *workspace*. Includes
        the ``/v1`` suffix expected by OpenAI clients.
        """
        return f"{self.igw_loopback_base_url}/apis/inference-gateway/v2/workspaces/{workspace}/openai/-/v1"


__all__ = [
    "BodyPredicate",
    "DEFAULT_MOCK_CHAT_PATH",
    "IGWLoopbackHarness",
    "IGWPluginHarness",
]
