# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ResourceUsageSample(BaseModel):
    """One runtime-provided aggregate resource observation."""

    model_config = ConfigDict(frozen=True)

    component: str = "sandbox"
    source: str
    collection_status: str = "sampled"
    collection_error: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cpu_usage_cores: float | None = Field(default=None, ge=0)
    memory_usage_bytes: int | None = Field(default=None, ge=0)
    cpu_request_cores: float | None = Field(default=None, ge=0)
    cpu_limit_cores: float | None = Field(default=None, ge=0)
    memory_request_bytes: int | None = Field(default=None, ge=0)
    memory_limit_bytes: int | None = Field(default=None, ge=0)
    gpu_request: float | None = Field(default=None, ge=0)
    gpu_usage_percent: float | None = Field(default=None, ge=0)
    gpu_memory_usage_bytes: int | None = Field(default=None, ge=0)
