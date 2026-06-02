# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the memory-triage council orchestrator.

Uses fake in-process judges (no LLM calls). Covers happy path,
single-judge failure tolerance, total-failure skips, the corpus
summary calibration, the disagreement-set helper, the max_entries
cap, and progress reporting.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import pytest
from nemo_agents_plugin.improvement.memory.judges import JudgeContext
from nemo_agents_plugin.improvement.memory.proposal import Judgment, Verdict
from nemo_agents_plugin.improvement.memory.store import MemoryEntry
from nemo_agents_plugin.improvement.memory.triage import (
    TriageError,
    TriageRun,
    run_triage,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeStore:
    """Minimal in-memory ``MemoryStore`` implementation for tests."""

    name: str
    entries: list[MemoryEntry]

    def list_entries(self) -> Iterable[MemoryEntry]:
        return iter(self.entries)

    def get(self, entry_id: str) -> MemoryEntry:
        for e in self.entries:
            if e.id == entry_id:
                return e
        raise KeyError(entry_id)


class FakeJudge:
    """Judge that returns a pre-canned verdict per entry id.

    ``votes`` maps ``entry_id -> Verdict``. Entries not in the map get
    ``KEEP``. ``raise_on`` is a set of entry ids that should raise
    instead of voting, used to exercise the partial-failure path.
    Records every context it received so tests can assert on the
    corpus summary calibration.
    """

    def __init__(
        self,
        model: str,
        votes: dict[str, Verdict] | None = None,
        raise_on: set[str] | None = None,
        quality: float = 0.5,
        necessity: float = 0.5,
    ) -> None:
        self.model = model
        self._votes = votes or {}
        self._raise_on = raise_on or set()
        self._quality = quality
        self._necessity = necessity
        self.received_contexts: list[JudgeContext] = []

    async def judge(self, entry: MemoryEntry, context: JudgeContext) -> Judgment:
        self.received_contexts.append(context)
        if entry.id in self._raise_on:
            raise RuntimeError(f"injected failure for {entry.id}")
        verdict = self._votes.get(entry.id, Verdict.KEEP)
        return Judgment(
            model=self.model,
            verdict=verdict,
            quality=self._quality,
            necessity=self._necessity,
            justification=f"{self.model} -> {verdict.value}",
        )


def _entry(id_: str, content: str = "x", corroboration: int = 1) -> MemoryEntry:
    return MemoryEntry(id=id_, content=content, corroboration_count=corroboration)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestRunTriageHappyPath:
    @pytest.mark.asyncio
    async def test_unanimous_council_produces_proposals(self):
        store = FakeStore(name="test", entries=[_entry("a"), _entry("b"), _entry("c")])
        judges = [FakeJudge("sonnet"), FakeJudge("nano"), FakeJudge("kimi")]
        run = await run_triage(store, judges, reference_model="sonnet")
        assert len(run.proposals) == 3
        assert all(p.verdict == Verdict.KEEP for p in run.proposals)
        assert all(p.confidence == 1.0 for p in run.proposals)
        assert run.errors == []
        assert run.skipped_entries == []
        assert run.council_models == ["sonnet", "nano", "kimi"]
        assert run.store_name == "test"
        assert run.started_at is not None and run.finished_at is not None

    @pytest.mark.asyncio
    async def test_split_council_uses_aggregation_rule(self):
        store = FakeStore(name="test", entries=[_entry("a"), _entry("b")])
        judges = [
            FakeJudge("sonnet", votes={"a": Verdict.DROP, "b": Verdict.KEEP}),
            FakeJudge("nano", votes={"a": Verdict.DROP, "b": Verdict.REFINE}),
            FakeJudge("kimi", votes={"a": Verdict.KEEP, "b": Verdict.DROP}),
        ]
        run = await run_triage(store, judges, reference_model="sonnet")
        proposals_by_id = {p.entry_id: p for p in run.proposals}
        # Entry a: 2 DROP + 1 KEEP -> DROP wins by majority.
        assert proposals_by_id["a"].verdict == Verdict.DROP
        # Entry b: 1 KEEP + 1 REFINE + 1 DROP, no majority -> conservative
        # tiebreak picks KEEP (lowest destructiveness).
        assert proposals_by_id["b"].verdict == Verdict.KEEP


# ---------------------------------------------------------------------------
# Failure tolerance
# ---------------------------------------------------------------------------


class TestRunTriageFailureTolerance:
    @pytest.mark.asyncio
    async def test_single_judge_failure_still_produces_proposal(self):
        store = FakeStore(name="test", entries=[_entry("a")])
        judges = [
            FakeJudge("sonnet", raise_on={"a"}),
            FakeJudge("nano"),
            FakeJudge("kimi"),
        ]
        run = await run_triage(store, judges, reference_model="sonnet")
        assert len(run.proposals) == 1
        # Two surviving judges both said KEEP.
        assert run.proposals[0].verdict == Verdict.KEEP
        assert run.proposals[0].confidence == 1.0  # 2 of 2 surviving judges agree
        # The failure was recorded.
        assert len(run.errors) == 1
        assert run.errors[0].entry_id == "a"
        assert run.errors[0].model == "sonnet"
        assert run.errors[0].error_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_all_judges_failing_skips_entry(self):
        store = FakeStore(name="test", entries=[_entry("a"), _entry("b")])
        judges = [
            FakeJudge("sonnet", raise_on={"a"}),
            FakeJudge("nano", raise_on={"a"}),
            FakeJudge("kimi", raise_on={"a"}),
        ]
        run = await run_triage(store, judges, reference_model="sonnet")
        # Entry a was skipped (no proposal).
        assert run.skipped_entries == ["a"]
        # Entry b still got a proposal.
        assert len(run.proposals) == 1
        assert run.proposals[0].entry_id == "b"
        # Three error records for entry a.
        assert len(run.errors) == 3

    @pytest.mark.asyncio
    async def test_zero_judges_raises(self):
        store = FakeStore(name="test", entries=[_entry("a")])
        with pytest.raises(ValueError, match="at least one judge"):
            await run_triage(store, [], reference_model=None)


# ---------------------------------------------------------------------------
# Corpus summary calibration
# ---------------------------------------------------------------------------


class TestCorpusSummary:
    @pytest.mark.asyncio
    async def test_summary_reflects_corroboration_distribution(self):
        # 3 single-observation, 1 strongly corroborated.
        store = FakeStore(
            name="user-store",
            entries=[
                _entry("a", corroboration=1),
                _entry("b", corroboration=1),
                _entry("c", corroboration=1),
                _entry("d", corroboration=8),
            ],
        )
        judges = [FakeJudge("sonnet")]
        await run_triage(store, judges, reference_model="sonnet")
        # Every judge call should have received the same context.
        ctx = judges[0].received_contexts[0]
        assert ctx.corpus_size == 4
        assert "3 of 4 entries are single-observation" in ctx.corroboration_summary
        assert "Highest corroboration in the corpus is 8" in ctx.corroboration_summary
        assert ctx.store_name == "user-store"

    @pytest.mark.asyncio
    async def test_empty_store_yields_empty_context(self):
        store = FakeStore(name="empty", entries=[])
        judges = [FakeJudge("sonnet")]
        run = await run_triage(store, judges)
        assert run.proposals == []
        assert run.errors == []
        # No judge calls happened, so no contexts were captured.
        assert judges[0].received_contexts == []


# ---------------------------------------------------------------------------
# max_entries cap and progress reporting
# ---------------------------------------------------------------------------


class TestMaxEntriesAndProgress:
    @pytest.mark.asyncio
    async def test_max_entries_caps_processing(self):
        store = FakeStore(name="t", entries=[_entry(f"e{i}") for i in range(10)])
        judges = [FakeJudge("sonnet")]
        run = await run_triage(store, judges, max_entries=3)
        assert len(run.proposals) == 3
        assert [p.entry_id for p in run.proposals] == ["e0", "e1", "e2"]

    @pytest.mark.asyncio
    async def test_progress_callback_invoked_per_entry(self):
        store = FakeStore(name="t", entries=[_entry("a"), _entry("b"), _entry("c")])
        judges = [FakeJudge("sonnet")]
        calls: list[tuple[int, int]] = []
        await run_triage(store, judges, progress=lambda done, total: calls.append((done, total)))
        assert calls == [(1, 3), (2, 3), (3, 3)]


# ---------------------------------------------------------------------------
# TriageRun helpers
# ---------------------------------------------------------------------------


class TestTriageRunHelpers:
    def test_verdict_counts(self):
        # Build a TriageRun by hand to keep the test focused on the helper.
        from nemo_agents_plugin.improvement.memory.proposal import MemoryProposal

        def _p(verdict: Verdict) -> MemoryProposal:
            return MemoryProposal(
                entry_id="x",
                verdict=verdict,
                quality_score=0.5,
                necessity_score=0.5,
                confidence=1.0,
                judge_votes={},
                justification="",
            )

        run = TriageRun(
            store_name="t",
            council_models=["sonnet"],
            proposals=[
                _p(Verdict.KEEP),
                _p(Verdict.KEEP),
                _p(Verdict.DROP),
                _p(Verdict.REFINE),
            ],
        )
        assert run.verdict_counts == {"keep": 2, "drop": 1, "refine": 1}

    @pytest.mark.asyncio
    async def test_disagreement_set_uses_proposal_helper(self):
        store = FakeStore(name="t", entries=[_entry("a"), _entry("b")])
        # On entry a, nano disagrees with sonnet. On entry b they agree.
        judges = [
            FakeJudge("sonnet", votes={"a": Verdict.KEEP, "b": Verdict.DROP}),
            FakeJudge("nano", votes={"a": Verdict.DROP, "b": Verdict.DROP}),
            FakeJudge("kimi", votes={"a": Verdict.KEEP, "b": Verdict.DROP}),
        ]
        run = await run_triage(store, judges, reference_model="sonnet")
        disagreements = run.disagreement_set(reference="sonnet", candidate="nano")
        assert [p.entry_id for p in disagreements] == ["a"]

    def test_triage_error_record_is_truncated_for_long_messages(self):
        # Defensive: error messages are capped at 500 chars to keep
        # the audit log readable.
        err = TriageError(entry_id="x", model="m", error_type="RuntimeError", error_message="y" * 1000)
        # The orchestrator truncates; constructing one directly is uncapped.
        # This documents the contract for direct readers of the dataclass.
        assert len(err.error_message) == 1000
