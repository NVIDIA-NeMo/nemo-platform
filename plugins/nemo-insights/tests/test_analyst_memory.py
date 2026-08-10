# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The memory document format and the fileset store's failure behaviour."""

from typing import Any, cast

import httpx
import pytest
from nemo_insights_plugin.analyst import memory as memory_module
from nemo_insights_plugin.analyst.memory import (
    AUTO_END,
    AUTO_START,
    EMPTY_ZONE,
    MAX_NOTES,
    FilesetMemoryStore,
    memory_remote_path,
    replace_auto_zone,
)
from nemo_insights_plugin.analyst.result import MemoryNote
from nemo_platform import AsyncNeMoPlatform

STAMP = "2026-08-10"

HUMAN_ZONE = """# Agent memory: research-agent

## Context from the developer
- `search_web` times out at 30s deliberately. Not a bug.
"""


def _document(notes: list[MemoryNote], *, existing: str = "") -> str:
    return replace_auto_zone(existing, notes, agent="research-agent", stamp=STAMP)[0]


def _auto_zone(document: str) -> str:
    return document[document.index(AUTO_START) : document.index(AUTO_END) + len(AUTO_END)]


def test_rewrite_preserves_the_developer_zone_and_replaces_only_the_maintained_one() -> None:
    first = _document([MemoryNote(note="eval spans are synthetic", source="t1")], existing=HUMAN_ZONE)
    second = _document([MemoryNote(note="sessions carry one trace")], existing=first)

    assert second.startswith(HUMAN_ZONE.rstrip())
    assert "search_web" in second
    assert "eval spans are synthetic" not in second
    assert "- sessions carry one trace (2026-08-10)" in _auto_zone(second)
    assert second.count(AUTO_START) == 1


def test_missing_document_gets_a_scaffold_and_an_empty_list_renders_a_placeholder() -> None:
    document = _document([])

    assert document.startswith("# Agent memory: research-agent")
    assert EMPTY_ZONE in _auto_zone(document)


def test_hand_written_document_without_markers_keeps_its_content_and_gains_a_zone() -> None:
    document = _document([MemoryNote(note="a fact")], existing="# Notes\n\nkeep me\n")

    assert document.startswith("# Notes\n\nkeep me")
    assert "- a fact (2026-08-10)" in _auto_zone(document)


def test_content_after_the_maintained_zone_survives_a_rewrite() -> None:
    existing = f"{HUMAN_ZONE}\n{AUTO_START}\nold\n{AUTO_END}\n\n## Appendix\n- mine\n"

    document = _document([MemoryNote(note="fresh")], existing=existing)

    assert "old" not in document
    assert document.rstrip().endswith("## Appendix\n- mine")


def test_over_budget_notes_are_dropped_in_rank_order_and_counted() -> None:
    notes = [MemoryNote(note=f"note {index}") for index in range(MAX_NOTES + 5)]

    document, dropped = replace_auto_zone("", notes, agent="research-agent", stamp=STAMP)

    assert dropped == 5
    assert "- note 0 (2026-08-10)" in document
    assert f"- note {MAX_NOTES} " not in document


def test_note_is_flattened_to_one_bullet_so_it_cannot_break_the_markers() -> None:
    document = _document([MemoryNote(note="first line\nsecond line", source="t1\nt2")])

    assert "- first line second line (2026-08-10; t1 t2)" in document


def test_remote_path_reduces_an_offline_agent_directory_to_one_safe_segment() -> None:
    assert memory_remote_path("research-agent") == "research-agent/AGENT-MEMORY.md"
    assert memory_remote_path("/home/me/agents/bot") == "home-me-agents-bot/AGENT-MEMORY.md"


class FakeFiles:
    def __init__(self, *, stored: str | None = None, upload_error: Exception | None = None) -> None:
        self.stored = stored
        self.upload_error = upload_error
        self.uploads: list[dict[str, Any]] = []

    async def download_content(self, *, remote_path: str, fileset: str, workspace: str) -> bytes:
        if self.stored is None:
            raise FileNotFoundError(remote_path)
        return self.stored.encode("utf-8")

    async def upload_content(self, *, content: str, **kwargs: Any) -> None:
        if self.upload_error is not None:
            raise self.upload_error
        self.uploads.append({"content": content, **kwargs})
        self.stored = content


def _store(files: FakeFiles) -> FilesetMemoryStore:
    client = cast(AsyncNeMoPlatform, type("FakeClient", (), {"files": files})())
    return FilesetMemoryStore(client=client, workspace="default", agent="research-agent")


async def test_absent_document_reads_as_empty_rather_than_raising() -> None:
    assert await _store(FakeFiles()).read() == ""


async def test_empty_note_list_leaves_the_document_untouched() -> None:
    files = FakeFiles(stored=HUMAN_ZONE)

    line = await _store(files).write([])

    assert files.uploads == []
    assert "unchanged" in line


async def test_write_uploads_to_the_agent_path_and_reports_the_budget() -> None:
    files = FakeFiles(stored=HUMAN_ZONE)
    notes = [MemoryNote(note=f"note {index}") for index in range(MAX_NOTES + 2)]

    line = await _store(files).write(notes)

    upload = files.uploads[0]
    assert upload["remote_path"] == "research-agent/AGENT-MEMORY.md"
    assert upload["fileset"] == memory_module.MEMORY_FILESET
    assert upload["fileset_auto_create"] is True
    assert "search_web" in upload["content"]
    assert f"wrote {MAX_NOTES} note(s)" in line
    assert "dropped 2" in line


async def test_unwritable_fileset_warns_instead_of_failing_the_run() -> None:
    files = FakeFiles(stored=HUMAN_ZONE, upload_error=httpx.ConnectError("no route"))

    line = await _store(files).write([MemoryNote(note="a fact")])

    assert line.startswith("- warning: memory could not be written")
    assert "no route" in line


@pytest.mark.parametrize("failure", [httpx.ConnectError("down"), ValueError("bad fileset")])
async def test_unreadable_document_degrades_to_empty(failure: Exception) -> None:
    files = FakeFiles()

    async def failing_download(**kwargs: Any) -> bytes:
        raise failure

    files.download_content = failing_download  # ty: ignore[invalid-assignment]

    assert await _store(files).read() == ""
