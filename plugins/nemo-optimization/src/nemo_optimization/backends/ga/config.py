# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration parsing for prompt GA optimization."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from nemo_optimization.search_space import PromptSearchSpaceSpec, SearchSpaceError, parse_prompt_optimizer_config

DEFAULT_POPULATION_SIZE = 10
DEFAULT_GENERATIONS = 5
DEFAULT_CROSSOVER_RATE = 0.7
DEFAULT_MUTATION_RATE = 0.1
DEFAULT_SELECTION_METHOD = "tournament"
DEFAULT_TOURNAMENT_SIZE = 3
DEFAULT_PARALLEL_EVALUATIONS = 8
DEFAULT_MULTI_OBJECTIVE_MODE = "harmonic"
DEFAULT_ORACLE_FEEDBACK_MODE = "never"
DEFAULT_ORACLE_FEEDBACK_WORST_N = 5
DEFAULT_ORACLE_FEEDBACK_MAX_CHARS = 4000
DEFAULT_ORACLE_FEEDBACK_FITNESS_THRESHOLD = 0.3
DEFAULT_ORACLE_FEEDBACK_STAGNATION_GENERATIONS = 3
DEFAULT_ORACLE_FEEDBACK_VARIANCE_THRESHOLD = 0.01
DEFAULT_ORACLE_FEEDBACK_DIVERSITY_THRESHOLD = 0.5

SELECTION_METHODS = frozenset({"tournament", "roulette"})
MULTI_OBJECTIVE_MODES = frozenset({"harmonic", "weighted_sum", "chebyshev"})
ORACLE_FEEDBACK_MODES = frozenset({"never", "always", "failing_only", "adaptive"})


class GaConfigError(ValueError):
    """Raised when prompt GA configuration is invalid."""


