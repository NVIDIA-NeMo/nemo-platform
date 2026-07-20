# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level Models helpers built on the typed :class:`ModelsClient`.

Historically ``ModelsResource`` / ``AsyncModelsResource`` extended the
Stainless-generated ``ModelsResource`` base to inherit its CRUD surface and
layered convenience helpers on top. As part of AIRCORE-876 the Stainless-
resource *inheritance* is removed: these classes now hold a ``NeMoPlatform``
SDK and drive the typed ``nemo_platform_plugin.models.client.ModelsClient``
(built from that SDK via ``client_from_platform``) for their own genuine public
surface -- the inference-gateway route builders, OpenAI client factories, and
deployment/provider status polling.

CRUD (``retrieve`` / ``create`` / ``list`` / adapter sub-resource) is
intentionally *not* re-implemented here: reproducing the Stainless resource
method/param shapes would be a compatibility proxy. Callers that need CRUD
should use the typed client directly, e.g.::

    from nemo_platform_plugin.client.adapter import client_from_platform
    from nemo_platform_plugin.models.client import ModelsClient

    models = client_from_platform(sdk, ModelsClient)
    entity = models.get_model(name="llama", workspace="default").data()

.. warning::
    **Vendoring gate.** This package is vendored into the SDK as
    ``nemo_platform.models`` (``sdk.models`` resolves to this ``ModelsResource``
    via ``packages/models`` ``[tool.vendor-package]``). Because the Stainless
    CRUD inheritance is dropped above, running ``make vendor`` will remove
    ``sdk.models.retrieve`` / ``create`` / ``list`` / ``adapters.*`` from the
    vendored SDK and break every consumer still on that surface (automodel
    compiler, provider/deployment reconcilers, models_controller, adapter
    sidecar, model_spec task, ``nmp_customization_common``, evaluator resolver,
    inference-gateway model cache, generated CLI). Those call sites must first be
    migrated to the typed client and repointed from ``nemo_platform`` exceptions
    to ``nemo_platform_plugin.client.errors`` (``NotFoundError`` / ``ConflictError``
    are distinct classes). Do not run ``make vendor`` for this package until that
    consumer migration lands -- it is a separate follow-up under the AIRCORE-827
    migration umbrella.

