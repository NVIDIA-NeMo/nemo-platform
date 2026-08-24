# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only contracts shared by trace-consuming NeMo Platform plugins."""

from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TraceQuery:
    """Portable filters supported by every trace provider."""

    ids: tuple[str, ...] = ()
    started_after: datetime | None = None
    started_before: datetime | None = None
    has_error: bool | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("trace query limit must be at least 1")
        if any(not trace_id for trace_id in self.ids):
            raise ValueError("trace query ids must not contain empty values")
        for field_name, value in (
            ("started_after", self.started_after),
            ("started_before", self.started_before),
        ):
            if value is not None and value.utcoffset() is None:
                raise ValueError(f"trace query {field_name} must include a timezone")
        if self.started_after is not None and self.started_before is not None:
            if self.started_after > self.started_before:
                raise ValueError("trace query started_after must not be later than started_before")


@dataclass(frozen=True)
class TraceRef:
    """Lightweight provider-native trace identity and list-view data."""

    id: str
    summary: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("trace ref id must not be empty")


@dataclass(frozen=True)
class TraceRow:
    """One hydrated trace whose data retains its provider-native shape."""

    id: str
    data: dict[str, object]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("trace row id must not be empty")


class TraceProvider(Protocol):
    """The minimal read capability required by trace consumers.

    Provider construction owns the durable source scope, such as an Intake
    workspace, LangSmith project, or MLflow experiment. ``TraceQuery`` carries
    only portable filters within that scope. ``has_error=False`` means a
    completed successful trace; in-progress and unknown states do not match.
    """

    name: str

    def filter_traces(self, query: TraceQuery) -> AsyncIterator[TraceRef]: ...

    def read_traces(self, traces: AsyncIterable[TraceRef]) -> AsyncIterator[TraceRow]: ...
