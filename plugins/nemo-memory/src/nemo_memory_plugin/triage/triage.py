# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Council orchestration for memory triage.

For every entry in the provided store, run every judge in parallel,
aggregate their votes into a :class:`MemoryProposal`, and accumulate a
:class:`TriageRun` describing the full pass.

Concurrency shape: per-entry parallel judges, serial across entries.
Three concurrent calls per entry keeps wallclock low and rate-limit
exposure bounded. Pipelining across entries is a Phase 2 optimization
if we find we are bottlenecked on per-entry latency rather than
per-call latency.

Failure shape: a single judge raising on one entry is tolerated and
becomes a missing vote (the surviving judges still produce a proposal
via the conservative-tie rule in :mod:`proposal`). When all judges
fail on the same entry, no proposal is emitted; instead a
:class:`TriageError` is appended. The caller surfaces these in the
report artifact.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from nemo_memory_plugin.triage.judges import Judge, JudgeContext
from nemo_memory_plugin.triage.proposal import Judgment, MemoryProposal, aggregate
from nemo_memory_plugin.triage.store import MemoryEntry, MemoryStore

# Callable invoked after each entry completes. Receives ``(done, total)``
# so the caller can drive a progress bar, log line, or no-op. ``total``
# may be ``-1`` when the store does not support cheap counting.
ProgressCallback = Callable[[int, int], None]


@dataclass
class TriageError:
    """One judge failed on one entry.

    The entry may still have a proposal if other judges voted; this
    record exists for the audit trail and for the disagreement set
    seeding the eventual judge fine-tune.
    """

    entry_id: str
    model: str
    error_type: str
    error_message: str


@dataclass
class TriageRun:
    """Full output of one ``run_triage`` invocation.

    ``proposals`` is the staged-mutation artifact for review. ``errors``
    documents every per-judge failure that occurred. ``skipped_entries``
    lists entries where every judge failed (no proposal could be made).

    ``elapsed_sec`` is wallclock for the full pass; per-judge latency
    is preserved inside each :class:`Judgment`.
    """

    store_name: str
    council_models: list[str]
    proposals: list[MemoryProposal] = field(default_factory=list)
    errors: list[TriageError] = field(default_factory=list)
    skipped_entries: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_sec: float = 0.0

    @property
    def verdict_counts(self) -> dict[str, int]:
        """Count proposals by verdict value (e.g. ``{"keep": 30, "drop": 5}``).

        Stable across runs because :class:`Verdict` is a string enum. The
        report layer renders this as the headline-level "what would this
        proposal change if accepted" summary.
        """
        return dict(Counter(p.verdict.value for p in self.proposals))

    def disagreement_set(self, reference: str, candidate: str) -> list[MemoryProposal]:
        """Proposals where the candidate judge dissented from the reference.

        Used to seed the eventual judge fine-tune corpus. A proposal is
        included only when both models cast a vote; parser failures do
        not pollute the set (see ``MemoryProposal.is_candidate_disagreement``).
        """
        return [p for p in self.proposals if p.is_candidate_disagreement(reference, candidate)]


def _build_context(store: MemoryStore, entries: list[MemoryEntry]) -> JudgeContext:
    """Compute the corpus-level summary the council prompt prefaces with.

    Calibrates each judge's prior: knowing "58 of 71 entries are
    single-observation" prevents the judge from treating low
    corroboration as automatically suspect when it is the corpus norm.
    """
    if not entries:
        return JudgeContext(store_name=store.name, corpus_size=0, corroboration_summary="")

    n = len(entries)
    single_obs = sum(1 for e in entries if e.corroboration_count <= 1)
    multi_obs = n - single_obs
    max_corroboration = max(e.corroboration_count for e in entries)

    summary = (
        f"{single_obs} of {n} entries are single-observation (seen-in 1 session); "
        f"{multi_obs} have multi-session corroboration. "
        f"Highest corroboration in the corpus is {max_corroboration}."
    )
    return JudgeContext(store_name=store.name, corpus_size=n, corroboration_summary=summary)


