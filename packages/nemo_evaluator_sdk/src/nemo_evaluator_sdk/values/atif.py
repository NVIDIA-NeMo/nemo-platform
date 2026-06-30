# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Lightweight ATIF read models for the evaluator SDK.

The evaluator *ingests* traces that producers emit in the Agent Trajectory
Interchange Format (ATIF; RFC 0001, schema_version ``ATIF-v1.x``). It does not
produce or normalize ATIF, and it only reads a small subset of the schema, so
this module models *just that subset* rather than vendoring the full reference
implementation.

These are deliberately permissive (``extra="ignore"``): fields the SDK does not
consume (images, content parts, observations, sub-agents, agent metadata, ...)
are accepted and dropped, so a trace emitted against a newer ATIF revision still
validates. Validation here means "this payload carries the ATIF fields the
evaluator's metrics rely on" — not full RFC conformance, which is the producer's
responsibility. The authoritative spec is RFC 0001.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolCall(BaseModel):
    """A single tool/function invocation within an agent step."""

    model_config = ConfigDict(extra="ignore")

    tool_call_id: str | None = Field(default=None, description="Producer-assigned tool call id, if any.")
    function_name: str = Field(description="Name of the invoked tool/function.")
    arguments: dict[str, Any] | None = Field(default=None, description="Arguments passed to the tool.")


class Metrics(BaseModel):
    """Per-step token metrics."""

    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class FinalMetrics(BaseModel):
    """Trajectory-level aggregate token metrics."""

    model_config = ConfigDict(extra="ignore")

    total_prompt_tokens: int | None = None
    total_completion_tokens: int | None = None


class Step(BaseModel):
    """One step in an agent trajectory."""

    model_config = ConfigDict(extra="ignore")

    source: Literal["system", "user", "agent"] = Field(description="Who produced this step.")
    message: str = Field(default="", description="Step text content.")
    tool_calls: list[ToolCall] | None = Field(default=None, description="Tool calls issued in this step.")
    metrics: Metrics | None = Field(default=None, description="Per-step token metrics, if reported.")


class Trajectory(BaseModel):
    """An ATIF agent trajectory (read view over the subset the SDK consumes)."""

    model_config = ConfigDict(extra="ignore")

    schema_version: str = Field(description="ATIF schema version, e.g. 'ATIF-v1.7'.")
    steps: list[Step] = Field(min_length=1, description="Ordered trajectory steps.")
    final_metrics: FinalMetrics | None = Field(default=None, description="Aggregate token metrics, if reported.")

    @field_validator("schema_version")
    @classmethod
    def _looks_like_atif(cls, value: str) -> str:
        # Cheap sanity gate so arbitrary JSON isn't silently accepted as a trace.
        if not value.startswith("ATIF-"):
            raise ValueError(f"unexpected trace schema_version {value!r}; expected an 'ATIF-*' version")
        return value
