# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build a labeled fine-tune corpus from a memory-triage artifact.

Takes a triage artifact JSON (produced by ``report.write_artifacts``,
with at least the ``reference_judge`` model in its ``judge_votes``) and
the original pi-hermes corpus, and emits a labeled dataset ready for
supervised fine-tuning of a smaller judge model.

Two output JSONL formats land in the same directory:

- **Raw labeled JSONL** (``{basename}.jsonl``): one record per entry with
  the entry text, corroboration count, and the reference judge's full
  judgment (verdict, scores, justification, refined_text, merge_with,
  raw_response). Prompt-template-independent. This is the canonical
  training data; whatever fine-tune pipeline ultimately lands can
  re-render its own prompt format from here.

- **Chat-format JSONL** (``{basename}-chat.jsonl``): one record per entry
  formatted as ``{"messages": [system, user, assistant]}``, using the
  *current* Phase 1 judge system + user prompts from ``judges.py``. SFT
  pipelines (OpenAI fine-tune API, HF TRL, NeMo Customizer when it
  ships) generally consume this shape directly. Re-export this view
  any time the prompt template changes; the raw view stays stable.

Disagreement tagging:

When a ``candidate_judge`` is supplied (and the artifact has both that
judge's vote and the reference judge's vote), every record gets an
``is_disagreement`` flag plus the candidate's verdict and justification.
``only_disagreements=True`` filters the corpus down to just the
boundary cases (the original bd ``mdubrinsky-7au.3`` deliverable: the
v1 Sonnet 4.5 vs Nemotron-Nano 40-entry disagreement set).

The function is pure data extraction; no LLM calls.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nemo_agents_plugin.improvement.memory.judges import _PROMPT_TEMPLATE, _SYSTEM, JudgeContext
from nemo_agents_plugin.improvement.memory.proposal import Verdict
from nemo_agents_plugin.improvement.memory.store import MemoryEntry


@dataclass(frozen=True)
class FinetuneRecord:
    """One labeled training example.

    Fields divide into three groups:

    1. **Entry**: the durable memory entry being judged (id, content,
       corroboration_count).
    2. **Label**: the reference judge's full judgment, including the
       raw_response so chat-format export gets the exact JSON string
       the judge emitted rather than a re-serialized round-trip.
    3. **Candidate metadata**: when comparing against a weaker
       candidate judge, the candidate's verdict + justification + the
       ``is_disagreement`` flag. Always present (None / False when no
       candidate is provided), so JSONL consumers don't have to handle
       optional keys.
    """

    # Entry
    entry_id: str
    entry_content: str
    corroboration_count: int

    # Label (gold = reference judge's judgment)
    reference_judge: str
    label_verdict: str
    label_quality: float
    label_necessity: float
    label_justification: str
    label_refined_text: str | None
    label_merge_with: list[str]
    label_raw_response: str | None

    # Candidate (optional disagreement metadata)
    candidate_judge: str | None
    candidate_verdict: str | None
    candidate_justification: str | None
    is_disagreement: bool

    # Reproducible prompts (rendered from Phase 1 templates + corpus context)
    system_prompt: str
    user_prompt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "entry_content": self.entry_content,
            "corroboration_count": self.corroboration_count,
            "label": {
                "reference_judge": self.reference_judge,
                "verdict": self.label_verdict,
                "quality": self.label_quality,
                "necessity": self.label_necessity,
                "justification": self.label_justification,
                "refined_text": self.label_refined_text,
                "merge_with": self.label_merge_with,
                "raw_response": self.label_raw_response,
            },
            "candidate": {
                "judge": self.candidate_judge,
                "verdict": self.candidate_verdict,
                "justification": self.candidate_justification,
            },
            "is_disagreement": self.is_disagreement,
            "prompts": {
                "system": self.system_prompt,
                "user": self.user_prompt,
            },
        }

    def to_chat_messages(self) -> list[dict[str, str]]:
        """Render as the SFT-standard messages list.

        Uses ``label_raw_response`` as the assistant turn when available,
        so the model learns to reproduce the judge's exact wire format
        (including any quirks the live judge actually emitted). Falls
        back to a freshly-serialized JSON if the artifact predates the
        raw_response field.
        """
        if self.label_raw_response and self.label_raw_response.strip():
            assistant_content = self.label_raw_response.strip()
        else:
            payload: dict[str, Any] = {
                "verdict": self.label_verdict,
                "quality": self.label_quality,
                "necessity": self.label_necessity,
                "justification": self.label_justification,
            }
            if self.label_verdict == Verdict.REFINE.value and self.label_refined_text:
                payload["refined_text"] = self.label_refined_text
            if self.label_verdict == Verdict.MERGE.value and self.label_merge_with:
                payload["merge_with"] = self.label_merge_with
            assistant_content = json.dumps(payload)
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt},
            {"role": "assistant", "content": assistant_content},
        ]


