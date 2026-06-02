# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Memory triage proposals.

A ``MemoryProposal`` is the staged-mutation artifact emitted by the
council. It carries one verdict per memory entry plus the full per-judge
audit trail so a human reviewer can see who voted what and why. Proposals
are *never* applied directly by code; see ``DESIGN.md`` Phase 0 for the
mutation contract.

Aggregation rule (DESIGN.md):

- Strict majority (>50% of judges) wins outright.
- Ties resolve by conservativeness, least-destructive first:
  ``keep`` < ``promote_to_prompt`` < ``refine`` < ``merge`` < ``drop``.
- Confidence is the fraction of judges in agreement with the winning
  verdict.

Refined text, merge targets, and the human-readable justification are
sourced from the *reference judge* (the highest-quality slot, typically
sonnet) when the aggregate verdict is one that needs them. Scores are
averaged across judges.
"""

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    """Per-entry triage verdict.

    Values are ordered by *destructiveness to existing content*: lower
    ordinal = less destructive. The order matters for tie-breaking; do
    not reorder without updating ``_CONSERVATIVENESS``.
    """

    KEEP = "keep"
    PROMOTE_TO_PROMPT = "promote_to_prompt"
    REFINE = "refine"
    MERGE = "merge"
    DROP = "drop"


# Lower index = more conservative (less destructive). Used for tiebreaks
# when no verdict has a strict majority. The promote slot sits next to
# keep because promotion does not remove the entry — it just suggests an
# additional placement in the prompt.
_CONSERVATIVENESS: tuple[Verdict, ...] = (
    Verdict.KEEP,
    Verdict.PROMOTE_TO_PROMPT,
    Verdict.REFINE,
    Verdict.MERGE,
    Verdict.DROP,
)


@dataclass
class Judgment:
    """A single judge's vote on a single entry.

    ``raw_response`` is kept verbatim so a reviewer can audit the model's
    actual output even if the parser had to coerce shape. ``elapsed_sec``
    is wallclock for the judge call (latency tracking, not billing).
    """

    model: str
    verdict: Verdict
    quality: float  # 0.0..1.0 — is the entry specific, verifiable, retrievable?
    necessity: float  # 0.0..1.0 — would agent behavior change without it?
    justification: str
    raw_response: str = ""
    refined_text: str | None = None
    merge_with: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0


@dataclass
class MemoryProposal:
    """Aggregate triage proposal for one memory entry.

    Construct via :func:`aggregate`, never directly — the constructor
    skips invariants the aggregator enforces (e.g. ``confidence`` must
    track ``judge_votes``).
    """

    entry_id: str
    verdict: Verdict
    quality_score: float  # averaged across judges
    necessity_score: float  # averaged across judges
    confidence: float  # fraction of judges agreeing with ``verdict``
    judge_votes: dict[str, Judgment]  # keyed by model name
    justification: str
    refined_text: str | None = None
    merge_with: list[str] = field(default_factory=list)

    def is_candidate_disagreement(self, reference: str, candidate: str) -> bool:
        """True when the candidate judge differed from the reference judge.

        Used to populate the disagreement-set artifact that seeds the
        eventual judge fine-tune. Missing votes (model didn't return) are
        treated as non-disagreement so we don't pollute the training set
        with parser failures.
        """
        ref = self.judge_votes.get(reference)
        cand = self.judge_votes.get(candidate)
        if ref is None or cand is None:
            return False
        return ref.verdict != cand.verdict


def aggregate(
    entry_id: str,
    judgments: dict[str, Judgment],
    reference_model: str | None = None,
) -> MemoryProposal:
    """Reduce a per-model vote dict into a single ``MemoryProposal``.

    ``reference_model`` selects whose ``refined_text`` / ``merge_with`` /
    ``justification`` to use when the aggregate verdict needs them. If
    None or not present in ``judgments``, the first judge that voted for
    the winning verdict is used as a fallback.

    Raises ``ValueError`` if ``judgments`` is empty (a proposal with no
    votes is meaningless; callers should skip the entry instead).
    """
    if not judgments:
        raise ValueError(f"cannot aggregate proposal for {entry_id!r}: no judgments")

    verdict_counts = Counter(j.verdict for j in judgments.values())
    total = len(judgments)
    most_common = verdict_counts.most_common()
    top_count = most_common[0][1]

    if top_count * 2 > total:
        # Strict majority.
        winner = most_common[0][0]
    else:
        # No majority. Pick the most conservative verdict among those tied
        # for top count. ``_CONSERVATIVENESS`` is a stable, total order.
        tied = {v for v, c in most_common if c == top_count}
        winner = next(v for v in _CONSERVATIVENESS if v in tied)

    confidence = verdict_counts[winner] / total

    # Source supporting fields from the reference judge if it voted for the
    # winner; otherwise from the first agreeing judge (insertion order). We
    # never silently fabricate a refined_text for a verdict that doesn't
    # carry one in any vote — that would be the council inventing content.
    source: Judgment | None = None
    if reference_model and reference_model in judgments:
        ref = judgments[reference_model]
        if ref.verdict == winner:
            source = ref
    if source is None:
        for j in judgments.values():
            if j.verdict == winner:
                source = j
                break

    # ``source`` is non-None by construction: ``winner`` came from
    # ``verdict_counts``, which means at least one judgment voted for it.
    assert source is not None

    quality = sum(j.quality for j in judgments.values()) / total
    necessity = sum(j.necessity for j in judgments.values()) / total

    return MemoryProposal(
        entry_id=entry_id,
        verdict=winner,
        quality_score=quality,
        necessity_score=necessity,
        confidence=confidence,
        judge_votes=dict(judgments),
        justification=source.justification,
        refined_text=source.refined_text if winner in (Verdict.REFINE, Verdict.MERGE) else None,
        merge_with=list(source.merge_with) if winner == Verdict.MERGE else [],
    )
