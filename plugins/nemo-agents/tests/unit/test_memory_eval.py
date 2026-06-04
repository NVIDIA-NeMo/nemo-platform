# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the baseline-vs-candidate evaluation primitive.

Synthetic artifacts only; real-corpus regression coverage lives in the
phase1-smoke / baselines artifacts and the omnistation observation flow.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nemo_agents_plugin.improvement.memory.eval import (
    compare_runs,
    load_triage_artifact,
    to_markdown,
    write_report_artifacts,
)
from nemo_agents_plugin.improvement.memory.proposal import Verdict


def _proposal(
    eid: str,
    verdict: str,
    *,
    confidence: float = 1.0,
    justification: str = "",
) -> dict:
    """Build a minimal proposal dict matching report.write_artifacts shape."""
    return {
        "entry_id": eid,
        "verdict": verdict,
        "quality_score": 0.5,
        "necessity_score": 0.5,
        "confidence": confidence,
        "judge_votes": {},
        "justification": justification,
        "refined_text": None,
        "merge_with": [],
    }


def _artifact(
    proposals: list[dict],
    *,
    store_name: str = "pi-hermes:test",
    council: list[str] | None = None,
    elapsed_sec: float = 1.0,
) -> dict:
    """Build a minimal triage artifact JSON-able dict."""
    from collections import Counter

    counts = Counter(p["verdict"] for p in proposals)
    return {
        "store_name": store_name,
        "council_models": council or ["test-model"],
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "elapsed_sec": elapsed_sec,
        "verdict_counts": dict(counts),
        "proposals": proposals,
        "errors": [],
        "skipped_entries": [],
    }


def _write_artifact(path: Path, artifact: dict) -> Path:
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


class TestLoadTriageArtifact:
    def test_loads_valid_artifact(self, tmp_path: Path) -> None:
        a = _artifact([_proposal("e1", "keep")])
        p = _write_artifact(tmp_path / "a.json", a)
        loaded = load_triage_artifact(p)
        assert loaded["store_name"] == "pi-hermes:test"
        assert len(loaded["proposals"]) == 1

    def test_rejects_missing_required_keys(self, tmp_path: Path) -> None:
        # Missing 'proposals' should produce a clear error pointing at the
        # offending path, not a downstream KeyError inside compare_runs.
        bad = {"store_name": "x", "council_models": []}
        p = _write_artifact(tmp_path / "bad.json", bad)
        with pytest.raises(ValueError, match="missing required top-level keys"):
            load_triage_artifact(p)


class TestCompareRunsPerfectMatch:
    def test_strict_rate_one_when_runs_identical(self, tmp_path: Path) -> None:
        # Two artifacts with identical proposals should report 100% strict
        # agreement, zero deltas, all confusion on the diagonal.
        proposals = [
            _proposal("e1", "keep"),
            _proposal("e2", "promote_to_prompt"),
            _proposal("e3", "refine"),
            _proposal("e4", "drop"),
        ]
        a = _write_artifact(tmp_path / "a.json", _artifact(proposals))
        b = _write_artifact(tmp_path / "b.json", _artifact(proposals))

        r = compare_runs(a, b)

        assert r.common_entries == 4
        assert r.strict_agreements == 4
        assert r.strict_rate == 1.0
        assert r.retain_vs_drop_rate == 1.0
        assert r.promote_threshold_rate == 1.0
        assert r.deltas == []
        # All confusion on the diagonal; off-diagonal cells must be zero.
        for b_v in Verdict:
            for c_v in Verdict:
                if b_v == c_v:
                    continue
                assert r.confusion[b_v][c_v] == 0