The inference-gateway *readiness* probe (:meth:`wait_for_gateway`) still calls
through the ``NeMoPlatform`` SDK because it targets the separate
inference-gateway service, which has not yet been migrated to a typed client.
"""

from __future__ import annotations

import time
from datetime import datetime

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform, NotFoundError
from nemo_platform.types.inference import ModelDeployment, ModelProvider
from nemo_platform.types.models import ModelEntity
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.models.client import AsyncModelsClient, ModelsClient


class ModelsResource:
    """Sync Models helpers backed by a typed :class:`ModelsClient`.

    Example:
        >>> sdk = NeMoPlatform(base_url="http://nmp-host", workspace="default")
        >>> sdk.models.get_openai_route_base_url()
        >>> sdk.models.wait_for_status("my-deployment", "READY")
    """

    def __init__(self, client: NeMoPlatform) -> None:
        self._client = client
        self._typed: ModelsClient | None = None

    @property
    def models(self) -> ModelsClient:
        """The typed Models client sharing this SDK's transport (built lazily)."""
        if self._typed is None:
            self._typed = client_from_platform(self._client, ModelsClient)
        return self._typed

    def _get_base_url_str(self) -> str:
        """Get the base URL as a string with trailing slash removed."""
        return str(self._client.base_url).rstrip("/")

    # -- OpenAI inference-gateway route builders (delegate to the typed client) --

    def get_openai_route_base_url(self, *, workspace: str | None = None) -> str:
        """Base URL for the OpenAI proxy route (routes on the request body ``model``)."""
        return self.models.get_openai_route_base_url(workspace=workspace)

    def get_client_default_headers(self) -> dict[str, str]:
        """String-only default headers for third-party client libraries (OpenAI SDK, LiteLLM).

        Forwards the SDK's auth/identity headers, required for inference when
        platform authorization is enabled.
        """
        return {key: value for key, value in self._client.default_headers.items() if isinstance(value, str)}

    def get_openai_client(self, *, workspace: str | None = None):
        """A sync OpenAI client configured for NeMo Platform's inference gateway."""
        import openai

        base_url = self.get_openai_route_base_url(workspace=workspace)
        default_headers = self.get_client_default_headers()
        return openai.OpenAI(base_url=base_url, api_key="not-needed", default_headers=default_headers)

    def get_provider_route_openai_url(self, provider: ModelProvider) -> str:
        """OpenAI SDK-compatible URL for a provider proxy route (conditional ``/v1``)."""
        return self.models.get_provider_route_openai_url(provider)

    def get_provider_route_openai_url_for_deployment(self, deployment: ModelDeployment) -> str:
        """Fetch a deployment's ModelProvider and return its OpenAI route URL."""
        return self.models.get_provider_route_openai_url_for_deployment(deployment)

    def get_model_entity_route_openai_url(self, model_entity: ModelEntity) -> str:
        """OpenAI SDK-compatible URL for a model-entity proxy route (always ``/v1``)."""
        return self.models.get_model_entity_route_openai_url(model_entity)

    # -- Deployment / provider status polling --

    def wait_for_status(
        self,
        deployment_name: str,
        desired_status: str,
        *,
        workspace: str | None = None,
        timeout: int = 1200,
        check_gateway: bool = True,
    ) -> bool:
        """Wait for a ModelDeployment to reach ``desired_status``.

        When ``desired_status`` is ``"READY"`` and ``check_gateway`` is set, also
        waits for the inference gateway to be able to route to the provider.
        """
        if not self.models.wait_for_deployment_status(
            deployment_name, desired_status, workspace=workspace, timeout=timeout
        ):
            return False
        if desired_status == "READY" and check_gateway:
            return self.wait_for_gateway(deployment_name, workspace=workspace, timeout=timeout)
        return True

    def wait_for_deployment_status(
        self,
        deployment_name: str,
        desired_status: str,
        *,
        workspace: str | None = None,
        timeout: int = 1200,
    ) -> bool:
        """Wait for a ModelDeployment to reach ``desired_status`` (or 404 for ``DELETED``)."""
        return self.models.wait_for_deployment_status(
            deployment_name, desired_status, workspace=workspace, timeout=timeout
        )

    def wait_for_provider(
        self,
        provider_name: str,
        desired_status: str = "READY",
        *,
        workspace: str | None = None,
        timeout: int = 60,
        check_gateway: bool = True,
    ) -> bool:
        """Wait for a ModelProvider to reach ``desired_status`` (optionally gateway-ready)."""
        if not self.models.wait_for_provider_status(
            provider_name, desired_status, workspace=workspace, timeout=timeout
        ):
            return False
        if desired_status == "READY" and check_gateway:
            return self.wait_for_gateway(provider_name, workspace=workspace, timeout=timeout)
        return True

    def wait_for_gateway(
        self,
        provider_name: str,
        *,
        workspace: str | None = None,
        timeout: int = 60,
    ) -> bool:
        """Wait for the inference gateway to be able to route to a provider.

        Targets the separate inference-gateway service, which is not yet migrated
        to a typed client, so this still calls through the ``NeMoPlatform`` SDK.
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        start_time = time.time()
        print("Waiting for gateway to be ready...")
        while time.time() - start_time < timeout:
            try:
                self._client.inference.gateway.provider.ready(provider_name, workspace=workspace)
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Gateway is ready!\n")
                return True
            except NotFoundError:
                time.sleep(1)
            except Exception:
                time.sleep(1)
        print(f"Gateway timeout after {int(time.time() - start_time)}s\n")
        return False


class AsyncModelsResource:
    """Async twin of :class:`ModelsResource`.

    Route builders are synchronous (no I/O) and safe to call from async code;
    methods that perform I/O are async.
    """

    def __init__(self, client: AsyncNeMoPlatform) -> None:
        self._client = client
        self._typed: AsyncModelsClient | None = None

    @property
    def models(self) -> AsyncModelsClient:
        """The typed async Models client sharing this SDK's transport (built lazily)."""
        if self._typed is None:
            self._typed = client_from_platform(self._client, AsyncModelsClient)
        return self._typed

    def _get_base_url_str(self) -> str:
        """Get the base URL as a string with trailing slash removed."""
        return str(self._client.base_url).rstrip("/")

    def get_openai_route_base_url(self, *, workspace: str | None = None) -> str:
        """Base URL for the OpenAI proxy route. Synchronous (no I/O)."""
        return self.models.get_openai_route_base_url(workspace=workspace)

    def get_client_default_headers(self) -> dict[str, str]:
        """String-only default headers for third-party client libraries."""
        return {key: value for key, value in self._client.default_headers.items() if isinstance(value, str)}

    def get_async_openai_client(self, *, workspace: str | None = None):
        """An async OpenAI client configured for NeMo Platform's inference gateway."""
        import openai

        base_url = self.get_openai_route_base_url(workspace=workspace)
        default_headers = self.get_client_default_headers()
        return openai.AsyncOpenAI(base_url=base_url, api_key="not-needed", default_headers=default_headers)

    def get_provider_route_openai_url(self, provider: ModelProvider) -> str:
        """OpenAI SDK-compatible URL for a provider proxy route. Synchronous (no I/O)."""
        return self.models.get_provider_route_openai_url(provider)

    async def get_provider_route_openai_url_for_deployment(self, deployment: ModelDeployment) -> str:
        """Fetch a deployment's ModelProvider and return its OpenAI route URL."""
        return await self.models.get_provider_route_openai_url_for_deployment(deployment)

    def get_model_entity_route_openai_url(self, model_entity: ModelEntity) -> str:
        """OpenAI SDK-compatible URL for a model-entity proxy route. Synchronous (no I/O)."""
        return self.models.get_model_entity_route_openai_url(model_entity)

    async def wait_for_status(
        self,
        deployment_name: str,
        desired_status: str,
        *,
        workspace: str | None = None,
        timeout: int = 1200,
        check_gateway: bool = True,
    ) -> bool:
        """Wait for a ModelDeployment to reach ``desired_status`` (optionally gateway-ready)."""
        if not await self.models.wait_for_deployment_status(
            deployment_name, desired_status, workspace=workspace, timeout=timeout
        ):
            return False
        if desired_status == "READY" and check_gateway:
            return await self.wait_for_gateway(deployment_name, workspace=workspace, timeout=timeout)
        return True

    async def wait_for_deployment_status(
        self,
        deployment_name: str,
        desired_status: str,
        *,
        workspace: str | None = None,
        timeout: int = 1200,
    ) -> bool:
        """Wait for a ModelDeployment to reach ``desired_status`` (or 404 for ``DELETED``)."""
        return await self.models.wait_for_deployment_status(
            deployment_name, desired_status, workspace=workspace, timeout=timeout
        )

    async def wait_for_provider(
        self,
        provider_name: str,
        desired_status: str = "READY",
        *,
        workspace: str | None = None,
        timeout: int = 60,
        check_gateway: bool = True,
    ) -> bool:
        """Wait for a ModelProvider to reach ``desired_status`` (optionally gateway-ready)."""
        if not await self.models.wait_for_provider_status(
            provider_name, desired_status, workspace=workspace, timeout=timeout
        ):
            return False
        if desired_status == "READY" and check_gateway:
            return await self.wait_for_gateway(provider_name, workspace=workspace, timeout=timeout)
        return True

    async def wait_for_gateway(
        self,
        provider_name: str,
        *,
        workspace: str | None = None,
        timeout: int = 60,
    ) -> bool:
        """Wait for the inference gateway to be able to route to a provider.

        Targets the separate inference-gateway service (not yet migrated to a
        typed client), so this still calls through the ``AsyncNeMoPlatform`` SDK.
        """
        import asyncio

        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        start_time = time.time()
        print("Waiting for gateway to be ready...")
        while time.time() - start_time < timeout:
            try:
                await self._client.inference.gateway.provider.ready(provider_name, workspace=workspace)
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Gateway is ready!\n")
                return True
            except NotFoundError:
                await asyncio.sleep(1)
            except Exception:
                await asyncio.sleep(1)
        print(f"Gateway timeout after {int(time.time() - start_time)}s\n")
        return False
