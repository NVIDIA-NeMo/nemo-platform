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
    """Named evidence descriptors attached to a candidate attempt."""

    model_config = ConfigDict(extra="forbid")

    descriptors: dict[str, EvidenceDescriptor] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def names(self, *, kind: str | None = None) -> list[str]:
        """Return evidence names, optionally filtered by descriptor kind."""
        if kind is None:
            return list(self.descriptors)
        return [name for name, descriptor in self.descriptors.items() if descriptor.kind == kind]

    def get(self, name: str) -> EvidenceDescriptor | None:
        """Return a descriptor by name without materializing evidence."""
        return self.descriptors.get(name)

    def require(self, name: str, *, kind: str | None = None) -> EvidenceDescriptor:
        """Return a descriptor by name, raising when it is missing or has the wrong kind."""
        descriptor = self.get(name)
        if descriptor is None:
            raise KeyError(f"missing evidence descriptor {name!r}")
        if kind is not None and descriptor.kind != kind:
            raise ValueError(f"evidence descriptor {name!r} has kind {descriptor.kind!r}, expected {kind!r}")
        return descriptor