class MetricDirection(str, Enum):
    """Optimization direction for one metric."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class MetricSpec:
    """One metric objective consumed by the GA fitness reducer."""

    name: str
    direction: MetricDirection
    weight: float = 1.0


@dataclass(frozen=True)
class GaPromptOptimizerConfig:
    """Validated prompt GA optimizer settings."""

    backend: str
    model: str
    search_space: dict[str, PromptSearchSpaceSpec]
    metrics: tuple[MetricSpec, ...]
    population_size: int
    generations: int
    crossover_rate: float
    mutation_rate: float
    elitism: int
    selection_method: str
    tournament_size: int
    diversity_lambda: float
    parallel_evaluations: int
    seed: int | None
    target: float | None
    multi_objective_mode: str
    reps_per_param_set: int
    oracle_feedback_mode: str
    oracle_feedback_worst_n: int
    oracle_feedback_max_chars: int
    oracle_feedback_fitness_threshold: float
    oracle_feedback_stagnation_generations: int
    oracle_feedback_fitness_variance_threshold: float
    oracle_feedback_diversity_threshold: float

    @property
    def metric_names(self) -> tuple[str, ...]:
        return tuple(metric.name for metric in self.metrics)


def parse_ga_prompt_optimizer_config(payload: Mapping[str, Any]) -> GaPromptOptimizerConfig:
    """Parse prompt GA settings from a Fabric optimize payload."""

    try:
        base = parse_prompt_optimizer_config(payload)
    except SearchSpaceError as exc:
        raise GaConfigError(str(exc)) from exc

    optimizer = payload.get("optimizer")
    if not isinstance(optimizer, Mapping):
        raise GaConfigError("payload.optimizer must be a mapping.")
    prompt = optimizer.get("prompt")
    if not isinstance(prompt, Mapping):
        raise GaConfigError("optimizer.prompt must be a mapping.")

    population_size = _positive_int(
        prompt,
        "population_size",
        "ga_population_size",
        default=DEFAULT_POPULATION_SIZE,
    )
    generations = _positive_int(prompt, "generations", "ga_generations", default=DEFAULT_GENERATIONS)
    elitism = _non_negative_int(
        prompt,
        "elitism",
        "ga_elitism",
        default=min(2, max(0, population_size - 1)),
    )
    if elitism >= population_size and population_size > 1:
        raise GaConfigError("optimizer.prompt.elitism must be less than population_size.")
    if population_size == 1 and elitism:
        raise GaConfigError("optimizer.prompt.elitism must be 0 when population_size is 1.")

    selection_method = _choice(
        prompt,
        "selection_method",
        "ga_selection_method",
        choices=SELECTION_METHODS,
        default=DEFAULT_SELECTION_METHOD,
    )
    multi_objective_mode = _choice(
        optimizer,
        "multi_objective_combination_mode",
        choices=MULTI_OBJECTIVE_MODES,
        default=DEFAULT_MULTI_OBJECTIVE_MODE,
        normalize=_normalize_mode,
    )
    oracle_feedback_mode = _choice(
        prompt,
        "oracle_feedback_mode",
        choices=ORACLE_FEEDBACK_MODES,
        default=DEFAULT_ORACLE_FEEDBACK_MODE,
        normalize=_normalize_mode,
    )

    return GaPromptOptimizerConfig(
        backend=base.backend,
        model=base.model,
        search_space=base.search_space,
        metrics=_parse_metrics(optimizer),
        population_size=population_size,
        generations=generations,
        crossover_rate=_rate(prompt, "crossover_rate", "ga_crossover_rate", default=DEFAULT_CROSSOVER_RATE),
        mutation_rate=_rate(prompt, "mutation_rate", "ga_mutation_rate", default=DEFAULT_MUTATION_RATE),
        elitism=elitism,
        selection_method=selection_method,
        tournament_size=_positive_int(
            prompt,
            "tournament_size",
            "ga_tournament_size",
            default=DEFAULT_TOURNAMENT_SIZE,
        ),
        diversity_lambda=_non_negative_float(prompt, "diversity_lambda", default=0.0),
        parallel_evaluations=_positive_int(
            prompt,
            "parallel_evaluations",
            "ga_parallel_evaluations",
            default=DEFAULT_PARALLEL_EVALUATIONS,
        ),
        seed=_optional_int(prompt, "seed"),
        target=_optional_float(optimizer, "target"),
        multi_objective_mode=multi_objective_mode,
        reps_per_param_set=_positive_int(optimizer, "reps_per_param_set", default=1),
        oracle_feedback_mode=oracle_feedback_mode,
        oracle_feedback_worst_n=_positive_int(
            prompt,
            "oracle_feedback_worst_n",
            default=DEFAULT_ORACLE_FEEDBACK_WORST_N,
        ),
        oracle_feedback_max_chars=_positive_int(
            prompt,
            "oracle_feedback_max_chars",
            default=DEFAULT_ORACLE_FEEDBACK_MAX_CHARS,
        ),
        oracle_feedback_fitness_threshold=_non_negative_float(
            prompt,
            "oracle_feedback_fitness_threshold",
            default=DEFAULT_ORACLE_FEEDBACK_FITNESS_THRESHOLD,
        ),
        oracle_feedback_stagnation_generations=_positive_int(
            prompt,
            "oracle_feedback_stagnation_generations",
            default=DEFAULT_ORACLE_FEEDBACK_STAGNATION_GENERATIONS,
        ),
        oracle_feedback_fitness_variance_threshold=_non_negative_float(
            prompt,
            "oracle_feedback_fitness_variance_threshold",
            default=DEFAULT_ORACLE_FEEDBACK_VARIANCE_THRESHOLD,
        ),
        oracle_feedback_diversity_threshold=_non_negative_float(
            prompt,
            "oracle_feedback_diversity_threshold",
            default=DEFAULT_ORACLE_FEEDBACK_DIVERSITY_THRESHOLD,
        ),
    )


def _parse_metrics(optimizer: Mapping[str, Any]) -> tuple[MetricSpec, ...]:
    eval_metrics = optimizer.get("eval_metrics")
    if not isinstance(eval_metrics, Mapping) or not eval_metrics:
        raise GaConfigError("optimizer.eval_metrics must declare at least one metric.")

    metrics: list[MetricSpec] = []
    for name, raw in eval_metrics.items():
        if not isinstance(name, str):
            raise GaConfigError("optimizer.eval_metrics keys must be strings.")
        if not isinstance(raw, Mapping):
            raise GaConfigError(f"optimizer.eval_metrics[{name!r}] must be a mapping.")
        direction_raw = raw.get("direction", MetricDirection.MAXIMIZE.value)
        if not isinstance(direction_raw, str):
            raise GaConfigError(f"Metric {name!r} direction must be 'maximize' or 'minimize'.")
        direction = _normalize_mode(direction_raw)
        if direction not in {MetricDirection.MAXIMIZE.value, MetricDirection.MINIMIZE.value}:
            raise GaConfigError(f"Metric {name!r} direction must be 'maximize' or 'minimize'.")
        metric_name = raw.get("evaluator_name") or name
        if not isinstance(metric_name, str) or not metric_name.strip():
            raise GaConfigError(f"Metric {name!r} evaluator_name must be a non-empty string.")
        weight = _float_value(raw.get("weight", 1.0), path=f"optimizer.eval_metrics[{name!r}].weight")
        if weight <= 0:
            raise GaConfigError(f"Metric {name!r} weight must be greater than 0.")
        metrics.append(
            MetricSpec(
                name=metric_name.strip(),
                direction=MetricDirection(direction),
                weight=weight,
            )
        )
    return tuple(metrics)


def _choice(
    mapping: Mapping[str, Any],
    *keys: str,
    choices: frozenset[str],
    default: str,
    normalize: Callable[[str], str] | None = None,
) -> str:
    value = _first_present(mapping, *keys, default=default)
    if not isinstance(value, str):
        raise GaConfigError(f"{_path(keys)} must be a string.")
    normalized = (normalize or _normalize_choice)(value)
    if normalized not in choices:
        supported = ", ".join(sorted(choices))
        raise GaConfigError(f"{_path(keys)} has unsupported value {value!r}; supported values: {supported}.")
    return normalized


def _rate(mapping: Mapping[str, Any], *keys: str, default: float) -> float:
    value = _float_value(_first_present(mapping, *keys, default=default), path=_path(keys))
    if value < 0 or value > 1:
        raise GaConfigError(f"{_path(keys)} must be between 0 and 1.")
    return value


def _positive_int(mapping: Mapping[str, Any], *keys: str, default: int) -> int:
    value = _int_value(_first_present(mapping, *keys, default=default), path=_path(keys))
    if value < 1:
        raise GaConfigError(f"{_path(keys)} must be greater than 0.")
    return value


def _non_negative_int(mapping: Mapping[str, Any], *keys: str, default: int) -> int:
    value = _int_value(_first_present(mapping, *keys, default=default), path=_path(keys))
    if value < 0:
        raise GaConfigError(f"{_path(keys)} must be greater than or equal to 0.")
    return value


def _non_negative_float(mapping: Mapping[str, Any], *keys: str, default: float) -> float:
    value = _float_value(_first_present(mapping, *keys, default=default), path=_path(keys))
    if value < 0:
        raise GaConfigError(f"{_path(keys)} must be greater than or equal to 0.")
    return value


def _optional_int(mapping: Mapping[str, Any], *keys: str) -> int | None:
    value = _first_present(mapping, *keys, default=None)
    if value is None:
        return None
    return _int_value(value, path=_path(keys))


def _optional_float(mapping: Mapping[str, Any], *keys: str) -> float | None:
    value = _first_present(mapping, *keys, default=None)
    if value is None:
        return None
    return _float_value(value, path=_path(keys))


def _first_present(mapping: Mapping[str, Any], *keys: str, default: Any) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def _int_value(value: Any, *, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GaConfigError(f"{path} must be an integer.")
    return value


def _float_value(value: Any, *, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GaConfigError(f"{path} must be a number.")
    return float(value)


def _normalize_mode(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _normalize_choice(value: str) -> str:
    return value.strip().lower()


def _path(keys: tuple[str, ...]) -> str:
    if len(keys) == 1:
        return keys[0]
    return "/".join(keys)


__all__ = [
    "GaConfigError",
    "GaPromptOptimizerConfig",
    "MetricDirection",
    "MetricSpec",
    "parse_ga_prompt_optimizer_config",
]
