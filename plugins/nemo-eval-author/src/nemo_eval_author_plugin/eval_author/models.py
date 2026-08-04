# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared models for the top-level Eval Author."""

from nemo_experimentalist_plugin.experimentalist.components.evaluator import Dataset
from pydantic import BaseModel, ConfigDict, Field


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
    """Output of one Eval Author run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    train_dataset: Dataset
    validation_dataset: Dataset
    insight_train_suite: Dataset | None = Field(
        default=None,
        description="Insight suite train half, visible to the optimization loop as development feedback.",
    )
    insight_train_suite_identity: str | None = Field(
        default=None,
        description="SHA-256 identity of the Insight train half's task and verifier content.",
    )
    insight_validation_suite: Dataset | None = Field(
        default=None,
        description="Insight suite validation half, held out so its score is independent scoring evidence.",
    )
    insight_validation_suite_identity: str | None = Field(
        default=None,
        description="SHA-256 identity of the Insight validation half's task and verifier content.",
    )
    summary: str
