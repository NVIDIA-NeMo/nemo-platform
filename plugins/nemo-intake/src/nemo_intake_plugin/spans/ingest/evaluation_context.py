# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared experiment/evaluation context models for span ingest endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExperimentContext(BaseModel):
    """Experiment context accepted by ingest endpoints."""

    experiment_id: str = Field(description="Name of an existing Experiment entity.")
    test_case_id: str | None = Field(default=None, description="Optional producer-supplied test case id.")

    model_config = ConfigDict(extra="forbid")

    def to_evaluation_context(self) -> EvaluationContext:
        return EvaluationContext(
            evaluation_id=self.experiment_id,
            test_case_id=self.test_case_id,
        )


class EvaluationContext(BaseModel):
    # Deprecated pre-release ingest shape. Use ExperimentContext / experiment_context.
    evaluation_id: str | None = None
    evaluation_sha: str | None = None
    evaluation_run_id: str | None = None
    test_case_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ExperimentContextIngestModel(BaseModel):
    """Base model for ingest payloads that accept experiment context."""

    experiment_context: ExperimentContext | None = None
    # Deprecated pre-release field. Use experiment_context.
    evaluation_context: EvaluationContext | None = Field(
        default=None,
        deprecated=True,
        description="Deprecated. Use experiment_context; when both are sent, experiment_context takes precedence.",
    )

    def resolved_evaluation_context(self) -> EvaluationContext | None:
        if self.experiment_context is not None:
            return self.experiment_context.to_evaluation_context()
        evaluation_context: EvaluationContext | None = self.__dict__.get("evaluation_context")
        return evaluation_context
