# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The analyst's memory document: durable context that survives across runs.

An analyst run is otherwise stateless. Its only carry-over is
``AnalysisRunStatus.last_successful_run_at``, a cursor that narrows which
traces to read, so everything the analyst works out about an agent's telemetry
is rediscovered from scratch on the next run. Memory is a small markdown
document that closes that gap, and — because it lives in the platform rather
than on a developer's disk — it is also the only way to hand standing context
to *scheduled* analysis, which never sees ``AGENT-SPEC.md``.

The document has two zones:

- Everything before ``AUTO_START`` belongs to the developer. Nothing here ever
  rewrites it, which is what makes a document that is both auto-maintained and
  hand-editable safe without version history or a review queue.
- The span between ``AUTO_START`` and ``AUTO_END`` belongs to the analyst and
  is replaced wholesale on each run that returns notes.

Replacing rather than appending means de-duplication and pruning are ordinary
consequences of writing, with no separate consolidation pass. The cost is that
the analyst must treat its returned notes as the memory it wants to *exist*
rather than a log of the current run — see ``AnalystResult.memory``. It is told
so in its instructions, and :func:`write` refuses to act on an empty list so a
model that simply omits the field cannot erase the document.

Storage is the ``nemo-agent-memory`` fileset rather than a file beside
``optimizer.yaml``, because the scheduled job runs in a container with no
checkout and no durable local path: ``ctx.storage.persistent`` is scoped to one
job id and deleted once the job succeeds. A fileset is the one store that is
durable, workspace-scoped, writable from inside a job, and visible to a human
in Studio.
"""

import re
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol

import httpx
from nemo_insights_plugin.analyst.result import MemoryNote
from nemo_platform import AsyncNeMoPlatform, NeMoPlatformError
from nemo_platform_plugin.client.errors import NemoClientError

MEMORY_FILESET = "nemo-agent-memory"
MEMORY_FILENAME = "AGENT-MEMORY.md"

AUTO_START = "<!-- nemo:auto:start -->"
AUTO_END = "<!-- nemo:auto:end -->"
AUTO_BANNER = "<!-- Observed by `nemo agents analyst run`. Edits between these markers are replaced. -->"
EMPTY_ZONE = "_No observations recorded yet._"

# The whole document is injected into the analyst's instructions on every run,
# so the budget is a context cost paid forever, not a storage limit. It is
# enforced here rather than merely requested in the prompt: an advisory limit
# on a machine-written file is how context windows quietly fill up.
MAX_NOTES = 40
MAX_AUTO_BYTES = 8_000

_HUMAN_ZONE_HINT = (
    "Context the optimization loop keeps about this agent. Anything you write\n"
    "above the marker below is yours and is never rewritten; the analyst only\n"
    "replaces the section between the markers."
)

_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

# Read failures are normal on a first run (no document, no fileset yet) and are
# reported by the write instead, which is the operation whose loss matters.
# NemoClientError covers transport failures and is deliberately not a
# NeMoPlatformError, so it has to be named: without it a network blip while
# fetching memory would abort an otherwise healthy analysis.
_STORE_ERRORS = (NeMoPlatformError, NemoClientError, httpx.HTTPError, OSError, ValueError, RuntimeError)


def scaffold(agent: str) -> str:
    """Return a fresh document with a header and an empty developer zone."""
    return f"# Agent memory: {agent}\n\n{_HUMAN_ZONE_HINT}\n"


def render_note(note: MemoryNote, *, stamp: str) -> str:
    """Render one note as a single bullet.

    Interior whitespace is collapsed so that a multi-line note cannot break the
    bullet list or the marker arithmetic that :func:`replace_auto_zone` relies
    on. The stamp records when the note was last affirmed, not when it was first
    observed: a full rewrite re-states everything still true, so "as of" is the
    honest reading of the date.
    """
    text = " ".join(note.note.split())
    detail = f"{stamp}; {' '.join(note.source.split())}" if note.source.strip() else stamp
    return f"- {text} ({detail})"


def render_auto_zone(notes: Sequence[MemoryNote], *, stamp: str) -> tuple[str, int]:
    """Render the maintained zone, returning it with the number of notes dropped.

    Notes arrive most important first, so the budget is applied by stopping at
    the first note that does not fit rather than skipping it and continuing —
    keeping a later short note over an earlier important one would silently
    invert the analyst's own ranking.
    """
    lines: list[str] = []
    used = 0
    dropped = 0
    for index, note in enumerate(notes):
        line = render_note(note, stamp=stamp)
        size = len(line.encode("utf-8")) + 1
        if len(lines) >= MAX_NOTES or used + size > MAX_AUTO_BYTES:
            dropped = len(notes) - index
            break
        lines.append(line)
        used += size
    body = "\n".join(lines) if lines else EMPTY_ZONE
    return f"{AUTO_START}\n{AUTO_BANNER}\n\n{body}\n\n{AUTO_END}", dropped


def replace_auto_zone(
    document: str,
    notes: Sequence[MemoryNote],
    *,
    agent: str,
    stamp: str,
) -> tuple[str, int]:
    """Return *document* with its maintained zone replaced, plus notes dropped.

    A document with no markers keeps all of its content and gains a zone at the
    end, so a developer can hand-write memory without knowing the format and
    have the analyst adopt it on the next run.
    """
    block, dropped = render_auto_zone(notes, stamp=stamp)
    base = document if document.strip() else scaffold(agent)

    start = base.find(AUTO_START)
    end = base.find(AUTO_END, start + len(AUTO_START)) if start != -1 else -1
    if start == -1 or end == -1:
        head, tail = base, ""
    else:
        head, tail = base[:start], base[end + len(AUTO_END) :]

    sections = [section for section in (head.rstrip(), block, tail.strip()) if section]
    return "\n\n".join(sections) + "\n", dropped


def memory_remote_path(agent: str) -> str:
    """Return the fileset-relative path holding *agent*'s memory document.

    The agent identifier doubles as a directory name, and it is a local
    filesystem path rather than a registered name when the loop runs offline,
    so it is reduced to one safe segment.
    """
    segment = _UNSAFE_PATH_CHARS.sub("-", agent).strip("-") or "agent"
    return f"{segment}/{MEMORY_FILENAME}"


class MemoryStore(Protocol):
    """Where the analyst's memory document is read from and written back to."""

    async def read(self) -> str:
        """Return the current document, or an empty string when there is none."""
        ...

    async def write(self, notes: Sequence[MemoryNote]) -> str:
        """Persist *notes* as the maintained zone and return one report line."""
        ...


