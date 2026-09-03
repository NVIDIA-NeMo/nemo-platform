# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Visibility = Literal["private", "team", "org", "public"]
BenchmarkQualification = Literal["registered", "qualified", "rejected"]

SLUG_MAX_LEN = 63
SLUG_PATTERN = rf"^[a-z0-9][a-z0-9-]{{0,{SLUG_MAX_LEN - 1}}}$"


class OperationalPolicy(BaseModel):
    """Allowlisted operational overrides for a metadata-only benchmark variant."""

    model_config = ConfigDict(extra="forbid")

    agent_timeout_floor_sec: int = Field(ge=1, le=86400)


class BenchmarkDerivedFrom(BaseModel):
    benchmark_id: str
    revision: int = Field(ge=1)


class BenchmarkVariantCreate(BaseModel):
    """Request body: POST /v1/benchmarks/{id}/variants.

    Copies the base revision member pins unchanged and attaches an allowlisted
    operational policy. Does not accept tasks or content-changing fields.
    """

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = None
    visibility: Visibility = "private"
    from_revision: int | None = Field(default=None, ge=1)
    operational_policy: OperationalPolicy


# A member task in a benchmark revision. `task_revision` is optional: null pins
# nothing and resolves to the task's current/latest revision at eval time; an
# integer pins that exact task revision (reproducible).
class BenchmarkTaskRef(BaseModel):
    task_id: str = Field(min_length=1)
    task_revision: int | None = Field(default=None, ge=1)


# Response shape of a member task (adds the stable in-revision ordering).
class BenchmarkTaskMember(BenchmarkTaskRef):
    position: int
    # The referenced task's human-readable slug/name (joined from `tasks`), so
    # clients can show "nemo-secrets-crud" rather than the opaque task_id.
    task_slug: str | None = None
    task_name: str | None = None


# Request body: POST /v1/benchmarks. Creates the benchmark and its revision 1
# with `tasks` as the immutable member set (may be empty).
class BenchmarkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = None
    visibility: Visibility = "private"
    tasks: list[BenchmarkTaskRef] = Field(default_factory=list)


# Request body: POST /v1/benchmarks/{id}/revisions. Snapshots a new immutable
# revision with the given member set.
class BenchmarkRevisionCreate(BaseModel):
    description: str | None = None
    tasks: list[BenchmarkTaskRef] = Field(default_factory=list)


# Request body: PATCH /v1/benchmarks/{id}. Identity/metadata only; revision
# membership is immutable (snapshot a new revision to change it).
class BenchmarkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = None
    visibility: Visibility | None = None


class BenchmarkQualificationUpdate(BaseModel):
    status: Literal["qualified", "rejected"]
    evidence: dict[str, Any] = Field(default_factory=dict)


# Response: GET /v1/benchmarks/{id}, /by-slug/{slug}, and list items.
class Benchmark(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    visibility: Visibility
    qualification_status: BenchmarkQualification = "registered"
    qualification_evidence: dict[str, Any] = Field(default_factory=dict)
    qualified_at: datetime | None = None
    qualified_by: str | None = None
    current_revision: int | None
    created_at: datetime
    updated_at: datetime


# Response: GET /v1/benchmarks/{id} — benchmark plus the latest revision number
# and its member tasks (empty until a revision exists).
class BenchmarkDetail(Benchmark):
    revision: int | None = None
    tasks: list[BenchmarkTaskMember] = Field(default_factory=list)
    derived_from: BenchmarkDerivedFrom | None = None
    operational_policy: dict[str, Any] = Field(default_factory=dict)


# Response body: POST /v1/benchmarks
class BenchmarkCreateResponse(Benchmark):
    revision: int
    links: dict[str, str]


# Response body: POST /v1/benchmarks/{id}/variants
class BenchmarkVariantCreateResponse(Benchmark):
    revision: int
    derived_from: BenchmarkDerivedFrom
    operational_policy: OperationalPolicy
    links: dict[str, str]


# Response body: POST /v1/benchmarks/{id}/revisions
class BenchmarkRevisionCreateResponse(BaseModel):
    id: str
    revision: int
    links: dict[str, str]
