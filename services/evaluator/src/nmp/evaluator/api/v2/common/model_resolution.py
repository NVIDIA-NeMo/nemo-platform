# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Protocol and utilities for resolving ModelRef to Model in the API layer.

Resolution happens at the API layer before data is passed to the app layer,
ensuring the app layer only works with Model instances.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, cast, runtime_checkable
from urllib.parse import urlparse

from nemo_evaluator_sdk.enums import ModelFormat
from nemo_evaluator_sdk.values import Model as SDKModel
from nemo_platform import AsyncNeMoPlatform, NotFoundError
from nmp.common.config import get_platform_config
from nmp.common.config.base import LOOPBACK_ADDRESSES
from nmp.common.sdk_factory import get_async_platform_sdk
from nmp.evaluator.api.v2.common.inline_models import Model
from nmp.evaluator.app.values.common import ModelRef

_logger = logging.getLogger(__name__)

# =============================================================================
# Model Union Type and Resolution
# =============================================================================


async def _resolve_provider_host_url(
    sdk: AsyncNeMoPlatform,
    model_entity: object,
) -> str | None:
    """Resolve the direct NIM host URL from a model entity's first provider.

    Returns the provider's host_url (e.g., http://nim-host:8080) or None if
    the model has no providers or the lookup fails.
    """
    model_providers = getattr(model_entity, "model_providers", None)
    if not model_providers:
        return None

    provider_ref = model_providers[0]
    parts = provider_ref.split("/", 1)
    if len(parts) != 2:
        _logger.warning("Invalid provider reference format", extra={"provider_ref": provider_ref})
        return None

    provider_workspace, provider_name = parts
    try:
        provider = await sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)
        _logger.debug(
            "Resolved provider host_url",
            extra={"provider_ref": provider_ref, "host_url": provider.host_url},
        )
        return provider.host_url
    except NotFoundError:
        _logger.warning("Provider not found during host_url resolution", extra={"provider_ref": provider_ref})
        return None
    except Exception:
        _logger.warning("Failed to resolve provider host_url", extra={"provider_ref": provider_ref}, exc_info=True)
        return None


async def resolve_model(
    model: SDKModel | ModelRef,
    sdk: AsyncNeMoPlatform | None = None,
) -> Model:
    """Resolve a Model or ModelRef to an Model.

    This function should only be called from the API layer.
    The app layer should receive pre-resolved Model instances.

    If the model is already an Model, it is returned unchanged.
    If the model is a ModelRef, queries the Models API to validate the model exists
    and builds the Inference Gateway model entity route URL.

    Args:
        model: An Model or ModelRef (workspace/model_name).
        sdk: Optional SDK instance for testing. If None, uses get_async_platform_sdk().

    Returns:
        Model instance with url set to the appropriate Inference Gateway URL.

    Raises:
        ValueError: If ModelRef format is invalid or points to a non-existent entity.
        TypeError: If model is an unsupported type.
    """
    if isinstance(model, Model):
        return model

    if isinstance(model, SDKModel):
        return Model.model_validate(model)

    if sdk is None:
        sdk = get_async_platform_sdk()

    if isinstance(model, ModelRef):
        parts = model.root.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("ModelRef must be in format 'workspace/model_name'")
        workspace, name = parts

        _logger.debug("Resolving ModelRef to Model", extra={"model_ref": model.root})

        # Fetch model entity to validate it exists
        try:
            model_entity = await sdk.models.retrieve(name, workspace=workspace)
        except NotFoundError as e:
            raise ValueError(
                f"Model reference '{model.root}' not found. "
                f"Ensure the model entity '{name}' exists in workspace '{workspace}', "
                f"or use an inline model definition instead."
            ) from e

        # Build inference gateway model entity route URL
        # The gateway will rewrite the model field in requests to the correct served_model_name
        endpoint = sdk.models.get_model_entity_route_openai_url(model_entity)

        # Resolve the direct NIM host URL from the first model provider for
        # callers that need provider-level connectivity details.
        host_url = await _resolve_provider_host_url(sdk, model_entity)

        resolved = Model(
            url=endpoint,
            name=name,  # Gateway rewrites this to served_model_name
            format=ModelFormat.NVIDIA_NIM,  # IGW uses NIM format
            host_url=host_url,
        )
        _logger.debug(
            "Resolved ModelRef to Model",
            extra={"model_ref": model.root, "endpoint": endpoint, "host_url": host_url},
        )
        return resolved

    raise TypeError(f"Unsupported model type: {type(model)}")