class FilesetMemoryStore:
    """Memory held at ``<agent>/AGENT-MEMORY.md`` on the ``nemo-agent-memory`` fileset.

    Reachable identically from a developer's laptop and from the scheduled
    analysis job, which is the whole point of not using a local file.
    """

    def __init__(self, *, client: AsyncNeMoPlatform, workspace: str, agent: str) -> None:
        self._client = client
        self._workspace = workspace
        self._agent = agent
        self.remote_path = memory_remote_path(agent)

    async def read(self) -> str:
        """Return the stored document, or an empty string if it cannot be read.

        A missing document is the ordinary first-run state and must not be
        noisy. A genuine outage is not swallowed in practice, because the write
        at the end of the run reports its own failure.
        """
        try:
            raw = await self._client.files.download_content(
                remote_path=self.remote_path,
                fileset=MEMORY_FILESET,
                workspace=self._workspace,
            )
        except _STORE_ERRORS:
            return ""
        return raw.decode("utf-8", errors="replace")

    async def write(self, notes: Sequence[MemoryNote]) -> str:
        """Replace the maintained zone with *notes* and report what happened.

        An empty *notes* leaves the document alone. The analyst is asked for the
        memory that should exist, so an empty list is indistinguishable from a
        model that skipped the field, and wiping a developer's accumulated
        context on that ambiguity is the worse failure. Clearing memory is a
        deliberate hand edit.

        Storage failures are reported rather than raised: by the time this runs
        the insights have already landed, and failing the run would misreport a
        successful analysis.
        """
        if not notes:
            return "- memory: unchanged (no notes returned)"

        document, dropped = replace_auto_zone(
            await self.read(),
            notes,
            agent=self._agent,
            stamp=_today(),
        )
        try:
            await self._client.files.upload_content(
                content=document,
                remote_path=self.remote_path,
                fileset=MEMORY_FILESET,
                workspace=self._workspace,
                fileset_auto_create=True,
            )
        except _STORE_ERRORS as exc:
            detail = " ".join(str(exc).split())
            return f"- warning: memory could not be written to {MEMORY_FILESET}#{self.remote_path}: {detail}"

        kept = len(notes) - dropped
        line = f"- memory: wrote {kept} note(s) to {MEMORY_FILESET}#{self.remote_path}"
        if dropped:
            line += f", dropped {dropped} over the {MAX_NOTES}-note / {MAX_AUTO_BYTES}-byte budget"
        return line


def _today() -> str:
    """Today's date in UTC, as an absolute stamp rather than a relative one."""
    return datetime.now(timezone.utc).date().isoformat()
