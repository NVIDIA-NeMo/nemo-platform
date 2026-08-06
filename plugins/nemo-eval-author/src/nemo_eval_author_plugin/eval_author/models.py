# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small boundary models for Eval Author."""

from typing import Self

from nemo_experimentalist_plugin.entities import Dataset
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_GENERIC_METRIC_KEYS = frozenset({"reward", "score"})


def _validate_metric_keys(value: tuple[str, ...]) -> tuple[str, ...]:
    keys = tuple(key.strip() for key in value)
    if not keys or any(not key for key in keys):
        raise ValueError("metric keys must be non-empty")
    if len(set(keys)) != len(keys):
        raise ValueError("metric keys must be unique")
    if set(keys) <= _GENERIC_METRIC_KEYS:
        raise ValueError("at least one non-generic metric key is required")
    return keys


def _non_empty(value: str, *, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} must be non-empty")
    return value


class MetricAuthoringResult(BaseModel):
    """Metric keys and a short account of the authored verifier edits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_keys: tuple[str, ...]
    summary: str

    @field_validator("metric_keys")
    @classmethod
    def _metric_keys_are_portable(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_metric_keys(value)

    @field_validator("summary")
    @classmethod
    def _summary_is_non_empty(cls, value: str) -> str:
        return _non_empty(value, label="metric authoring summary")


class EvalAuthorConfig(BaseModel):
    """Tuning parameters for the Eval Author agent."""

    max_summary_tokens: int = Field(
        default=80_000,
        description="Max tokens the token-budget summarizer may use.",
    )
    max_traces: int = Field(
        default=10,
        description="Max trace refs from the insight to analyze in depth.",
    )
    max_validation_repair_attempts: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Max Eval Author repair attempts after mandatory Insight verifier validation fails.",
    )


class EvalAuthorResult(BaseModel):
    """Modified evaluation datasets, their metric keys, and a summary."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    train_dataset: Dataset
    validation_dataset: Dataset
    insight_suite: Dataset | None = None
    insight_suite_identity: str | None = None
    metric_keys: tuple[str, ...] = ()
    summary: str

    @field_validator("summary")
    @classmethod
    def _summary_is_non_empty(cls, value: str) -> str:
        return _non_empty(value, label="Eval Author result summary")

    @model_validator(mode="after")
    def _authored_suite_fields_are_all_or_none(self) -> Self:
        if self.insight_suite is None:
            if self.insight_suite_identity is not None or self.metric_keys:
                raise ValueError("Insight suite identity and metric keys require an authored Insight suite")
            return self
        if self.insight_suite_identity is None:
            raise ValueError("an authored Insight suite requires its content identity")
        _non_empty(self.insight_suite_identity, label="Insight suite identity")
        _validate_metric_keys(self.metric_keys)
        return self