class TestCompareRunsDisagreement:
    def test_strict_disagreement_recorded_as_delta(self, tmp_path: Path) -> None:
        # Same entry, different verdict in each run. The delta should
        # carry both verdicts plus both justifications inline.
        a = _write_artifact(
            tmp_path / "a.json",
            _artifact([_proposal("e1", "keep", justification="bv-just")]),
        )
        b = _write_artifact(
            tmp_path / "b.json",
            _artifact([_proposal("e1", "promote_to_prompt", justification="cv-just")]),
        )
        r = compare_runs(a, b)

        assert r.strict_agreements == 0
        assert r.strict_rate == 0.0
        assert len(r.deltas) == 1
        d = r.deltas[0]
        assert d.entry_id == "e1"
        assert d.baseline_verdict is Verdict.KEEP
        assert d.candidate_verdict is Verdict.PROMOTE_TO_PROMPT
        assert d.baseline_justification == "bv-just"
        assert d.candidate_justification == "cv-just"

    def test_retain_vs_drop_collapses_promote_keep_refine(self, tmp_path: Path) -> None:
        # keep -> promote_to_prompt is a strict disagreement but the two
        # are both "retain" verdicts; the retain-vs-drop metric should
        # treat that flip as agreement, only counting drop disagreements
        # as a flip in the 2-way view.
        proposals_a = [
            _proposal("e1", "keep"),
            _proposal("e2", "refine"),
            _proposal("e3", "drop"),
        ]
        proposals_b = [
            _proposal("e1", "promote_to_prompt"),
            _proposal("e2", "keep"),
            _proposal("e3", "drop"),
        ]
        a = _write_artifact(tmp_path / "a.json", _artifact(proposals_a))
        b = _write_artifact(tmp_path / "b.json", _artifact(proposals_b))
        r = compare_runs(a, b)

        # 1 strict match (e3: drop=drop), 2 deltas
        assert r.strict_agreements == 1
        assert len(r.deltas) == 2
        # Retain-vs-drop: all 3 entries agree on retain vs drop sides.
        assert r.retain_vs_drop_agreements == 3
        assert r.retain_vs_drop_rate == 1.0

    def test_promote_threshold_only_distinguishes_promote(self, tmp_path: Path) -> None:
        # keep <-> refine is strict-disagreement but neither is "promote",
        # so the promote-threshold metric reads it as agreement.
        a = _write_artifact(
            tmp_path / "a.json",
            _artifact([_proposal("e1", "keep"), _proposal("e2", "refine")]),
        )
        b = _write_artifact(
            tmp_path / "b.json",
            _artifact([_proposal("e1", "refine"), _proposal("e2", "promote_to_prompt")]),
        )
        r = compare_runs(a, b)

        # 0 strict matches.
        assert r.strict_agreements == 0
        # e1 (keep <-> refine): both non-promote => agree
        # e2 (refine <-> promote): one is promote => disagree
        assert r.promote_threshold_agreements == 1
        assert r.promote_threshold_rate == 0.5

    def test_deltas_sorted_by_band(self, tmp_path: Path) -> None:
        # Multiple delta types — assert the sort groups same-flip bands
        # together so reviewers see all keep->promote disagreements in a
        # cluster before moving to the next band.
        proposals_a = [
            _proposal("a1", "keep"),
            _proposal("a2", "refine"),
            _proposal("a3", "keep"),
            _proposal("a4", "refine"),
        ]
        proposals_b = [
            _proposal("a1", "promote_to_prompt"),
            _proposal("a2", "keep"),
            _proposal("a3", "promote_to_prompt"),
            _proposal("a4", "keep"),
        ]
        a = _write_artifact(tmp_path / "a.json", _artifact(proposals_a))
        b = _write_artifact(tmp_path / "b.json", _artifact(proposals_b))
        r = compare_runs(a, b)

        bands = [(d.baseline_verdict.value, d.candidate_verdict.value) for d in r.deltas]
        # Two keep->promote flips together, then two refine->keep flips.
        assert bands == [
            ("keep", "promote_to_prompt"),
            ("keep", "promote_to_prompt"),
            ("refine", "keep"),
            ("refine", "keep"),
        ]


