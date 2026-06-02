# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Memory store protocol — read-only seam over an agent's durable memory.

A ``MemoryStore`` is the harness-agnostic abstraction the triage layer
reasons against. Concrete adapters live under ``adapters/``. The
protocol intentionally exposes *no* write methods: mutation only happens
through reviewed ``MemoryProposal`` artifacts. Adapters that need to
also support writes (e.g. for a Phase 3 ``MemoryStrategy``) implement a
separate ``MutableMemoryStore`` protocol on top of this one, so a
read-only caller never accidentally picks up write surface.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Protocol, runtime_checkable


@dataclass
class MemoryEntry:
    """A single durable-memory entry, normalized across store backends.

    ``source_session_ids`` captures the corroboration depth — if an
    adapter can track which sessions originally produced an entry, the
    triage layer uses that as a "seen-in N sessions" signal. Adapters
    that can't track this should leave the list empty rather than
    populate with fake IDs; the council prompt handles empty lists as
    "single observation, low corroboration".

    ``last_used_at`` is for retrieval-staleness signal. Adapters set it
    to ``None`` when the store does not track retrieval (the PoC pi-
    hermes corpus is in this bucket).

    ``tags`` is an open dict for adapter-specific metadata (category,
    project scope, source file). The council prompt does not look at it
    directly; it surfaces in the proposal artifact for review.
    """

    id: str
    content: str
    source_session_ids: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    tags: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class MemoryStore(Protocol):
    """Read-only protocol every memory-store adapter implements.

    ``name`` identifies the store in proposal artifacts (e.g.
    ``"pi-hermes-memory"``, ``"nat-agent:my-workflow"``). It is recorded
    on each emitted proposal so a reviewer can see which store was
    triaged without consulting the surrounding job spec.
    """

    name: str

    def list_entries(self) -> Iterable[MemoryEntry]:
        """Iterate all entries in the store, in arbitrary but stable order.

        Implementations should yield entries lazily when the underlying
        store supports it; the triage layer streams over the iterable
        and does not require materializing the full corpus in memory.
        """
        ...

    def get(self, entry_id: str) -> MemoryEntry:
        """Fetch a single entry by id.

        Raises ``KeyError`` (or a subclass) when the id is unknown. The
        triage layer uses this for cross-entry lookups during merge
        proposal review; it does not call ``get`` during the main pass.
        """
        ...
