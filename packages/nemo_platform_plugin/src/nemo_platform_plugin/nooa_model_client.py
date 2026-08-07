# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run-scoped Nooa clients backed by configured Platform Model Entities.

This module is an optional integration: consumers must depend on ``nooa``.
Keeping the integration here lets plugins share Platform config, routing, auth,
and client lifetime behavior without making Nooa a required dependency of the
public plugin contract.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from litellm import get_model_info
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.config import get_context
from nemo_platform.types.inference import ModelProvider
from nemo_platform.types.models import ModelEntity
from nooa.unifiedllm import CompletionClient

_PLACEHOLDER_API_KEY = "not-needed"
_OPENAI_FORMAT = "OPENAI_CHAT"
_ANTHROPIC_FORMAT = "ANTHROPIC_MESSAGES"
_OPENAI_CHAT_REASONING_EFFORT = "none"
_ACCEPT_ENCODING_HEADER = "accept-encoding"
_IDENTITY_ENCODING = "identity"


def _openai_chat_reasoning_effort(model: str) -> str | None:
    """Disable reasoning unless LiteLLM explicitly says this value is unsupported."""
    try:
        model_info = get_model_info(model)
    except Exception as exc:
        # Custom provider registrations need not appear in LiteLLM's model map.
        # Preserve the value that makes frontier Chat Completions tool calls work.
        if "This model isn't mapped yet" not in str(exc):
            raise
        return _OPENAI_CHAT_REASONING_EFFORT
    if model_info.get("supports_none_reasoning_effort") is False:
        return None
    return _OPENAI_CHAT_REASONING_EFFORT


@dataclass(frozen=True)
class ConfiguredModelRefs:
    """Workspace-qualified Model Entity IDs for default and fast agent work."""

    default: str
    fast: str


@dataclass(frozen=True)
class ConfiguredModelClients:
    """Resolved Nooa clients for default and low-latency agent work."""

    default: CompletionClient
    fast: CompletionClient
    refs: ConfiguredModelRefs | None = None

    async def aclose(self) -> None:
        """Close each distinct client owned by this pair."""
        await self.default.aclose()
        if self.fast is not self.default:
            await self.fast.aclose()


_ACTIVE_MODEL_CLIENTS: ContextVar[ConfiguredModelClients | None] = ContextVar(
    "nemo_platform_active_model_clients",
    default=None,
)


def configured_model_refs() -> ConfiguredModelRefs:
    """Read the default/fast Model Entity pair from the active CLI context."""
    context = get_context()
    default = context.default_model
    fast = context.fast_model or default
    if not default:
        raise ValueError("No default model is configured. Run `nemo setup` and select agent models.")
    if not fast:
        raise ValueError("No fast model is configured. Run `nemo setup` and select agent models.")
    return ConfiguredModelRefs(default=default, fast=fast)


def _parse_model_ref(model_ref: str) -> tuple[str, str]:
    workspace, separator, name = model_ref.partition("/")
    if separator != "/" or not workspace or not name:
        raise ValueError(f"Model reference {model_ref!r} must use workspace/name format")
    return workspace, name


