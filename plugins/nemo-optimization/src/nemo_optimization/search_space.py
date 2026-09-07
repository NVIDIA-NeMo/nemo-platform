# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared Fabric search-space parsing for optimizer phases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nemo_optimization.config_overlay import get_by_dotted_path

SUPPORTED_PARAM_TYPES = frozenset({"fabric"})
DEFAULT_PARAM_TYPE = "fabric"
DEFAULT_PROMPT_BACKEND = "ga"


class SearchSpaceError(ValueError):
    """Raised when a search-space entry is invalid."""


@dataclass(frozen=True)
class NumericSearchSpaceSpec:
    """One non-prompt Fabric search-space dimension."""

    path: str
    param_type: str = DEFAULT_PARAM_TYPE
    values: tuple[Any, ...] | None = None
    low: int | float | None = None
    high: int | float | None = None
    log: bool = False
    step: int | float | None = None

    @classmethod
    def from_mapping(cls, name: str, spec: Mapping[str, Any]) -> NumericSearchSpaceSpec:
        param_type, path = _common_entry_fields(name, spec)
        values = spec.get("values")
        if values is not None:
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                raise SearchSpaceError("'values' must be a non-string sequence.")
            if not values:
                raise SearchSpaceError("'values' must not be empty.")
            if spec.get("low") is not None or spec.get("high") is not None:
                raise SearchSpaceError("'values' is mutually exclusive with 'low' and 'high'.")
            return cls(path=path, param_type=param_type, values=tuple(values))

        low = spec.get("low")
        high = spec.get("high")
        if (low is None) != (high is None):
            raise SearchSpaceError("Range search spaces require both 'low' and 'high'.")
        if low is None or high is None:
            raise SearchSpaceError("Search space entry must define either 'values' or both 'low' and 'high'.")
        if (
            isinstance(low, bool)
            or isinstance(high, bool)
            or not isinstance(low, (int, float))
            or not isinstance(high, (int, float))
        ):
            raise SearchSpaceError(f"'low' and 'high' must be numbers; got low={low!r}, high={high!r}.")
        if low >= high:
            raise SearchSpaceError(f"'low' must be less than 'high'; got low={low}, high={high}.")

        return cls(
            path=path,
            param_type=param_type,
            low=low,
            high=high,
            log=bool(spec.get("log", False)),
            step=spec.get("step"),
        )


@dataclass(frozen=True)
class PromptSearchSpaceSpec:
    """One prompt Fabric search-space dimension."""

    path: str
    purpose: str
    param_type: str = DEFAULT_PARAM_TYPE
    format: str | None = None

    @classmethod
    def from_mapping(cls, name: str, spec: Mapping[str, Any]) -> PromptSearchSpaceSpec:
        param_type, path = _common_entry_fields(name, spec)
        unsupported = sorted(key for key in ("values", "low", "high", "log", "step") if key in spec)
        if unsupported:
            raise SearchSpaceError(
                f"Prompt search-space entry {name!r} must not define numeric search keys: {unsupported}."
            )

        purpose = spec.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            raise SearchSpaceError(f"Prompt search-space entry {name!r} requires non-empty 'purpose'.")

        raw_format = spec.get("format")
        if raw_format is not None and (not isinstance(raw_format, str) or not raw_format.strip()):
            raise SearchSpaceError(f"Prompt search-space entry {name!r} has malformed 'format'.")

        return cls(
            path=path,
            purpose=purpose.strip(),
            param_type=param_type,
            format=raw_format.strip() if isinstance(raw_format, str) else None,
        )


SearchSpaceSpec = NumericSearchSpaceSpec | PromptSearchSpaceSpec


@dataclass(frozen=True)
class PromptOptimizerConfig:
    """Validated prompt-optimizer configuration from a Fabric optimize payload."""

    backend: str
    model: str
    search_space: dict[str, PromptSearchSpaceSpec]


def parse_all_search_space(optimizer: Mapping[str, Any]) -> dict[str, SearchSpaceSpec]:
    """Parse ``optimizer.search_space`` (with legacy ``optimizable_params`` shim)."""
    raw = optimizer.get("search_space")
    if raw is None:
        raw = optimizer.get("optimizable_params")
    if not isinstance(raw, Mapping):
        raise SearchSpaceError("optimizer.search_space must be a mapping of param names to typed specs.")

    space: dict[str, SearchSpaceSpec] = {}
    for name, spec in raw.items():
        if not isinstance(name, str):
            raise SearchSpaceError("Search-space keys must be strings (logical param names).")
        if not isinstance(spec, Mapping):
            raise SearchSpaceError(f"Search space entry {name!r} must be a mapping.")
        space[name] = parse_search_space_entry(name, spec)
    if not space:
        raise SearchSpaceError("optimizer.search_space must declare at least one dimension.")
    return space


def parse_search_space_entry(name: str, spec: Mapping[str, Any]) -> SearchSpaceSpec:
    """Parse one shared search-space entry."""

    if _is_prompt_dimension(name, spec):
        return PromptSearchSpaceSpec.from_mapping(name, spec)
    return NumericSearchSpaceSpec.from_mapping(name, spec)


