# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run-scoped Platform model resolution for the Insights Analyst."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from nemo_platform import AsyncNeMoPlatform
from nemo_platform.config import get_context
from nemo_platform.types.models import ModelEntity
from nooa.unifiedllm import CompletionClient

_PLACEHOLDER_API_KEY = "not-needed"
_OPENAI_FORMAT = "OPENAI_CHAT"
_ANTHROPIC_FORMAT = "ANTHROPIC_MESSAGES"


@dataclass(frozen=True)
class AnalystModelRefs:
    """Workspace-qualified Model Entity IDs selected for an Analyst run."""

    smart: str
    fast: str


@dataclass(frozen=True)
class AnalystModelPair:
    """Resolved Nooa clients for quality-critical and low-latency work."""

    smart: CompletionClient
    fast: CompletionClient

    async def aclose(self) -> None:
        """Close each distinct Nooa client owned by the pair."""
        await self.smart.aclose()
        if self.fast is not self.smart:
            await self.fast.aclose()


_ACTIVE_MODEL_PAIR: ContextVar[AnalystModelPair | None] = ContextVar(
    "nemo_insights_analyst_model_pair",
    default=None,
)


def configured_model_refs() -> AnalystModelRefs:
    """Read the smart/fast pair from the active Platform CLI context."""
    context = get_context()
    smart = context.smart_model or context.default_model
    fast = context.fast_model or context.default_model
    if not smart or not fast:
        raise ValueError("No smart/fast models are configured. Run `nemo setup` and select both agent models.")
    return AnalystModelRefs(smart=smart, fast=fast)


def _parse_model_ref(model_ref: str) -> tuple[str, str]:
    workspace, separator, name = model_ref.partition("/")
    if separator != "/" or not workspace or not name:
        raise ValueError(f"Model reference {model_ref!r} must use workspace/name format")
    return workspace, name


def _backend_format(model_entity: ModelEntity) -> str:
    backend_format = model_entity.backend_format
    if backend_format in {_OPENAI_FORMAT, _ANTHROPIC_FORMAT}:
        return backend_format
    raise ValueError(
        f"Model '{model_entity.workspace}/{model_entity.name}' has unsupported backend format "
        f"{backend_format!r}; expected {_OPENAI_FORMAT} or {_ANTHROPIC_FORMAT}"
    )


def _completion_client(
    client: AsyncNeMoPlatform,
    model_entity: ModelEntity,
) -> CompletionClient:
    """Build a Nooa client using existing Model Entity routing and SDK headers."""
    backend_format = _backend_format(model_entity)
    api_base = client.models.get_model_entity_route_openai_url(model_entity)
    provider = "openai"
    if backend_format == _ANTHROPIC_FORMAT:
        provider = "anthropic"
        api_base = api_base.removesuffix("/v1")

    return CompletionClient(
        f"{provider}/{model_entity.name}",
        api_base=api_base,
        api_key=_PLACEHOLDER_API_KEY,
        extra_headers=client.models.get_client_default_headers(),
    )


async def resolve_model_pair(
    client: AsyncNeMoPlatform,
    refs: AnalystModelRefs | None = None,
) -> AnalystModelPair:
    """Resolve configured Model Entities and construct their Nooa clients once."""
    selected = refs or configured_model_refs()
    resolved: dict[str, CompletionClient] = {}
    for model_ref in (selected.smart, selected.fast):
        if model_ref in resolved:
            continue
        workspace, name = _parse_model_ref(model_ref)
        entity = await client.models.retrieve(name, workspace=workspace)
        resolved[model_ref] = _completion_client(client, entity)
    return AnalystModelPair(smart=resolved[selected.smart], fast=resolved[selected.fast])


@contextmanager
def activate_model_pair(model_pair: AnalystModelPair) -> Iterator[None]:
    """Make a resolved pair available to nested Analyst constructors for this run."""
    token = _ACTIVE_MODEL_PAIR.set(model_pair)
    try:
        yield
    finally:
        _ACTIVE_MODEL_PAIR.reset(token)


def _active_model_pair() -> AnalystModelPair:
    model_pair = _ACTIVE_MODEL_PAIR.get()
    if model_pair is None:
        raise RuntimeError("Analyst model pair was not activated for this run")
    return model_pair


def get_smart_model() -> CompletionClient:
    """Return the active high-capability Analyst model."""
    return _active_model_pair().smart


def get_fast_model() -> CompletionClient:
    """Return the active low-latency Analyst model."""
    return _active_model_pair().fast