def _completion_client(
    client: AsyncNeMoPlatform,
    model_entity: ModelEntity,
    served_model_name: str,
) -> CompletionClient:
    """Build a Nooa client that routes through the Model Entity's Platform URL."""
    api_base = client.models.get_model_entity_route_openai_url(model_entity)
    extra_headers = dict(client.models.get_client_default_headers())
    # Inference Gateway's direct passthrough session preserves compressed
    # response bytes. Nooa needs decoded JSON/SSE, so make that requirement
    # explicit at this adapter boundary for every configured agent client.
    extra_headers[_ACCEPT_ENCODING_HEADER] = _IDENTITY_ENCODING
    if model_entity.backend_format == _OPENAI_FORMAT:
        litellm_model = f"openai/{served_model_name}"
        return CompletionClient(
            litellm_model,
            api_base=api_base,
            api_key=_PLACEHOLDER_API_KEY,
            # Platform rewrites the response model to the Model Entity ID. Keep
            # the provider's authoritative served name available to LiteLLM for
            # post-response capability and cost lookup.
            base_model=litellm_model,
            extra_headers=extra_headers,
            drop_params=True,
            # The configured backend contract is explicitly OPENAI_CHAT. Newer
            # LiteLLM versions otherwise bridge GPT-5.4+ tool calls with any
            # reasoning_effort value (including "none") to /responses.
            _skip_responses_api_bridge=True,
            # Chat Completions tool calls on current OpenAI frontier models
            # require reasoning to be disabled. Use LiteLLM's capability map to
            # omit that value only when the served model explicitly rejects it.
            reasoning_effort=_openai_chat_reasoning_effort(litellm_model),
        )
    elif model_entity.backend_format == _ANTHROPIC_FORMAT:
        api_base = api_base.removesuffix("/v1")
    else:
        raise ValueError(
            f"Model '{model_entity.workspace}/{model_entity.name}' has unsupported backend format "
            f"{model_entity.backend_format!r}; expected {_OPENAI_FORMAT} or {_ANTHROPIC_FORMAT}"
        )

    litellm_model = f"anthropic/{served_model_name}"
    return CompletionClient(
        litellm_model,
        api_base=api_base,
        api_key=_PLACEHOLDER_API_KEY,
        base_model=litellm_model,
        extra_headers=extra_headers,
        drop_params=True,
    )


async def _served_model_name(
    client: AsyncNeMoPlatform,
    model_entity: ModelEntity,
    provider_cache: dict[str, ModelProvider],
) -> str:
    """Return the provider-recorded model name, without inferring from the entity ID."""
    entity_ref = f"{model_entity.workspace}/{model_entity.name}"
    for provider_ref in model_entity.model_providers or ():
        provider = provider_cache.get(provider_ref)
        if provider is None:
            workspace, name = _parse_model_ref(provider_ref)
            provider = await client.inference.providers.retrieve(name, workspace=workspace)
            provider_cache[provider_ref] = provider
        for mapping in provider.served_models or ():
            if mapping.model_entity_id == entity_ref:
                return mapping.served_model_name

    if model_entity.api_endpoint is not None and model_entity.api_endpoint.model_id:
        return model_entity.api_endpoint.model_id
    return model_entity.name


async def resolve_model_clients(
    client: AsyncNeMoPlatform,
    refs: ConfiguredModelRefs | None = None,
) -> ConfiguredModelClients:
    """Resolve configured Model Entities and construct each distinct client once."""
    selected = refs or configured_model_refs()
    resolved: dict[str, CompletionClient] = {}
    provider_cache: dict[str, ModelProvider] = {}
    for model_ref in (selected.default, selected.fast):
        if model_ref in resolved:
            continue
        workspace, name = _parse_model_ref(model_ref)
        entity = await client.models.retrieve(name, workspace=workspace)
        served_model_name = await _served_model_name(client, entity, provider_cache)
        resolved[model_ref] = _completion_client(client, entity, served_model_name)
    return ConfiguredModelClients(
        default=resolved[selected.default],
        fast=resolved[selected.fast],
        refs=selected,
    )


@contextmanager
def activate_model_clients(model_clients: ConfiguredModelClients) -> Iterator[None]:
    """Expose a resolved pair to agents constructed within this run context."""
    token = _ACTIVE_MODEL_CLIENTS.set(model_clients)
    try:
        yield
    finally:
        _ACTIVE_MODEL_CLIENTS.reset(token)


def _active_model_clients() -> ConfiguredModelClients:
    model_clients = _ACTIVE_MODEL_CLIENTS.get()
    if model_clients is None:
        raise RuntimeError("Configured model clients were not activated for this agent run")
    return model_clients


def get_default_model() -> CompletionClient:
    """Return the active default model client."""
    return _active_model_clients().default


def get_fast_model() -> CompletionClient:
    """Return the active low-latency model client."""
    return _active_model_clients().fast


def get_configured_model_refs() -> ConfiguredModelRefs:
    """Return the model references resolved for the active agent run."""
    refs = _active_model_clients().refs
    if refs is None:
        raise RuntimeError("Configured model references are unavailable for this agent run")
    return refs