class TestCompareRunsCoverage:
    def test_baseline_only_and_candidate_only_recorded(self, tmp_path: Path) -> None:
        # e2 is only in baseline; e3 is only in candidate. e1 is common.
        # Agreement rates must be computed over common entries only.
        a = _write_artifact(
            tmp_path / "a.json",
            _artifact([_proposal("e1", "keep"), _proposal("e2", "drop")]),
        )
        b = _write_artifact(
            tmp_path / "b.json",
            _artifact([_proposal("e1", "keep"), _proposal("e3", "drop")]),
        )
        r = compare_runs(a, b)

        assert r.common_entries == 1
        assert r.baseline_only_entries == ["e2"]
        assert r.candidate_only_entries == ["e3"]
        # The one common entry matches strictly.
        assert r.strict_rate == 1.0

    def test_no_common_entries_yields_zero_rates(self, tmp_path: Path) -> None:
        # If the two runs share nothing, all rates are 0.0 (and we must
        # not divide by zero). This guards against the eval bombing on a
        # stale artifact whose entry IDs no longer match the corpus.
        a = _write_artifact(tmp_path / "a.json", _artifact([_proposal("e1", "keep")]))
        b = _write_artifact(tmp_path / "b.json", _artifact([_proposal("e2", "keep")]))
        r = compare_runs(a, b)

        assert r.common_entries == 0
        assert r.strict_rate == 0.0
        assert r.retain_vs_drop_rate == 0.0
        assert r.promote_threshold_rate == 0.0
        assert r.deltas == []


class TestRenderingAndWrite:
    def test_to_markdown_includes_headline_rates(self, tmp_path: Path) -> None:
        a = _write_artifact(
            tmp_path / "a.json",
            _artifact([_proposal("e1", "keep"), _proposal("e2", "drop")]),
        )
        b = _write_artifact(
            tmp_path / "b.json",
            _artifact([_proposal("e1", "promote_to_prompt"), _proposal("e2", "drop")]),
        )
        r = compare_runs(a, b)
        md = to_markdown(r)

        assert "# Memory-triage agreement report" in md
        assert "Strict" in md
        assert "Retain vs drop" in md
        assert "Promote threshold" in md
        # The one delta should render under its band header.
        assert "`keep` -> `promote_to_prompt`" in md
        # Diagonal cell with non-zero count should be bold.
        assert "**1**" in md

    def test_to_markdown_no_disagreements_section_when_empty(self, tmp_path: Path) -> None:
        a = _write_artifact(tmp_path / "a.json", _artifact([_proposal("e1", "keep")]))
        b = _write_artifact(tmp_path / "b.json", _artifact([_proposal("e1", "keep")]))
        r = compare_runs(a, b)
        md = to_markdown(r)
        assert "None. Every common entry got the same verdict in both runs." in md

    def test_write_report_artifacts_creates_pair(self, tmp_path: Path) -> None:
        # Must mirror report.write_artifacts: produce both {basename}.json
        # and {basename}.md so the same fileset-upload helper works.
        a = _write_artifact(tmp_path / "a.json", _artifact([_proposal("e1", "keep")]))
        b = _write_artifact(tmp_path / "b.json", _artifact([_proposal("e1", "keep")]))
        r = compare_runs(a, b)

        out = tmp_path / "out"
        json_path, md_path = write_report_artifacts(r, out, basename="run1")
        assert json_path.exists()
        assert md_path.exists()
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["agreement"]["strict"]["rate"] == 1.0


class TestRealBaselineSmoke:
    """Quick smoke against the committed Sonnet baseline.

    Confirms the primitive handles real artifact JSON (real entry IDs,
    real verdict distribution) without changes, and that comparing the
    baseline to itself produces the expected 100% strict agreement.
    """

    def test_baseline_self_compare_is_perfect(self) -> None:
        baseline = Path(
            "plugins/nemo-agents/src/nemo_agents_plugin/improvement/memory/"
            "phase1-smoke/baselines/baseline-sonnet-4-6-user.json"
        )
        if not baseline.exists():
            pytest.skip("baseline artifact not present in this checkout")

        r = compare_runs(baseline, baseline)
        assert r.common_entries == 71
        assert r.strict_agreements == 71
        assert r.strict_rate == 1.0
        assert r.deltas == []
