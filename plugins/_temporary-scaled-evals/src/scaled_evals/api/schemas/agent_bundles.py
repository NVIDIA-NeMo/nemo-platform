# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AgentBundleVisibility = Literal["private", "public"]
AgentBundleQualification = Literal["registered", "qualified", "rejected"]


class AgentBundleCreate(BaseModel):
    bundle_name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    agent_name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    agent_version: str = Field(min_length=1, max_length=100)
    image_ref: str = Field(
        min_length=1,
        max_length=500,
        description="Signed tag-form OCI reference submitted to hosted Kubernetes.",
    )
    image_digest: str = Field(
        pattern=r"^[^\s@]+@sha256:[0-9a-f]{64}$",
        description="Immutable OCI image identity; tags without a digest are rejected.",
    )
    entrypoint: str = Field(pattern=r"^[A-Za-z0-9._/-]+$", min_length=1, max_length=300)
    platform: Literal["linux/amd64"] = "linux/amd64"
    runtime_abi: Literal["glibc"] = "glibc"
    bundle_layout_version: Literal[1] = 1
    builder_profile: str = Field(default="node22-npm-v1", min_length=1, max_length=100)
    source_lock_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("entrypoint")
    @classmethod
    def relative_entrypoint(cls, value: str) -> str:
        normalized = value.strip().removeprefix("/")
        if not normalized or ".." in normalized.split("/"):
            raise ValueError("entrypoint must be a relative path without '..'")
        return normalized

    @model_validator(mode="after")
    def image_tag_matches_digest_repository(self) -> "AgentBundleCreate":
        if "@" in self.image_ref or any(char.isspace() for char in self.image_ref):
            raise ValueError("image_ref must be a tag-form reference without '@'")
        image_ref_repo, separator, tag = self.image_ref.rpartition(":")
        digest_repo = self.image_digest.split("@", 1)[0]
        if not separator or not image_ref_repo or not tag or "/" in tag:
            raise ValueError("image_ref must include an explicit runtime tag")
        if image_ref_repo != digest_repo:
            raise ValueError("image_ref and image_digest must use the same repository")
        return self


class AgentBundleQualificationUpdate(BaseModel):
    status: Literal["qualified", "rejected"]
    evidence: dict[str, Any] = Field(default_factory=dict)


class AgentBundle(BaseModel):
    id: str
    owner_id: str | None
    bundle_name: str
    agent_name: str
    agent_version: str
    image_ref: str
    image_digest: str
    entrypoint: str
    platform: Literal["linux/amd64"]
    runtime_abi: Literal["glibc"]
    bundle_layout_version: Literal[1]
    builder_profile: str
    source_lock_digest: str
    fingerprint: str
    metadata: dict[str, Any]
    visibility: AgentBundleVisibility
    qualification_status: AgentBundleQualification
    qualification_evidence: dict[str, Any]
    qualified_at: datetime | None
    qualified_by: str | None
    created_at: datetime
    updated_at: datetime
