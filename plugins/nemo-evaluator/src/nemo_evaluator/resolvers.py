# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Platform resolver implementations for evaluator plugin jobs."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable
from typing import Protocol, TypeVar, cast

from nemo_evaluator_sdk.enums import ModelFormat
from nemo_evaluator_sdk.values.models import Model, ModelRef
from nemo_platform import NotFoundError

_logger = logging.getLogger(__name__)
_T = TypeVar("_T")


class _ModelsResource(Protocol):
    """Models SDK surface used by platform model resolution."""

    def retrieve(self, name: str, *, workspace: str) -> object | Awaitable[object]:
        """Retrieve a model entity by name and workspace."""
        ...

    def get_model_entity_route_openai_url(self, model_entity: object) -> str:
        """Return the inference gateway OpenAI-compatible URL for a model entity."""
        ...


class _ProvidersResource(Protocol):
    """Inference providers SDK surface used by host_url resolution."""

    def retrieve(self, name: str, *, workspace: str) -> object | Awaitable[object]:
        """Retrieve a model provider by name and workspace."""
        ...


class _InferenceResource(Protocol):
    """Inference SDK surface used by host_url resolution."""

    providers: _ProvidersResource


class _PlatformSDK(Protocol):
    """Minimal platform SDK surface used by this resolver."""

    models: _ModelsResource
    inference: _InferenceResource


async def _maybe_await(value: _T | Awaitable[_T]) -> _T:
    """Await SDK calls only when using an async platform client."""
    if inspect.isawaitable(value):
        return await value
    return value


async def _resolve_provider_host_url(
    sdk: _PlatformSDK,
    model_entity: object,
) -> str | None:
    """Resolve the direct provider host URL from a model entity's first provider."""
    model_providers = getattr(model_entity, "model_providers", None)
    if not model_providers:
        return None

    provider_ref = model_providers[0]
    if not isinstance(provider_ref, str):
        return None

    parts = provider_ref.split("/", 1)
    if len(parts) != 2:
        _logger.warning("Invalid provider reference format", extra={"provider_ref": provider_ref})
        return None

    provider_workspace, provider_name = parts
    try:
        provider = await _maybe_await(sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace))
        host_url = getattr(provider, "host_url", None)
        return host_url if isinstance(host_url, str) else None
    except NotFoundError:
        _logger.warning("Provider not found during host_url resolution", extra={"provider_ref": provider_ref})
        return None
    except Exception:
        _logger.warning("Failed to resolve provider host_url", extra={"provider_ref": provider_ref}, exc_info=True)
        return None


class PlatformModelResolver:
    """Resolve SDK ModelRef values through the platform Models API and IGW."""

    def __init__(self, sdk: object) -> None:
        """Store the platform SDK used for model lookup."""
        self._sdk = cast(_PlatformSDK, sdk)

    async def resolve_model(self, model_ref: ModelRef) -> Model:
        """Resolve ``workspace/name`` to an SDK Model routed through inference gateway."""
        parts = model_ref.root.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("ModelRef must be in format 'workspace/model_name'")
        workspace, name = parts

        try:
            model_entity = await _maybe_await(self._sdk.models.retrieve(name, workspace=workspace))
        except NotFoundError as exc:
            raise ValueError(
                f"Model reference '{model_ref.root}' not found. "
                f"Ensure the model entity '{name}' exists in workspace '{workspace}', "
                "or use an inline model definition instead."
            ) from exc

        endpoint = self._sdk.models.get_model_entity_route_openai_url(model_entity)
        host_url = await _resolve_provider_host_url(self._sdk, model_entity)
        return Model(
            url=endpoint,
            name=name,
            format=ModelFormat.NVIDIA_NIM,
            host_url=host_url,
        )
