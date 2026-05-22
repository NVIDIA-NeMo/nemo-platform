# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schemas for post-hoc annotations on spans and sessions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from nmp.common.entities.values import DatetimeFilter
from nmp.intake.spans.domain import Annotation as DomainAnnotation
from nmp.intake.spans.domain import AnnotationKind
from pydantic import BaseModel, ConfigDict, Field, model_validator

_FEEDBACK_VALUES = frozenset({"positive", "negative"})


class AnnotationSortField(StrEnum):
    CREATED_AT_ASC = "created_at"
    CREATED_AT_DESC = "-created_at"


class AnnotationFilter(BaseModel):
    span_id: str | None = Field(default=None, description="Filter by target span id.")
    session_id: str | None = Field(default=None, description="Filter by target session id.")
    kind: AnnotationKind | None = Field(default=None, description="Filter by annotation kind.")
    name: str | None = Field(default=None, description="Filter by annotation name (used by `label`/`metadata`).")
    created_by: str | None = Field(default=None, description="Filter by principal that wrote the annotation.")
    created_at: DatetimeFilter | None = Field(
        default=None, description="Filter by row creation time (range supported)."
    )


class _AnnotationFieldsMixin(BaseModel):
    """Shared value-field validators for AnnotationInput and AnnotationUpdate."""

    kind: AnnotationKind
    name: str | None = Field(default=None, max_length=256)
    value_text: str | None = Field(default=None, min_length=1, max_length=512)
    value_numeric: float | None = None
    text: str | None = Field(default=None, min_length=1, max_length=10_000)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_per_kind(self) -> Self:
        if self.kind == AnnotationKind.FEEDBACK:
            if self.value_text not in _FEEDBACK_VALUES:
                raise ValueError(f"kind=feedback requires value_text in {sorted(_FEEDBACK_VALUES)}")
            _forbid(self, "feedback", ("value_numeric", "text", "metadata", "name"))

        elif self.kind == AnnotationKind.LABEL:
            if self.value_text is None and self.value_numeric is None:
                raise ValueError("kind=label requires `value_text` or `value_numeric`")
            if self.value_numeric is not None and self.name is None:
                raise ValueError("kind=label with `value_numeric` requires `name`")
            _forbid(self, "label", ("text",))

        elif self.kind == AnnotationKind.NOTE:
            if not self.text:
                raise ValueError("kind=note requires `text`")
            _forbid(self, "note", ("value_text", "value_numeric", "metadata", "name"))

        elif self.kind == AnnotationKind.METADATA:
            if not self.metadata:
                raise ValueError("kind=metadata requires non-empty `metadata`")
            _forbid(self, "metadata", ("value_text", "value_numeric", "text", "name"))

        return self


class AnnotationInput(_AnnotationFieldsMixin):
    """Request body for POST /annotations.

    Server fills `annotation_id`, `created_at`, `ingested_at`, and `created_by`.
    Producer supplies the target (span_id and/or session_id; loose target — not
    validated against existing spans/sessions) plus kind-specific fields.
    """

    model_config = ConfigDict(extra="forbid")

    span_id: str | None = Field(
        default=None,
        description="Target span id. Optional when annotating a whole session. Loose target policy — not validated.",
    )
    session_id: str = Field(
        description="Session id this annotation belongs to. Required even for span-targeted annotations for session-locality reads.",
    )


class AnnotationUpdate(BaseModel):
    """Request body for PATCH /annotations/{id}.

    The kind is immutable. Value fields can be updated; the full set is
    re-validated against the kind on update.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=256)
    value_text: str | None = Field(default=None, min_length=1, max_length=512)
    value_numeric: float | None = None
    text: str | None = Field(default=None, min_length=1, max_length=10_000)
    metadata: dict[str, Any] | None = None


class Annotation(BaseModel):
    """Response model for annotation read endpoints."""

    annotation_id: str
    workspace: str
    span_id: str | None = None
    session_id: str

    kind: AnnotationKind
    name: str | None = None
    value_text: str | None = None
    value_numeric: float | None = None
    text: str | None = None
    metadata: dict[str, Any] | None = None

    created_by: str | None = None
    created_at: datetime
    ingested_at: datetime

    @classmethod
    def from_domain(cls, annotation: DomainAnnotation) -> Self:
        return cls(
            annotation_id=annotation.annotation_id,
            workspace=annotation.workspace,
            span_id=annotation.span_id,
            session_id=annotation.session_id,
            kind=annotation.kind,
            name=annotation.name,
            value_text=annotation.value_text,
            value_numeric=annotation.value_numeric,
            text=annotation.text,
            metadata=annotation.metadata,
            created_by=annotation.created_by,
            created_at=annotation.created_at,
            ingested_at=annotation.ingested_at,
        )


def _forbid(model: BaseModel, kind: str, fields: tuple[str, ...]) -> None:
    for field in fields:
        if getattr(model, field, None) is not None:
            raise ValueError(f"kind={kind} does not accept `{field}`")
