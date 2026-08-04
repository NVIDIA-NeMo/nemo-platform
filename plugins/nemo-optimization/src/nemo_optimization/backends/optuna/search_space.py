# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""YAML search-space specs → Optuna ``trial.suggest_*`` dispatch.

Ported from https://github.com/NVIDIA/NeMo-Agent-Toolkit/blob/main/packages/nvidia_nat_core/src/nat/data_models/optimizable.py

Search-space entries are logical Optuna param names with an applicator ``type``
and a target ``path``. Today only ``type: fabric`` is supported (profile-overlay
paths such as ``models.default.temperature``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import numpy as np

SUPPORTED_PARAM_TYPES = frozenset({"fabric"})
DEFAULT_PARAM_TYPE = "fabric"


class _TrialLike(Protocol):
    def suggest_categorical(self, name: str, choices: Sequence[Any]) -> Any: ...

    def suggest_int(
        self,
        name: str,
        low: int,
        high: int,
        *,
        log: bool = False,
        step: int | None = None,
    ) -> int: ...

    def suggest_float(
        self,
        name: str,
        low: float,
        high: float,
        *,
        log: bool = False,
        step: float | None = None,
    ) -> float: ...


class SearchSpaceError(ValueError):
    """Raised when a search-space entry is invalid."""


@dataclass(frozen=True)
class SearchSpaceSpec:
    """One hyperparameter dimension parsed from ``optimizer.search_space``."""

    path: str
    param_type: str = DEFAULT_PARAM_TYPE
    values: tuple[Any, ...] | None = None
    low: int | float | None = None
    high: int | float | None = None
    log: bool = False
    step: int | float | None = None
    is_prompt: bool = False

    @classmethod
    def from_mapping(cls, name: str, spec: Mapping[str, Any]) -> SearchSpaceSpec:
        if spec.get("is_prompt"):
            return cls(path=name, is_prompt=True)

        param_type = str(spec.get("type") or DEFAULT_PARAM_TYPE).strip().lower()
        if param_type not in SUPPORTED_PARAM_TYPES:
            supported = ", ".join(sorted(SUPPORTED_PARAM_TYPES))
            raise SearchSpaceError(
                f"Search space entry {name!r} has unsupported type {param_type!r}; "
                f"supported types: {supported}."
            )

        path = spec.get("path")
        if path is None or not str(path).strip():
            raise SearchSpaceError(
                f"Search space entry {name!r} requires 'path' (Fabric overlay dotted path)."
            )
        path = str(path).strip()

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
            raise SearchSpaceError(
                "Search space entry must define either 'values' or both 'low' and 'high'."
            )
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

    def suggest(self, trial: _TrialLike, name: str) -> Any:
        if self.is_prompt:
            raise SearchSpaceError(
                "Prompt search-space entries are not supported by the Optuna backend."
            )
        if self.values is not None:
            return trial.suggest_categorical(name, list(self.values))
        if isinstance(self.low, int) and isinstance(self.high, int):
            step = int(self.step) if self.step is not None else None
            return trial.suggest_int(name, self.low, self.high, log=self.log, step=step)
        return trial.suggest_float(
            name,
            float(cast(float, self.low)),
            float(cast(float, self.high)),
            log=self.log,
            step=float(self.step) if self.step is not None else None,
        )

    def to_grid_values(self) -> list[Any]:
        if self.is_prompt:
            raise SearchSpaceError("Prompt dimensions cannot be used with grid search.")
        if self.values is not None:
            return list(self.values)
        if self.low is None or self.high is None:
            raise SearchSpaceError("Grid search requires 'values' or both 'low' and 'high'.")
        if self.step is None:
            raise SearchSpaceError(
                f"Grid search with range (low={self.low}, high={self.high}) requires 'step'."
            )

        step_float = float(self.step)
        if step_float <= 0:
            raise SearchSpaceError(f"Grid search 'step' must be positive; got {self.step}.")

        if isinstance(self.low, int) and isinstance(self.high, int) and step_float.is_integer():
            if self.log:
                raise SearchSpaceError("Log scale is not supported for integer grid ranges.")
            step = int(step_float)
            values = list(range(self.low, self.high + 1, step))
            if values and values[-1] != self.high:
                values.append(self.high)
            return values

        if self.log:
            raise SearchSpaceError("Log scale is not supported for float grid ranges; use explicit 'values'.")

        low_val = float(self.low)
        high_val = float(self.high)
        values = np.arange(low_val, high_val, step_float).tolist()
        if not values or abs(values[-1] - high_val) > 1e-9:
            values.append(high_val)
        return [round(v, 12) for v in values]


def parse_search_space(optimizer: Mapping[str, Any]) -> dict[str, SearchSpaceSpec]:
    """Parse ``optimizer.search_space`` (with legacy ``optimizable_params`` shim)."""
    raw = optimizer.get("search_space")
    if raw is None:
        raw = optimizer.get("optimizable_params")
    if not isinstance(raw, Mapping):
        raise SearchSpaceError(
            "optimizer.search_space must be a mapping of param names to typed specs."
        )

    space: dict[str, SearchSpaceSpec] = {}
    for name, spec in raw.items():
        if not isinstance(name, str):
            raise SearchSpaceError("Search-space keys must be strings (logical param names).")
        if not isinstance(spec, Mapping):
            raise SearchSpaceError(f"Search space entry {name!r} must be a mapping.")
        parsed = SearchSpaceSpec.from_mapping(name, spec)
        if parsed.is_prompt:
            raise SearchSpaceError(
                f"Search space entry {name!r} is prompt-only; enable optimizer.prompt for GA."
            )
        space[name] = parsed
    if not space:
        raise SearchSpaceError("optimizer.search_space must declare at least one dimension.")
    return space


def suggestions_by_path(
    search_space: Mapping[str, SearchSpaceSpec],
    suggestions: Mapping[str, Any],
) -> dict[str, Any]:
    """Map logical Optuna suggestions onto applicator ``path`` keys."""
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


def grid_trial_count(space: Mapping[str, SearchSpaceSpec]) -> int:
    """Cartesian product size for an exhaustive grid study."""
    count = 1
    for spec in space.values():
        count *= len(spec.to_grid_values())
    return count
