# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the memory-triage proposal aggregation.

Covers the conservative-tiebreak rule (DESIGN.md), confidence math, and
the source-of-truth selection for supporting fields (refined_text,
merge_with, justification). Pure-Python; no LLM calls.
"""

import pytest
from nemo_agents_plugin.improvement.memory.proposal import (
    Judgment,
    MemoryProposal,
    Verdict,
    aggregate,
)


def _j(
    model: str,
    verdict: Verdict,
    *,
    quality: float = 0.5,
    necessity: float = 0.5,
    justification: str = "",
    refined_text: str | None = None,
    merge_with: list[str] | None = None,
) -> Judgment:
    """Compact judgment factory for tests — fills the noisy defaults."""
    return Judgment(
        model=model,
        verdict=verdict,
        quality=quality,
        necessity=necessity,
        justification=justification or f"{model} says {verdict.value}",
        refined_text=refined_text,
        merge_with=list(merge_with or []),
    )


class TestAggregateMajority:
    def test_unanimous(self):
        judgments = {
            "sonnet": _j("sonnet", Verdict.KEEP),
            "nano": _j("nano", Verdict.KEEP),
            "kimi": _j("kimi", Verdict.KEEP),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.verdict == Verdict.KEEP
        assert p.confidence == 1.0
        assert p.entry_id == "e1"

    def test_two_of_three_majority(self):
        judgments = {
            "sonnet": _j("sonnet", Verdict.DROP),
            "nano": _j("nano", Verdict.DROP),
            "kimi": _j("kimi", Verdict.KEEP),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.verdict == Verdict.DROP
        assert p.confidence == pytest.approx(2 / 3)


class TestAggregateConservativeTiebreak:
    """When no verdict has a strict majority, the conservativeness order wins."""

    def test_three_way_tie_picks_keep(self):
        # 1/1/1 across keep, drop, refine — keep is the least destructive.
        judgments = {
            "sonnet": _j("sonnet", Verdict.DROP),
            "nano": _j("nano", Verdict.KEEP),
            "kimi": _j("kimi", Verdict.REFINE),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.verdict == Verdict.KEEP
        assert p.confidence == pytest.approx(1 / 3)

    def test_two_judge_tie_picks_more_conservative(self):
        judgments = {
            "sonnet": _j("sonnet", Verdict.DROP),
            "nano": _j("nano", Verdict.MERGE),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        # merge is more conservative than drop.
        assert p.verdict == Verdict.MERGE
        assert p.confidence == 0.5

    def test_promote_beats_refine_in_tie(self):
        # Promotion does not remove content; refine rewrites. Promote wins.
        judgments = {
            "a": _j("a", Verdict.PROMOTE_TO_PROMPT),
            "b": _j("b", Verdict.REFINE),
        }
        p = aggregate("e1", judgments)
        assert p.verdict == Verdict.PROMOTE_TO_PROMPT


class TestAggregateSupportingFields:
    """When the aggregate verdict needs a refined_text / merge_with /
    justification, those come from the reference judge if it voted with
    the winner, else from the first agreeing judge (insertion order)."""

    def test_refined_text_from_reference_when_reference_agrees(self):
        judgments = {
            "sonnet": _j(
                "sonnet",
                Verdict.REFINE,
                refined_text="sonnet rewrite",
                justification="sonnet says",
            ),
            "nano": _j(
                "nano",
                Verdict.REFINE,
                refined_text="nano rewrite",
                justification="nano says",
            ),
            "kimi": _j("kimi", Verdict.KEEP),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.verdict == Verdict.REFINE
        assert p.refined_text == "sonnet rewrite"
        assert p.justification == "sonnet says"

    def test_refined_text_falls_back_when_reference_dissents(self):
        # Reference disagrees with the winning verdict. Fall back to the
        # first judge (by insertion order) that voted for the winner.
        judgments = {
            "nano": _j("nano", Verdict.REFINE, refined_text="nano rewrite", justification="nano says"),
            "kimi": _j("kimi", Verdict.REFINE, refined_text="kimi rewrite", justification="kimi says"),
            "sonnet": _j("sonnet", Verdict.KEEP),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.verdict == Verdict.REFINE
        assert p.refined_text == "nano rewrite"
        assert p.justification == "nano says"

    def test_merge_with_only_populated_when_verdict_is_merge(self):
        # A judge that voted REFINE may have merge_with set in error;
        # aggregator must not surface that on a non-MERGE verdict.
        judgments = {
            "sonnet": _j("sonnet", Verdict.REFINE, refined_text="x", merge_with=["other"]),
            "nano": _j("nano", Verdict.REFINE, refined_text="x", merge_with=["other"]),
            "kimi": _j("kimi", Verdict.DROP),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.verdict == Verdict.REFINE
        assert p.merge_with == []

    def test_refined_text_cleared_when_verdict_is_keep(self):
        # Even if every judge supplied a refined_text, KEEP must not
        # carry one — KEEP means "no edit".
        judgments = {
            "sonnet": _j("sonnet", Verdict.KEEP, refined_text="should be dropped"),
            "nano": _j("nano", Verdict.KEEP, refined_text="should be dropped"),
            "kimi": _j("kimi", Verdict.KEEP, refined_text="should be dropped"),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.refined_text is None


class TestAggregateScoreAveraging:
    def test_quality_and_necessity_averaged(self):
        judgments = {
            "sonnet": _j("sonnet", Verdict.KEEP, quality=1.0, necessity=0.8),
            "nano": _j("nano", Verdict.KEEP, quality=0.4, necessity=0.2),
            "kimi": _j("kimi", Verdict.KEEP, quality=0.7, necessity=0.5),
        }
        p = aggregate("e1", judgments, reference_model="sonnet")
        assert p.quality_score == pytest.approx((1.0 + 0.4 + 0.7) / 3)
        assert p.necessity_score == pytest.approx((0.8 + 0.2 + 0.5) / 3)


class TestAggregateGuards:
    def test_empty_judgments_raises(self):
        with pytest.raises(ValueError):
            aggregate("e1", {})


class TestDisagreementDetection:
    def test_disagreement_true_when_models_diverge(self):
        p = MemoryProposal(
            entry_id="e1",
            verdict=Verdict.KEEP,
            quality_score=0.5,
            necessity_score=0.5,
            confidence=0.66,
            judge_votes={
                "sonnet": _j("sonnet", Verdict.KEEP),
                "nano": _j("nano", Verdict.DROP),
            },
            justification="",
        )
        assert p.is_candidate_disagreement("sonnet", "nano") is True

    def test_disagreement_false_when_models_agree(self):
        p = MemoryProposal(
            entry_id="e1",
            verdict=Verdict.KEEP,
            quality_score=0.5,
            necessity_score=0.5,
            confidence=1.0,
            judge_votes={
                "sonnet": _j("sonnet", Verdict.KEEP),
                "nano": _j("nano", Verdict.KEEP),
            },
            justification="",
        )
        assert p.is_candidate_disagreement("sonnet", "nano") is False

    def test_missing_vote_treated_as_non_disagreement(self):
        # A parser failure should not pollute the fine-tune training set.
        p = MemoryProposal(
            entry_id="e1",
            verdict=Verdict.KEEP,
            quality_score=0.5,
            necessity_score=0.5,
            confidence=1.0,
            judge_votes={"sonnet": _j("sonnet", Verdict.KEEP)},
            justification="",
        )
        assert p.is_candidate_disagreement("sonnet", "nano") is False
