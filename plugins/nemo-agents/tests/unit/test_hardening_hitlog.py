# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from nemo_agents_plugin.hardening.hitlog import parse_hitlog

FIXTURE = Path(__file__).parent / "fixtures" / "hardening" / "sample.hitlog.jsonl"


def test_parse_hitlog_returns_ordered_structured_hits():
    """Each hitlog line becomes an AttackHit with probe/detector/prompt and a running index."""
    hits = parse_hitlog(FIXTURE)
    assert len(hits) == 2
    assert hits[0].probe == "promptinject.HijackHateHumans"
    assert hits[0].detector == "promptinject.AttackRogueString"
    assert "bash_executor" in hits[0].prompt
    assert hits[0].index == 0
    assert hits[1].probe == "dan.DanInTheWild"
    assert hits[1].index == 1


def test_parse_hitlog_skips_blank_and_malformed_lines(tmp_path):
    """Blank and non-JSON lines are skipped; a partial hitlog still yields its valid hits."""
    p = tmp_path / "partial.hitlog.jsonl"
    p.write_text('\n{"probe_classname": "x.Y", "prompt": "a", "output": "b", "detector": "d"}\nnot json\n')
    hits = parse_hitlog(p)
    assert len(hits) == 1
    assert hits[0].probe == "x.Y"
    assert hits[0].index == 0


def test_parse_hitlog_ordering_is_deterministic():
    """Index order is stable across parses (Requirement 7 determinism)."""
    assert [h.index for h in parse_hitlog(FIXTURE)] == [0, 1]


def test_parse_hitlog_empty_file_returns_empty(tmp_path):
    """An empty hitlog yields no hits rather than raising."""
    p = tmp_path / "empty.hitlog.jsonl"
    p.write_text("")
    assert parse_hitlog(p) == []


def test_parse_hitlog_missing_fields_default_to_empty_strings(tmp_path):
    """A hit missing prompt/output/detector parses to empty strings, and probe falls back."""
    p = tmp_path / "sparse.hitlog.jsonl"
    p.write_text('{"probe": "only.Probe"}\n')
    hits = parse_hitlog(p)
    assert hits[0].probe == "only.Probe"
    assert hits[0].prompt == "" and hits[0].output == "" and hits[0].detector == ""
    assert hits[0].tool is None


def test_parse_hitlog_preserves_unicode_prompt(tmp_path):
    """Non-ASCII jailbreak prompts survive parsing unchanged."""
    p = tmp_path / "unicode.hitlog.jsonl"
    p.write_text('{"probe_classname": "p.Q", "prompt": "caf\\u00e9 signe", "output": "o", "detector": "d"}\n')
    assert "café" in parse_hitlog(p)[0].prompt
