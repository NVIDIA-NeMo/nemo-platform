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
