# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunnabilityState = Literal[
    "ready",
    "unavailable",
    "unverified",
    "incompatible",
    "not_applicable",
]


class RunnabilityCheck(BaseModel):
    prerequisite: str
    state: RunnabilityState
    blocking: bool
    code: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class BenchmarkMemberFailure(BaseModel):
    task_id: str
    task_revision: int | None = None
    prerequisite: str
    code: str
    message: str


class BenchmarkMemberSummary(BaseModel):
    total: int
    ready: int
    blocked: int
    failures: list[BenchmarkMemberFailure] = Field(default_factory=list)
    failures_truncated: bool = False


class RunnabilityReport(BaseModel):
    kind: Literal["evaluation", "benchmark_run"]
    runnable: bool
    checked_at: datetime
    checks: list[RunnabilityCheck]
    member_summary: BenchmarkMemberSummary | None = None
