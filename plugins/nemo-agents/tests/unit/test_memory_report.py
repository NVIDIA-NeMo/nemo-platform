# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the JSON and Markdown report emitters.

Builds TriageRun fixtures by hand and asserts on the emitted shape.
No LLM calls, no filesystem mocks beyond the real tmp_path fixture.
"""

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from nemo_agents_plugin.improvement.memory.proposal import Judgment, MemoryProposal, Verdict
from nemo_agents_plugin.improvement.memory.report import (
    to_json,
    to_markdown,
    write_artifacts,
)
from nemo_agents_plugin.improvement.memory.triage import TriageError, TriageRun

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _proposal(
    entry_id: str,
    verdict: Verdict,
    *,
    confidence: float = 1.0,
    refined_text: str | None = None,
    merge_with: list[str] | None = None,
    quality: float = 0.7,
    necessity: float = 0.6,
) -> MemoryProposal:
    return MemoryProposal(
        entry_id=entry_id,
        verdict=verdict,
        quality_score=quality,
        necessity_score=necessity,
        confidence=confidence,
        judge_votes={
            "sonnet": Judgment(
                model="sonnet",
                verdict=verdict,
                quality=quality,
                necessity=necessity,
                justification=f"sonnet says {verdict.value}",
                elapsed_sec=1.5,
            )
        },
        justification=f"council says {verdict.value}",
        refined_text=refined_text,
        merge_with=list(merge_with or []),
    )


def _run(proposals: list[MemoryProposal], **overrides: Any) -> TriageRun:
    defaults: dict[str, Any] = {
        "store_name": "pi-hermes:user",
        "council_models": ["sonnet", "nano", "kimi"],
        "proposals": proposals,
        "started_at": datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 6, 2, 12, 5, tzinfo=timezone.utc),
        "elapsed_sec": 300.0,
    }
    defaults.update(overrides)
    return TriageRun(**defaults)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


class TestToJson:
    def test_round_trips_through_json_load(self):
        run = _run([_proposal("a", Verdict.KEEP), _proposal("b", Verdict.DROP)])
        text = to_json(run)
        data = json.loads(text)
        assert data["store_name"] == "pi-hermes:user"
        assert data["council_models"] == ["sonnet", "nano", "kimi"]
        assert len(data["proposals"]) == 2
        # Verdicts are serialized as the enum value (lowercase string).
        assert data["proposals"][0]["verdict"] == "keep"
        assert data["proposals"][1]["verdict"] == "drop"
        # Verdict counts are inlined.
        assert data["verdict_counts"] == {"keep": 1, "drop": 1}

    def test_datetimes_serialize_as_isoformat(self):
        run = _run([_proposal("a", Verdict.KEEP)])
        data = json.loads(to_json(run))
        assert data["started_at"].startswith("2026-06-02T12:00:00")
        assert data["finished_at"].startswith("2026-06-02T12:05:00")

    def test_judgment_dataclass_is_recursively_expanded(self):
        run = _run([_proposal("a", Verdict.KEEP)])
        data = json.loads(to_json(run))
        votes = data["proposals"][0]["judge_votes"]
        assert "sonnet" in votes
        # The Judgment dataclass should be fully expanded, including the
        # nested verdict enum.
        assert votes["sonnet"]["verdict"] == "keep"
        assert votes["sonnet"]["model"] == "sonnet"

    def test_errors_serialize(self):
        run = _run(
            [],
            errors=[TriageError(entry_id="x", model="sonnet", error_type="RuntimeError", error_message="boom")],
        )
        data = json.loads(to_json(run))
        assert data["errors"][0]["entry_id"] == "x"
        assert data["errors"][0]["error_type"] == "RuntimeError"

    def test_unknown_type_raises_typeerror(self):
        # Use a non-dataclass object that json can't handle natively. The
        # default fallback should re-raise TypeError rather than silently
        # producing nonsense.
        class Opaque:
            pass

        run = _run([_proposal("a", Verdict.KEEP)])
        run.proposals[0].judge_votes["bad"] = Opaque()  # type: ignore[assignment]
        with pytest.raises(TypeError, match="not JSON serializable"):
            to_json(run)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


class TestToMarkdown:
    def test_header_carries_run_metadata(self):
        run = _run([_proposal("a", Verdict.KEEP)])
        md = to_markdown(run)
        assert "# Memory triage proposals" in md
        assert "`pi-hermes:user`" in md
        assert "`sonnet`" in md and "`nano`" in md and "`kimi`" in md
        assert "elapsed:" in md
        # The summary table appears before any per-verdict section.
        summary_pos = md.index("## Summary")
        first_section_pos = md.index("## `")
        assert summary_pos < first_section_pos

    def test_verdict_sections_emitted_in_display_order(self):
        # Display order: drop, merge, refine, promote, keep.
        run = _run(
            [
                _proposal("k1", Verdict.KEEP),
                _proposal("d1", Verdict.DROP),
                _proposal("r1", Verdict.REFINE, refined_text="rewrite"),
                _proposal("p1", Verdict.PROMOTE_TO_PROMPT),
                _proposal("m1", Verdict.MERGE, merge_with=["other"]),
            ]
        )
        md = to_markdown(run)
        # Each verdict has its own section heading.
        order = ["`drop` (1)", "`merge` (1)", "`refine` (1)", "`promote_to_prompt` (1)", "`keep` (1)"]
        positions = [md.index(label) for label in order]
        assert positions == sorted(positions), f"sections out of order: {positions}"

    def test_drop_section_omitted_when_empty(self):
        # When no proposals carry a verdict, that section is suppressed
        # entirely (not rendered as an empty heading).
        run = _run([_proposal("k1", Verdict.KEEP)])
        md = to_markdown(run)
        assert "`keep` (1)" in md
        assert "`drop` (" not in md
        assert "`refine` (" not in md

    def test_entry_content_inlined_when_provided(self):
        run = _run([_proposal("a", Verdict.DROP)])
        md = to_markdown(run, entries_by_id={"a": "the original entry text"})
        assert "the original entry text" in md
        # Multi-line content gets blockquote-prefixed.
        run2 = _run([_proposal("b", Verdict.DROP)])
        md2 = to_markdown(run2, entries_by_id={"b": "line one\nline two"})
        assert "> line one\n> line two" in md2

    def test_refined_text_rendered_for_refine_verdict(self):
        run = _run([_proposal("a", Verdict.REFINE, refined_text="Sharper phrasing.")])
        md = to_markdown(run)
        assert "**Refined text proposed:**" in md
        assert "Sharper phrasing." in md

    def test_merge_with_listed_for_merge_verdict(self):
        run = _run([_proposal("a", Verdict.MERGE, merge_with=["b", "c"])])
        md = to_markdown(run)
        assert "**merge with:** `b`, `c`" in md

    def test_judge_audit_trail_rendered(self):
        run = _run([_proposal("a", Verdict.KEEP)])
        md = to_markdown(run)
        assert "**Judge votes:**" in md
        assert "`sonnet`" in md
        assert "1.5s" in md

    def test_skipped_entries_section_present(self):
        run = _run([], skipped_entries=["x", "y"])
        md = to_markdown(run)
        assert "## Skipped entries" in md
        assert "`x`" in md and "`y`" in md

    def test_error_table_escapes_pipe_and_newline(self):
        run = _run(
            [],
            errors=[
                TriageError(
                    entry_id="x",
                    model="sonnet",
                    error_type="RuntimeError",
                    error_message="bad | content\nwith newline",
                )
            ],
        )
        md = to_markdown(run)
        # Pipes inside the message must be escaped or they break the
        # Markdown table structure.
        assert "bad \\| content with newline" in md
        # The literal newline must not appear inside the table row.
        error_section = md[md.index("## Per-judge errors") :]
        rows = [r for r in error_section.split("\n") if r.startswith("|")]
        assert all("\n" not in r for r in rows)

    def test_proposals_sorted_by_confidence_within_verdict(self):
        run = _run(
            [
                _proposal("low", Verdict.DROP, confidence=0.33),
                _proposal("high", Verdict.DROP, confidence=1.0),
                _proposal("mid", Verdict.DROP, confidence=0.67),
            ]
        )
        md = to_markdown(run)
        # Highest confidence appears first inside the drop section.
        high_pos = md.index("`high`")
        mid_pos = md.index("`mid`")
        low_pos = md.index("`low`")
        assert high_pos < mid_pos < low_pos


# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------


class TestWriteArtifacts:
    def test_creates_both_files(self, tmp_path):
        run = _run([_proposal("a", Verdict.KEEP)])
        json_path, md_path = write_artifacts(run, tmp_path)
        assert json_path.exists()
        assert md_path.exists()
        assert json_path.name == "triage.json"
        assert md_path.name == "triage.md"
        # The JSON is valid and contains the proposal.
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["proposals"][0]["entry_id"] == "a"
        # The Markdown carries the run header.
        assert "Memory triage proposals" in md_path.read_text(encoding="utf-8")

    def test_creates_missing_directory(self, tmp_path):
        nested = tmp_path / "nested" / "deeper"
        run = _run([_proposal("a", Verdict.KEEP)])
        write_artifacts(run, nested)
        assert nested.is_dir()

    def test_basename_override(self, tmp_path):
        run = _run([_proposal("a", Verdict.KEEP)])
        json_path, md_path = write_artifacts(run, tmp_path, basename="triage-user")
        assert json_path.name == "triage-user.json"
        assert md_path.name == "triage-user.md"