@dataclass(frozen=True)
class FinetuneCorpusSummary:
    """At-a-glance summary of a built corpus.

    Saved alongside the JSONL so a reviewer can audit dataset shape
    (label distribution, disagreement counts, source artifact provenance)
    without having to parse the records.
    """

    source_artifact: str
    source_corpus: str
    reference_judge: str
    candidate_judge: str | None
    only_disagreements: bool

    total_records: int
    label_verdict_counts: dict[str, int]
    disagreement_count: int
    candidate_verdict_counts: dict[str, int]
    skipped_entries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_artifact": self.source_artifact,
            "source_corpus": self.source_corpus,
            "reference_judge": self.reference_judge,
            "candidate_judge": self.candidate_judge,
            "only_disagreements": self.only_disagreements,
            "total_records": self.total_records,
            "label_verdict_counts": self.label_verdict_counts,
            "disagreement_count": self.disagreement_count,
            "candidate_verdict_counts": self.candidate_verdict_counts,
            "skipped_entries": self.skipped_entries,
        }


def _build_user_prompt(entry: MemoryEntry, context: JudgeContext) -> str:
    """Render the per-entry user prompt the live judge would have seen.

    Mirrors ``judges._build_prompt`` exactly so the fine-tune corpus's
    chat-format export matches the in-flight Phase 1 prompts byte-for-byte.
    Kept as a small local helper rather than importing ``_build_prompt``
    so the dependency on judge internals is visible at the call site.
    """
    return _PROMPT_TEMPLATE.format(
        store_name=context.store_name,
        corpus_size=context.corpus_size,
        corroboration_summary=context.corroboration_summary or "(no corpus-level corroboration summary)",
        corroboration=entry.corroboration_count,
        content=entry.content,
    )


def _judge_context_from_entries(store_name: str, entries: list[MemoryEntry]) -> JudgeContext:
    """Recompute the corpus-level context that triage._build_context produces.

    Kept here (rather than imported from triage.py) so the finetune
    module doesn't reach into another module's private helper. Logic is
    a small duplication; if it ever drifts the chat-format export will
    diverge from the live prompts, which is exactly the case our tests
    against the real v1 artifact will catch.
    """
    if not entries:
        return JudgeContext(store_name=store_name, corpus_size=0, corroboration_summary="")
    n = len(entries)
    single_obs = sum(1 for e in entries if e.corroboration_count <= 1)
    multi_obs = n - single_obs
    max_corroboration = max(e.corroboration_count for e in entries)
    summary = (
        f"{single_obs} of {n} entries are single-observation (seen-in 1 session); "
        f"{multi_obs} have multi-session corroboration. "
        f"Highest corroboration in the corpus is {max_corroboration}."
    )
    return JudgeContext(store_name=store_name, corpus_size=n, corroboration_summary=summary)


