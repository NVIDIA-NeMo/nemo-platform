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
from nemo_platform.types.inference import ModelProvider as PlatformModelProvider
from nemo_platform.types.models import ModelEntity as PlatformModelEntity

_logger = logging.getLogger(__name__)
_T = TypeVar("_T")


def _parse_required_workspace_name(ref: str, *, label: str, expected_format: str = "workspace/name") -> tuple[str, str]:
    """Parse a strict workspace-qualified reference."""
    workspace, separator, name = ref.partition("/")
    if separator != "/" or not workspace or not name or "/" in name:
        raise ValueError(f"{label} must be in format '{expected_format}'")
    return workspace, name


class _ModelsResource(Protocol):
    """Models SDK surface used by platform model resolution."""

    def retrieve(self, name: str, *, workspace: str) -> PlatformModelEntity | Awaitable[PlatformModelEntity]:
        """Retrieve a model entity by name and workspace."""
        ...

    def get_model_entity_route_openai_url(self, model_entity: PlatformModelEntity) -> str:
        """Return the inference gateway OpenAI-compatible URL for a model entity."""
        ...


class _ProvidersResource(Protocol):
    """Inference providers SDK surface used by host_url resolution."""

    def retrieve(self, name: str, *, workspace: str) -> PlatformModelProvider | Awaitable[PlatformModelProvider]:
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
    model_entity: PlatformModelEntity,
) -> str | None:
    """Resolve the direct provider host URL from a model entity's first provider."""
    model_providers = model_entity.model_providers
    if not model_providers:
        return None

    provider_ref = model_providers[0]
    try:
        provider_workspace, provider_name = _parse_required_workspace_name(provider_ref, label="Provider reference")
    except ValueError:
        _logger.warning("Invalid provider reference format", extra={"provider_ref": provider_ref})
        return None

    try:
        provider = await _maybe_await(sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace))
        return provider.host_url
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
        workspace, name = _parse_required_workspace_name(
            model_ref.root, label="ModelRef", expected_format="workspace/model_name"
        )

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