# =============================================================================
# Resolution Protocol and Helpers
# =============================================================================

# Type alias for the model resolver function
ModelResolver = Callable[[SDKModel | ModelRef], Awaitable[Model]]


@runtime_checkable
class ResolvableModels(Protocol):
    """Protocol for API types that have model fields needing resolution.

    Types implementing this protocol have fields typed as Model (Model | ModelRef)
    that need to be resolved to Model before passing to the app layer.

    Note: Do not inherit from this protocol directly (causes Pydantic metaclass conflict).
    Instead, use the _With* mixins which implement this protocol via structural typing.
    """

    async def resolve_models(self, resolver: ModelResolver) -> dict[str, Model]:
        """Resolve all Model fields to Model.

        Args:
            resolver: Function that resolves ModelRef to Model.

        Returns:
            Dict mapping field names to resolved Model instances.
        """
        ...


async def resolve_model_field(value: SDKModel | ModelRef | None, resolver: ModelResolver) -> Model | None:
    """Helper to resolve a single Model field to Model.

    Args:
        value: The field value (Model, ModelRef, or None).
        resolver: Function that resolves ModelRef to Model.

    Returns:
        The resolved Model, or None if value was None.
    """
    if value is None:
        return None
    # resolver handles both Model (returns unchanged) and ModelRef (resolves)
    return await resolver(value)


# =============================================================================
# Params Resolution
# =============================================================================

# Known param names that contain a nested `model` field needing resolution.
_MODEL_PARAM_KEYS = ("judge", "judge_embeddings")


async def resolve_params_model_refs(params: dict) -> dict:
    """Resolve any ModelRef values in a params dict to Model.

    Scans known param keys for nested `model` fields that are string references.

    Args:
        params: The metric_params dict from job input.

    Returns:
        A new dict with all model references resolved to Model.
    """
    params = dict(params)  # shallow copy

    for key in _MODEL_PARAM_KEYS:
        if key in params and params[key] and "model" in params[key]:
            model_value = params[key]["model"]
            # String values are ModelRef references that need resolution
            if isinstance(model_value, str):
                _logger.debug("Resolving ModelRef in params", extra={"param_key": key, "model_ref": model_value})
                params[key] = dict(params[key])  # shallow copy nested dict
                params[key]["model"] = (await resolve_model(ModelRef(model_value))).model_dump()

    return params


def _rebase_loopback_url(url: str, target_base_url: str | None) -> str:
    """Rewrite loopback-host URLs to use the target base URL's network location."""
    if not target_base_url:
        return url

    parsed_url = urlparse(url)
    if parsed_url.hostname not in LOOPBACK_ADDRESSES:
        return url

    parsed_target = urlparse(target_base_url)
    if not parsed_target.scheme or not parsed_target.hostname:
        return url

    return parsed_url._replace(
        scheme=parsed_target.scheme,
        netloc=parsed_target.netloc,
    ).geturl()


def rewrite_models_for_job_container(payload: dict, target_base_url: str | None = None) -> dict:
    """Rewrite resolved model URLs in a job payload for container execution.

    Jobs receive a container-reachable NMP_BASE_URL that may differ from the service's
    own network view. This helper rebases any loopback-host model URLs in the compiled
    payload onto that container-facing base URL while preserving the original path.
    """
    if target_base_url is None:
        target_base_url = get_platform_config().to_shared_envvars().get("NMP_BASE_URL")

    def _rewrite(value: object) -> object:
        if isinstance(value, dict):
            rewritten = {key: _rewrite(item) for key, item in value.items()}
            url = rewritten.get("url")
            name = rewritten.get("name")
            if isinstance(url, str) and isinstance(name, str):
                rewritten["url"] = _rebase_loopback_url(url, target_base_url)
                host_url = rewritten.get("host_url")
                if isinstance(host_url, str):
                    rewritten["host_url"] = _rebase_loopback_url(host_url, target_base_url)
            return rewritten
        if isinstance(value, list):
            return [_rewrite(item) for item in value]
        return value

    return cast(dict, _rewrite(payload))


__all__ = [
    "ModelResolver",
    "ResolvableModels",
    "resolve_model_field",
    "resolve_model",
    "resolve_params_model_refs",
    "rewrite_models_for_job_container",
]
