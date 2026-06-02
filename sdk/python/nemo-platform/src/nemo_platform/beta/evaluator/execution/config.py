# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public configuration types for the v4 evaluator API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

from nemo_platform.beta.evaluator.inference import PostprocessResponse, PreprocessRequest
from nemo_platform.beta.evaluator.values import (
    Agent,
    FieldMapping,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_platform.beta.evaluator.values.datasets import DatasetInput
from nemo_platform.beta.evaluator.values.results import AggregateFieldName

_RunConfigT: TypeAlias = RunConfig | RunConfigOnline | RunConfigOnlineModel


def normalize_params(
    params: _RunConfigT | None = None,
    target: Model | Agent | None = None,
) -> _RunConfigT:
    if isinstance(target, Model):
        if not isinstance(params, RunConfigOnlineModel):
            params = RunConfigOnlineModel(**params.model_dump()) if params else RunConfigOnlineModel()
    elif isinstance(target, Agent):
        if not isinstance(params, RunConfigOnline):
            params = RunConfigOnline(**params.model_dump()) if params else RunConfigOnline()
    else:
        params = params or RunConfig()
    return params


def fail_fast_from_params(params: _RunConfigT) -> bool:
    """
    Return whether row failures should abort execution for the given params.
    When params is not an online params, return fail_fast is True - always fail fast.
    """
    return not (isinstance(params, RunConfigOnline) and params.ignore_request_failure)


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """Normalized evaluator request passed from the public API to backends."""

    dataset: DatasetInput | str | Path
    params: _RunConfigT = field(default_factory=normalize_params)
    target: Model | Agent | None = None
    dataset_glob_pattern: str | None = None
    field_mapping: FieldMapping | None = None
    prompt_template: str | dict[str, Any] | None = None
    aggregate_fields: tuple[AggregateFieldName, ...] | None = None
    preprocess_hooks: tuple[PreprocessRequest, ...] | None = None
    postprocess_hooks: tuple[PostprocessResponse, ...] | None = None

    def __post_init__(self) -> None:
        """Normalize params to a concrete type compatible with the configured target."""
        object.__setattr__(self, "params", normalize_params(self.params, self.target))