def build_finetune_corpus(
    triage_artifact_path: Path,
    corpus_path: Path,
    *,
    reference_judge: str,
    candidate_judge: str | None = None,
    only_disagreements: bool = False,
) -> tuple[list[FinetuneRecord], FinetuneCorpusSummary]:
    """Extract a labeled fine-tune corpus.

    The triage artifact must have *reference_judge* in every proposal's
    ``judge_votes``. Entries where the reference judge failed (no vote
    captured) are logged into ``summary.skipped_entries`` and dropped
    from the corpus.

    When *candidate_judge* is None and *only_disagreements* is True,
    raises :class:`ValueError`: the filter is meaningless without a
    candidate to compare against.
    """
    if only_disagreements and candidate_judge is None:
        raise ValueError(
            "only_disagreements=True requires a candidate_judge to compare against. "
            "Set candidate_judge to a model id present in the artifact's judge_votes."
        )

    # Lazy import to avoid a top-level dependency on the adapter package
    # (keeps the test surface of the eval / finetune primitives small).
    from nemo_agents_plugin.improvement.memory.adapters.pi_hermes import PiHermesMemoryStore

    artifact = json.loads(Path(triage_artifact_path).read_text(encoding="utf-8"))
    required = {"store_name", "council_models", "proposals"}
    missing = required - set(artifact.keys())
    if missing:
        raise ValueError(
            f"Triage artifact at {triage_artifact_path} is missing required top-level "
            f"keys: {sorted(missing)}. Was it produced by report.write_artifacts?"
        )
    if reference_judge not in artifact["council_models"]:
        raise ValueError(
            f"reference_judge {reference_judge!r} is not in the artifact's council_models "
            f"({artifact['council_models']!r}). Pick a judge that actually ran."
        )
    if candidate_judge is not None and candidate_judge not in artifact["council_models"]:
        raise ValueError(
            f"candidate_judge {candidate_judge!r} is not in the artifact's council_models "
            f"({artifact['council_models']!r}). Pick a judge that actually ran, or "
            "leave candidate_judge unset to export the full reference-labeled corpus."
        )

    store = PiHermesMemoryStore(path=Path(corpus_path), name=str(artifact["store_name"]))
    entries = list(store.list_entries())
    entries_by_id = {e.id: e for e in entries}
    context = _judge_context_from_entries(str(artifact["store_name"]), entries)

    records: list[FinetuneRecord] = []
    skipped: list[str] = []
    label_counts: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()
    disagreements = 0

    for proposal in artifact["proposals"]:
        eid = proposal["entry_id"]
        votes = proposal.get("judge_votes", {})
        ref_vote = votes.get(reference_judge)
        if not ref_vote:
            # Reference judge had no vote on this entry (timeout, bad JSON,
            # empty content). The entry is unusable as a labeled example;
            # surface it in the summary so the user knows the corpus is
            # short of the artifact's entry count.
            skipped.append(eid)
            continue

        entry = entries_by_id.get(eid)
        if entry is None:
            # Entry ID is in the artifact but not in the live corpus.
            # Likely the corpus has drifted since the triage ran. Skip
            # rather than emit a record with no entry text.
            skipped.append(eid)
            continue

        cand_vote = votes.get(candidate_judge) if candidate_judge else None
        is_disagree = bool(cand_vote and ref_vote["verdict"] != cand_vote["verdict"])

        if only_disagreements and not is_disagree:
            continue

        label_counts[ref_vote["verdict"]] += 1
        if cand_vote:
            candidate_counts[cand_vote["verdict"]] += 1
        if is_disagree:
            disagreements += 1

        records.append(
            FinetuneRecord(
                entry_id=eid,
                entry_content=entry.content,
                corroboration_count=entry.corroboration_count,
                reference_judge=reference_judge,
                label_verdict=str(ref_vote["verdict"]),
                label_quality=float(ref_vote.get("quality", 0.0)),
                label_necessity=float(ref_vote.get("necessity", 0.0)),
                label_justification=str(ref_vote.get("justification", "")),
                label_refined_text=ref_vote.get("refined_text"),
                label_merge_with=list(ref_vote.get("merge_with", []) or []),
                label_raw_response=ref_vote.get("raw_response"),
                candidate_judge=candidate_judge,
                candidate_verdict=str(cand_vote["verdict"]) if cand_vote else None,
                candidate_justification=(str(cand_vote.get("justification", "")) if cand_vote else None),
                is_disagreement=is_disagree,
                system_prompt=_SYSTEM,
                user_prompt=_build_user_prompt(entry, context),
            )
        )

    summary = FinetuneCorpusSummary(
        source_artifact=str(triage_artifact_path),
        source_corpus=str(corpus_path),
        reference_judge=reference_judge,
        candidate_judge=candidate_judge,
        only_disagreements=only_disagreements,
        total_records=len(records),
        label_verdict_counts=dict(label_counts),
        disagreement_count=disagreements,
        candidate_verdict_counts=dict(candidate_counts),
        skipped_entries=skipped,
    )

    return records, summary


