# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evidence value types shared by protocol metrics and agent evaluations."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class LocalFilesystemEvidence:
    """Constrained local filesystem handle for metric evidence access."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()

    @property
    def root(self) -> Path:
        """Resolved root path for this local evidence handle."""
        return self._root

    def path(self, relative_path: str | Path = ".") -> Path:
        """Return a path under the evidence root, rejecting traversal outside it."""
        relative = Path(relative_path)
        candidate = relative.resolve() if relative.is_absolute() else (self._root / relative).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError(f"evidence path {relative_path!r} resolves outside evidence root")
        return candidate

    async def exists(self, relative_path: str | Path = ".") -> bool:
        """Return whether a path exists under the evidence root."""
        path = self.path(relative_path)
        return await asyncio.to_thread(path.exists)

    async def read_text(self, relative_path: str | Path, *, encoding: str = "utf-8") -> str:
        """Read a text file under the evidence root."""
        path = self.path(relative_path)
        return await asyncio.to_thread(path.read_text, encoding=encoding)

    async def iter_paths(self, relative_path: str | Path = ".", *, recursive: bool = False) -> list[str]:
        """Return stable relative path names under the evidence root."""
        base = self.path(relative_path)
        return await asyncio.to_thread(self._iter_paths_sync, base, recursive)

    def _iter_paths_sync(self, base: Path, recursive: bool) -> list[str]:
        if base.is_file():
            return [base.relative_to(self._root).as_posix()]
        iterator = base.rglob("*") if recursive else base.iterdir()
        return sorted(path.relative_to(self._root).as_posix() for path in iterator)


class EvidenceDescriptor(BaseModel):
    """Descriptor for a candidate trace, source, or artifact."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="Evidence type, e.g. 'filesystem', 'trace', 'log_bundle', or 'review'.")
    ref: str | None = Field(
        default=None,
        description="Reference to externally stored evidence (e.g. a local path or storage ref).",
    )
    format: str | None = Field(
        default=None,
        description="Parser hint for the evidence payload, e.g. 'atif' for normalized traces.",
    )
    data: Any | None = Field(
        default=None,
        description="Small inline evidence payload; at least one of ref or data must be set.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the evidence descriptor.",
    )

    @model_validator(mode="after")
    def _requires_ref_or_data(self) -> EvidenceDescriptor:
        if self.ref is None and self.data is None:
            raise ValueError("evidence descriptor requires ref or data")
        return self


class CandidateEvidence(BaseModel):
    """Named evidence descriptors attached to an AgentEvalAttempt."""

    model_config = ConfigDict(extra="forbid")

    descriptors: dict[str, EvidenceDescriptor] = Field(
        default_factory=dict,
        description="Evidence descriptors keyed by name (e.g. 'final_state', 'trace', 'logs').",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the evidence collection.",
    )
    _filesystem_cache: dict[str, LocalFilesystemEvidence] = PrivateAttr(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_descriptor_mapping(cls, value: Any) -> Any:
        if isinstance(value, cls):
            return value
        if isinstance(value, dict) and "descriptors" not in value and "metadata" not in value:
            return {"descriptors": value}
        return value

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

    async def filesystem(self, name: str) -> LocalFilesystemEvidence:
        """Return a cached local filesystem handle for a named filesystem descriptor."""
        cached = self._filesystem_cache.get(name)
        if cached is not None:
            return cached

        descriptor = self.require(name, kind="filesystem")
        if descriptor.ref is None:
            raise ValueError(f"filesystem evidence descriptor {name!r} requires a local ref")

        root = _local_filesystem_ref(descriptor.ref)
        handle = LocalFilesystemEvidence(root)
        self._filesystem_cache[name] = handle
        return handle


def _local_filesystem_ref(ref: str) -> Path:
    """Resolve a local filesystem ref to a Path.

    Accepts POSIX paths, ``file://`` URIs, and Windows drive paths (e.g. ``C:\\dir``).
    Network and cloud URI schemes (http, https, s3, gs, ...) are rejected.
    """
    parsed = urlparse(ref)
    # A single-letter scheme is a Windows drive letter (e.g. "C:\\dir"), not a URI scheme.
    if len(parsed.scheme) == 1 and parsed.scheme.isalpha():
        return Path(ref)
    if parsed.scheme in {"http", "https", "s3", "gs"}:
        raise ValueError("CandidateEvidence.filesystem only supports local filesystem refs")
    if parsed.scheme == "file":
        return Path(parsed.path)
    if parsed.scheme:
        raise ValueError(f"CandidateEvidence.filesystem does not support {parsed.scheme!r} refs")
    return Path(ref)
