# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the pi-hermes Markdown adapter.

Inline fixtures cover the two observed footer formats (PoC seen-in
counts; SQLite-export created/last dates) plus edge cases (no footer,
empty entries, blank trailing chunks). An opt-in smoke test exercises
the real consolidated corpus when present on the developer's machine.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from nemo_memory_plugin.triage.adapters.pi_hermes import PiHermesMemoryStore


def _write_fixture(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


class TestSeenInFormat:
    """Cover the PoC consolidate-pipeline footer format."""

    def test_parses_seen_in_sessions_plural(self, tmp_path):
        body = (
            "Keeps user in the loop. "
            "Wants gaps surfaced rather than guessed. <!-- seen-in: 8 sessions -->\n"
            "§\n"
            "Prefers terse output. <!-- seen-in: 3 sessions -->\n"
        )
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="pi-hermes:user")
        entries = list(store.list_entries())
        assert len(entries) == 2
        assert entries[0].corroboration_count == 8
        assert entries[1].corroboration_count == 3
        # The HTML comment must be stripped from content.
        assert "<!--" not in entries[0].content
        assert entries[0].content.endswith("guessed.")

    def test_parses_seen_in_session_singular(self, tmp_path):
        body = "Single observation. <!-- seen-in: 1 session -->\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert len(entries) == 1
        assert entries[0].corroboration_count == 1

    def test_parses_seen_in_bare_count(self, tmp_path):
        # Older consolidate.mjs format omitted the trailing word.
        body = "Older format. <!-- seen-in: 5 -->\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert entries[0].corroboration_count == 5


class TestSqliteExportFormat:
    """Cover the live pi-hermes-memory export footer format."""

    def test_parses_created_and_last(self, tmp_path):
        body = "Some fact. <!-- created=2026-05-29, last=2026-06-01 -->\n"
        path = _write_fixture(tmp_path, "MEMORY.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert len(entries) == 1
        e = entries[0]
        assert e.content == "Some fact."
        assert e.created_at == datetime(2026, 5, 29, tzinfo=timezone.utc)
        assert e.last_used_at == datetime(2026, 6, 1, tzinfo=timezone.utc)
        # No seen-in marker present, so corroboration defaults to 1.
        assert e.corroboration_count == 1

    def test_missing_last_does_not_crash(self, tmp_path):
        # Defensive: not every export carries both fields.
        body = "Partial footer. <!-- created=2026-05-29 -->\n"
        path = _write_fixture(tmp_path, "MEMORY.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert entries[0].created_at == datetime(2026, 5, 29, tzinfo=timezone.utc)
        assert entries[0].last_used_at is None


class TestEntryShapeEdges:
    def test_no_footer_defaults_to_corroboration_one(self, tmp_path):
        body = "Bare entry with no metadata footer.\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert len(entries) == 1
        assert entries[0].corroboration_count == 1
        assert entries[0].created_at is None
        assert entries[0].last_used_at is None

    def test_empty_chunks_are_skipped(self, tmp_path):
        # Leading whitespace, trailing whitespace, and consecutive
        # separators must not yield empty entries.
        body = "\n\n§\n\nReal entry.\n§\n  §  \n§\n\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert len(entries) == 1
        assert entries[0].content == "Real entry."

    def test_comment_only_chunk_is_skipped(self, tmp_path):
        # An HTML-comment-only chunk has no actual content. Skip it.
        body = "Real entry.\n§\n<!-- seen-in: 1 session -->\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert len(entries) == 1

    def test_missing_file_yields_no_entries(self, tmp_path):
        # Construction must not raise on a missing path; the store is
        # lazy-read. ``list_entries`` returns nothing.
        store = PiHermesMemoryStore(path=tmp_path / "absent.md", name="x")
        assert list(store.list_entries()) == []


class TestIdentityAndLookup:
    def test_ids_are_stable_across_calls(self, tmp_path):
        body = "Stable content. <!-- seen-in: 2 sessions -->\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        first = list(store.list_entries())
        second = list(store.list_entries())
        assert first[0].id == second[0].id

    def test_ids_ignore_source_file_name(self, tmp_path):
        # Same content in two different files should hash to the same id;
        # the source filename only lives in ``tags`` for disambiguation.
        body = "Identical content.\n"
        p1 = _write_fixture(tmp_path, "USER.md", body)
        p2 = _write_fixture(tmp_path, "MEMORY.md", body)
        e1 = list(PiHermesMemoryStore(path=p1, name="a").list_entries())[0]
        e2 = list(PiHermesMemoryStore(path=p2, name="b").list_entries())[0]
        assert e1.id == e2.id
        assert e1.tags["source_file"] != e2.tags["source_file"]

    def test_get_returns_matching_entry(self, tmp_path):
        body = "First entry.\n§\nSecond entry.\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        target = entries[1]
        assert store.get(target.id).content == "Second entry."

    def test_get_unknown_id_raises_keyerror(self, tmp_path):
        body = "Only entry.\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        with pytest.raises(KeyError):
            store.get("nonexistent")


class TestMultiLineContent:
    def test_preserves_internal_newlines(self, tmp_path):
        body = "Paragraph one.\n\nParagraph two with more detail.\n<!-- seen-in: 4 sessions -->\n§\nNext entry.\n"
        path = _write_fixture(tmp_path, "USER.md", body)
        store = PiHermesMemoryStore(path=path, name="x")
        entries = list(store.list_entries())
        assert len(entries) == 2
        assert "\n\n" in entries[0].content
        assert entries[0].content.startswith("Paragraph one")
        assert entries[0].content.endswith("more detail.")


# ---------------------------------------------------------------------------
# Opt-in smoke test against the real consolidated corpus on the developer's
# machine. Skipped in CI and when the corpus is absent. Verifies that the
# adapter parses without raising and that the entry count is in a plausible
# band — we are not asserting the corpus content itself, only that the
# adapter survives it.
# ---------------------------------------------------------------------------

_CONSOLIDATED_DIR = Path.home() / ".pi" / "agent" / "claude-session-replays" / "CONSOLIDATED"


@pytest.mark.skipif(
    not (_CONSOLIDATED_DIR / "USER.md").exists() or bool(os.environ.get("CI")),
    reason="real PoC corpus not present (or running in CI)",
)
class TestRealCorpusSmoke:
    def test_user_corpus_parses(self):
        path = _CONSOLIDATED_DIR / "USER.md"
        store = PiHermesMemoryStore(path=path, name="pi-hermes:CONSOLIDATED:user")
        entries = list(store.list_entries())
        # The PoC report listed USER.md at 71 entries post-dedup. We allow a
        # generous band because the corpus may have been re-run since.
        assert 30 <= len(entries) <= 200, f"unexpected count: {len(entries)}"
        # Every entry has a stable id and non-empty content.
        ids = {e.id for e in entries}
        assert len(ids) == len(entries), "id collisions in real corpus"
        assert all(e.content.strip() for e in entries)

    def test_memory_corpus_parses(self):
        path = _CONSOLIDATED_DIR / "MEMORY.md"
        store = PiHermesMemoryStore(path=path, name="pi-hermes:CONSOLIDATED:memory")
        entries = list(store.list_entries())
        assert len(entries) > 0
        assert all(e.id and e.content for e in entries)

    def test_failures_corpus_parses(self):
        path = _CONSOLIDATED_DIR / "failures.md"
        store = PiHermesMemoryStore(path=path, name="pi-hermes:CONSOLIDATED:failures")
        entries = list(store.list_entries())
        assert len(entries) > 0