def parse_numeric_search_space(optimizer: Mapping[str, Any]) -> dict[str, NumericSearchSpaceSpec]:
    """Parse numeric dimensions from ``optimizer.search_space``."""

    space = {
        name: spec
        for name, spec in parse_all_search_space(optimizer).items()
        if isinstance(spec, NumericSearchSpaceSpec)
    }
    if not space:
        raise SearchSpaceError("optimizer.search_space must declare at least one non-prompt dimension.")
    return space


def parse_prompt_search_space(
    optimizer: Mapping[str, Any],
    *,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, PromptSearchSpaceSpec]:
    """Parse prompt dimensions from ``optimizer.search_space``."""

    space = {
        name: spec
        for name, spec in parse_all_search_space(optimizer).items()
        if isinstance(spec, PromptSearchSpaceSpec)
    }
    if not space:
        raise SearchSpaceError("optimizer.search_space must declare at least one prompt dimension.")
    if payload is not None:
        validate_prompt_search_space_payload(payload, space)
    return space


def parse_prompt_optimizer_config(payload: Mapping[str, Any]) -> PromptOptimizerConfig:
    """Validate ``optimizer.prompt`` against the shared Fabric payload."""

    optimizer = payload.get("optimizer")
    if not isinstance(optimizer, Mapping):
        raise SearchSpaceError("payload.optimizer must be a mapping.")
    prompt = optimizer.get("prompt")
    if not isinstance(prompt, Mapping):
        raise SearchSpaceError("optimizer.prompt must be a mapping.")
    enabled = prompt.get("enabled")
    if not isinstance(enabled, bool):
        raise SearchSpaceError("optimizer.prompt.enabled must be a boolean.")
    if not enabled:
        raise SearchSpaceError("optimizer.prompt.enabled must be true.")

    backend = prompt.get("backend", DEFAULT_PROMPT_BACKEND)
    if not isinstance(backend, str) or not backend.strip():
        raise SearchSpaceError("optimizer.prompt.backend must be a non-empty backend name.")
    backend = backend.strip()

    model = prompt.get("model")
    if not isinstance(model, str) or not model.strip():
        raise SearchSpaceError("optimizer.prompt.model must reference a model declared under payload.models.")
    model = model.strip()

    models = payload.get("models")
    if not isinstance(models, Mapping) or not isinstance(models.get(model), Mapping):
        raise SearchSpaceError(f"optimizer.prompt.model references unknown payload model {model!r}.")

    return PromptOptimizerConfig(
        backend=backend,
        model=model,
        search_space=parse_prompt_search_space(optimizer, payload=payload),
    )


def validate_prompt_search_space_payload(
    payload: Mapping[str, Any],
    search_space: Mapping[str, PromptSearchSpaceSpec],
) -> None:
    """Ensure each prompt path resolves to the initial prompt string."""

    for name, spec in search_space.items():
        try:
            initial_prompt = get_by_dotted_path(payload, spec.path)
        except KeyError as exc:
            raise SearchSpaceError(
                f"Prompt search-space entry {name!r} path {spec.path!r} does not resolve in the Fabric payload."
            ) from exc
        if not isinstance(initial_prompt, str):
            raise SearchSpaceError(
                f"Prompt search-space entry {name!r} path {spec.path!r} must resolve to a string "
                f"(got {type(initial_prompt).__name__})."
            )


def suggestions_by_path(
    search_space: Mapping[str, SearchSpaceSpec],
    suggestions: Mapping[str, Any],
) -> dict[str, Any]:
    """Map logical suggestions onto applicator ``path`` keys."""
    by_path: dict[str, Any] = {}
    for name, value in suggestions.items():
        spec = search_space.get(name)
        if spec is None:
            raise SearchSpaceError(f"Suggestion {name!r} is not in the parsed search space.")
        if spec.path in by_path:
            raise SearchSpaceError(
                f"Search-space paths collide at {spec.path!r} "
                f"(params {[n for n, s in search_space.items() if s.path == spec.path]})."
            )
        by_path[spec.path] = value
    return by_path


def _is_prompt_dimension(name: str, spec: Mapping[str, Any]) -> bool:
    raw = spec.get("is_prompt", False)
    if not isinstance(raw, bool):
        raise SearchSpaceError(f"Search space entry {name!r} field 'is_prompt' must be a boolean.")
    return raw


def _common_entry_fields(name: str, spec: Mapping[str, Any]) -> tuple[str, str]:
    param_type = spec.get("type", DEFAULT_PARAM_TYPE)
    if not isinstance(param_type, str):
        raise SearchSpaceError(f"Search space entry {name!r} field 'type' must be a string.")
    param_type = param_type.strip().lower()
    if param_type not in SUPPORTED_PARAM_TYPES:
        supported = ", ".join(sorted(SUPPORTED_PARAM_TYPES))
        raise SearchSpaceError(
            f"Search space entry {name!r} has unsupported type {param_type!r}; supported types: {supported}."
        )

    path = spec.get("path")
    if not isinstance(path, str) or not path.strip():
        raise SearchSpaceError(f"Search space entry {name!r} requires 'path' (Fabric overlay dotted path).")
    return param_type, path.strip()
