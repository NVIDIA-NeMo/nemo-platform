# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small JSON-safe boundary models for Eval Author."""

from typing import Self

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


class ArtifactDescriptor(BaseModel):
    """A portable locator and content identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uri: str
    identity: str

    @field_validator("uri")
    @classmethod
    def _uri_is_non_empty(cls, value: str) -> str:
        return _non_empty(value, label="artifact URI")

    @field_validator("identity")
    @classmethod
    def _identity_is_non_empty(cls, value: str) -> str:
        return _non_empty(value, label="artifact identity")


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
    """The two authored artifacts, their metric keys, and a summary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_set: ArtifactDescriptor | None = None
    verifier_bundle: ArtifactDescriptor | None = None
    metric_keys: tuple[str, ...] = ()
    summary: str

    @field_validator("summary")
    @classmethod
    def _summary_is_non_empty(cls, value: str) -> str:
        return _non_empty(value, label="Eval Author result summary")

    @model_validator(mode="after")
    def _artifacts_are_all_or_none(self) -> Self:
        if self.task_set is None and self.verifier_bundle is None:
            if self.metric_keys:
                raise ValueError("metric keys require authored artifacts")
            return self
        if self.task_set is None or self.verifier_bundle is None:
            raise ValueError("task_set and verifier_bundle must be returned together")
        _validate_metric_keys(self.metric_keys)
        return self

    @classmethod
    def no_artifacts(cls, summary: str) -> Self:
        """Return a successful outcome that produced no artifacts."""
        return cls(summary=summary)
