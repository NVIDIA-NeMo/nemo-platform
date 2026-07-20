# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared evaluation context models for span ingest endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluationContext(BaseModel):
    """Evaluation context accepted by ingest endpoints (the canonical shape).

    ``extra="ignore"`` so a producer still sending retired keys (evaluation_sha, evaluation_run_id,
    metadata) keeps ingesting without error rather than being rejected.
    """

    evaluation_id: str | None = Field(default=None, description="Name of an existing Evaluation.")
    test_case_id: str | None = Field(default=None, description="Optional producer-supplied test case id.")

    model_config = ConfigDict(extra="ignore")


class ExperimentContext(BaseModel):
    """Deprecated alias for :class:`EvaluationContext`. Producers should send ``evaluation_context``."""

    experiment_id: str = Field(description="Name of an existing Experiment entity.")
    test_case_id: str | None = Field(default=None, description="Optional producer-supplied test case id.")

    model_config = ConfigDict(extra="forbid")

    def to_evaluation_context(self) -> EvaluationContext:
        return EvaluationContext(
            evaluation_id=self.experiment_id,
            test_case_id=self.test_case_id,
        )


class EvaluationContextIngestModel(BaseModel):
    """Base model for ingest payloads that carry evaluation context."""

    evaluation_context: EvaluationContext | None = None
    # Deprecated alias; use evaluation_context. Read via __dict__ to avoid a deprecation warning.
    experiment_context: ExperimentContext | None = Field(
        default=None,
        deprecated=True,
        description="Deprecated. Use evaluation_context; when both are sent, evaluation_context takes precedence.",
    )

    def resolved_evaluation_context(self) -> EvaluationContext | None:
        if self.evaluation_context is not None:
            return self.evaluation_context
        experiment_context: ExperimentContext | None = self.__dict__.get("experiment_context")
        if experiment_context is not None:
            return experiment_context.to_evaluation_context()
        return None
