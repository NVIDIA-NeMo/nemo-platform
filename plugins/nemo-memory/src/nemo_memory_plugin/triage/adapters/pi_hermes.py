# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only adapter over a pi-hermes-memory Markdown corpus.

Targets two related on-disk formats:

1. The PoC consolidate pipeline output at
   ``~/.pi/agent/claude-session-replays/CONSOLIDATED/{MEMORY,USER,failures}.md``
   and ``CONSOLIDATED/projects-memory/<proj>/MEMORY.md``. Entries are
   separated by ``§`` on its own line; each entry ends with an optional
   ``<!-- seen-in: N sessions -->`` HTML comment carrying corroboration
   depth.

2. The live pi-hermes-memory SQLite export at
   ``~/.pi/agent/pi-hermes-memory/{MEMORY,USER,failures}.md``. Same
   ``§`` separator, but the trailing comment is
   ``<!-- created=YYYY-MM-DD, last=YYYY-MM-DD -->`` instead of a
   seen-in count.

The adapter is read-only by design (the ``MemoryStore`` protocol is
read-only). Mutations only happen through reviewed ``MemoryProposal``
artifacts; see ``DESIGN.md`` Phase 0.
"""

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path

from nemo_memory_plugin.triage.store import MemoryEntry

# Trailing-comment patterns. The two known footer styles carry
# different metadata; we match whichever is present and ignore the rest.
_SEEN_IN_RE = re.compile(r"<!--\s*seen-in:\s*(\d+)(?:\s+sessions?)?\s*-->", re.IGNORECASE)
_CREATED_RE = re.compile(r"<!--\s*created=(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_LAST_RE = re.compile(r"last=(\d{4}-\d{2}-\d{2})\s*-->", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Entry separator: a line containing only ``§`` (with optional surrounding
# whitespace). ``re.MULTILINE`` lets ``^`` / ``$`` anchor inside the file.
_SEPARATOR_RE = re.compile(r"^\s*§\s*$", re.MULTILINE)


@dataclass
class PiHermesMemoryStore:
    """One Markdown file = one logical memory store.

    Instantiate once per category file (e.g. one store for ``USER.md``,
    a separate store for ``MEMORY.md``). Callers compose multiple stores
    when they need to triage across categories — the protocol stays
    single-source so the council prompt has a clean per-store name to
    cite in proposals.

    ``name`` is recorded on every emitted proposal. Pick something
    durable and unambiguous (e.g. ``"pi-hermes:user"``,
    ``"pi-hermes:CONSOLIDATED:projects-memory/nemo-platform"``).

    The constructor does not read the file; reading is deferred to
    ``list_entries`` so callers can construct a store against a path
    that may not yet exist (e.g. for fixture-grade tests that write the
    file just before iterating).
    """

    path: Path
    name: str

    def list_entries(self) -> Iterable[MemoryEntry]:
        if not self.path.exists():
            return
        text = self.path.read_text(encoding="utf-8")
        for index, chunk in enumerate(_SEPARATOR_RE.split(text)):
            entry = _parse_entry(chunk, source_file=self.path.name, ordinal=index)
            if entry is not None:
                yield entry

    def get(self, entry_id: str) -> MemoryEntry:
        for entry in self.list_entries():
            if entry.id == entry_id:
                return entry
        raise KeyError(entry_id)


def _stable_id(content: str) -> str:
    """SHA-256 prefix of the normalized content.

    Stable across re-reads of the same file and across instantiations
    of the same content in different files. We deliberately do not mix
    the source filename into the hash: if the same entry text appears
    in two files (which happens during the consolidate pipeline's raw/
    vs. deduped output), we want a reviewer to see them as the same
    entry. Disambiguation, when needed, goes through ``tags``.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _parse_iso_date(s: str) -> datetime | None:
    """Parse a ``YYYY-MM-DD`` date string into a UTC midnight datetime.

    The pi-hermes export uses date-only stamps. We coerce to a tz-aware
    datetime at UTC midnight so downstream comparisons against
    ``last_used_at`` are unambiguous.
    """
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _parse_entry(chunk: str, source_file: str, ordinal: int) -> MemoryEntry | None:
    """Parse one entry chunk into a :class:`MemoryEntry`.

    Returns ``None`` for chunks that contain no actual content (whitespace
    only, or only an HTML comment with no prose). ``ordinal`` is included
    in tags so reviewers can find an entry's original file position even
    when the content hash collides with another file.
    """
    stripped = chunk.strip()
    if not stripped:
        return None

    seen_in_match = _SEEN_IN_RE.search(stripped)
    corroboration = int(seen_in_match.group(1)) if seen_in_match else 1

    created_match = _CREATED_RE.search(stripped)
    last_match = _LAST_RE.search(stripped)
    created_at = _parse_iso_date(created_match.group(1)) if created_match else None
    last_used_at = _parse_iso_date(last_match.group(1)) if last_match else None

    content = _HTML_COMMENT_RE.sub("", stripped).strip()
    if not content:
        return None

    tags: dict[str, str] = {
        "source_file": source_file,
        "ordinal": str(ordinal),
    }
    if seen_in_match:
        tags["seen_in_raw"] = seen_in_match.group(0)

    return MemoryEntry(
        id=_stable_id(content),
        content=content,
        corroboration_count=corroboration,
        created_at=created_at,
        last_used_at=last_used_at,
        tags=tags,
    )