async def _judge_with_capture(
    judge: Judge,
    entry: MemoryEntry,
    context: JudgeContext,
    errors_out: list[TriageError],
) -> Judgment | None:
    """Run one judge on one entry; capture any failure into ``errors_out``.

    Catching ``Exception`` is intentional: the orchestrator's contract
    is "a single judge failing on a single entry must not crash the
    full pass." Re-raising ``KeyboardInterrupt`` and ``SystemExit``
    happens automatically because they are ``BaseException`` subclasses
    and not in the ``Exception`` hierarchy.
    """
    try:
        return await judge.judge(entry, context)
    except Exception as err:
        errors_out.append(
            TriageError(
                entry_id=entry.id,
                model=judge.model,
                error_type=type(err).__name__,
                error_message=str(err)[:500],
            )
        )
        return None


async def run_triage(
    store: MemoryStore,
    judges: list[Judge],
    *,
    reference_model: str | None = None,
    max_entries: int | None = None,
    progress: ProgressCallback | None = None,
) -> TriageRun:
    """Run the full council pass over ``store``.

    Arguments:
        store: read-only memory store to triage.
        judges: list of judge instances. Order is recorded but does not
            affect aggregation; the council vote uses the
            ``reference_model`` to break ties on supporting-field
            sourcing only.
        reference_model: name of the reference judge (typically the
            highest-quality model in the council). Used by
            :func:`aggregate` to pick whose refined_text/justification
            wins when the reference voted with the majority.
        max_entries: cap on entries processed. Useful for smoke runs
            against a small slice before committing budget to the full
            corpus. ``None`` means process every entry.
        progress: optional callback invoked after each entry completes
            with ``(done, total)``. ``total`` is -1 if the store could
            not cheaply count entries.

    Returns:
        :class:`TriageRun` with proposals, errors, and timing.

    Raises:
        ``ValueError`` if ``judges`` is empty. A council with no judges
        is meaningless and silently producing an empty run would hide
        the misconfiguration.
    """
    if not judges:
        raise ValueError("triage requires at least one judge")

    council_models = [j.model for j in judges]
    started = datetime.now(timezone.utc)
    start_monotonic = asyncio.get_event_loop().time()

    # Materialize entries up front so we can compute the corpus summary
    # before any judge call. This costs a full iteration of the store;
    # for a 300-entry PoC corpus that is negligible, and for larger
    # stores the alternative (streaming + degraded prompt context) is a
    # Phase 2 concern.
    all_entries = list(store.list_entries())
    if max_entries is not None:
        all_entries = all_entries[:max_entries]
    total = len(all_entries)

    context = _build_context(store, all_entries)

    run = TriageRun(
        store_name=store.name,
        council_models=council_models,
        started_at=started,
    )

    for done, entry in enumerate(all_entries, start=1):
        per_entry_errors: list[TriageError] = []
        tasks: list[Awaitable[Judgment | None]] = [
            _judge_with_capture(judge, entry, context, per_entry_errors) for judge in judges
        ]
        results = await asyncio.gather(*tasks)

        run.errors.extend(per_entry_errors)

        judgments: dict[str, Judgment] = {}
        for j in results:
            if j is not None:
                judgments[j.model] = j

        if judgments:
            proposal = aggregate(entry.id, judgments, reference_model=reference_model)
            run.proposals.append(proposal)
        else:
            # Every judge failed on this entry. Record the skip so the
            # report surfaces it; a reviewer may want to re-run the
            # council against just the skipped subset.
            run.skipped_entries.append(entry.id)

        if progress is not None:
            progress(done, total)

    run.finished_at = datetime.now(timezone.utc)
    run.elapsed_sec = asyncio.get_event_loop().time() - start_monotonic
    return run
