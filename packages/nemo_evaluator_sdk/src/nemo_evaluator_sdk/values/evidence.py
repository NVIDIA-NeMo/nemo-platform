# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evidence value types shared by protocol metrics and agent evaluations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceDescriptor(BaseModel):
    """Descriptor for a candidate trace, source, or artifact."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    ref: str | None = None
    format: str | None = None
    data: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _requires_ref_or_data(self) -> "EvidenceDescriptor":
        if self.ref is None and self.data is None:
            raise ValueError("evidence descriptor requires ref or data")
        return self


class CandidateEvidence(BaseModel):
    """Evidence attached to a generated or imported candidate output."""

    model_config = ConfigDict(extra="forbid")

    trace: EvidenceDescriptor | None = None
    sources: list[EvidenceDescriptor] = Field(default_factory=list)
    artifacts: list[EvidenceDescriptor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