def to_jsonl_raw(records: Iterable[FinetuneRecord]) -> str:
    """Serialize records as raw labeled JSONL (prompt-template-independent).

    One record per line, each record is the full :meth:`FinetuneRecord.to_dict`
    output. Stable across prompt-template changes; this is the canonical
    training data.
    """
    return "\n".join(json.dumps(r.to_dict()) for r in records) + "\n"


def to_jsonl_chat(records: Iterable[FinetuneRecord]) -> str:
    """Serialize records as ``{"messages": [...]}`` JSONL.

    Standard SFT shape consumed by OpenAI fine-tune API, HuggingFace
    TRL, and most NeMo customization flows. Uses the Phase 1 judge
    system + user prompts and the captured reference-judge raw response
    as the assistant turn.
    """
    return "\n".join(json.dumps({"messages": r.to_chat_messages()}) for r in records) + "\n"


def to_markdown_summary(summary: FinetuneCorpusSummary) -> str:
    """Render a human-readable summary of the built corpus.

    Saved alongside the JSONL files so a reviewer can audit dataset
    shape (label distribution, disagreement counts, source provenance)
    without having to parse the records.
    """
    lines: list[str] = []
    lines.append("# Memory-triage fine-tune corpus summary")
    lines.append("")
    lines.append("## Source")
    lines.append("")
    lines.append(f"- Artifact: `{summary.source_artifact}`")
    lines.append(f"- Corpus: `{summary.source_corpus}`")
    lines.append(f"- Reference judge (gold labels): `{summary.reference_judge}`")
    if summary.candidate_judge:
        lines.append(f"- Candidate judge (disagreement source): `{summary.candidate_judge}`")
    lines.append(f"- Filter: {'only disagreements' if summary.only_disagreements else 'full labeled corpus'}")
    lines.append("")

    lines.append("## Shape")
    lines.append("")
    lines.append(f"- Total records: **{summary.total_records}**")
    if summary.candidate_judge:
        lines.append(f"- Disagreements: **{summary.disagreement_count}**")
    if summary.skipped_entries:
        lines.append(f"- Skipped entries (no reference vote or missing in corpus): {len(summary.skipped_entries)}")
    lines.append("")

    lines.append("## Reference label distribution")
    lines.append("")
    lines.append("| verdict | count |")
    lines.append("| --- | ---: |")
    for v in sorted(summary.label_verdict_counts):
        lines.append(f"| `{v}` | {summary.label_verdict_counts[v]} |")
    lines.append("")

    if summary.candidate_judge:
        lines.append(f"## Candidate ({summary.candidate_judge}) label distribution")
        lines.append("")
        lines.append("| verdict | count |")
        lines.append("| --- | ---: |")
        for v in sorted(summary.candidate_verdict_counts):
            lines.append(f"| `{v}` | {summary.candidate_verdict_counts[v]} |")
        lines.append("")

    return "\n".join(lines)


def write_finetune_artifacts(
    records: list[FinetuneRecord],
    summary: FinetuneCorpusSummary,
    output_dir: Path,
    *,
    basename: str,
) -> dict[str, Path]:
    """Write the raw JSONL, chat JSONL, and Markdown summary to *output_dir*.

    Returns a dict keyed by artifact kind (``"raw"``, ``"chat"``, ``"summary"``)
    mapping to the written :class:`Path` so the caller can log / return / upload.

    The basename pattern is::

        {basename}.jsonl       (raw labeled records)
        {basename}-chat.jsonl  (chat-format messages)
        {basename}.md          (summary)

    Three files instead of the two-file pair the triage / eval jobs
    emit; the fileset-upload helper has to know about that, which is
    why the export NemoJob configures its expected_suffixes accordingly.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{basename}.jsonl"
    chat_path = output_dir / f"{basename}-chat.jsonl"
    md_path = output_dir / f"{basename}.md"
    raw_path.write_text(to_jsonl_raw(records), encoding="utf-8")
    chat_path.write_text(to_jsonl_chat(records), encoding="utf-8")
    md_path.write_text(to_markdown_summary(summary), encoding="utf-8")
    return {"raw": raw_path, "chat": chat_path, "summary": md_path}


__all__ = [
    "FinetuneCorpusSummary",
    "FinetuneRecord",
    "build_finetune_corpus",
    "to_jsonl_chat",
    "to_jsonl_raw",
    "to_markdown_summary",
    "write_finetune_artifacts",
]
