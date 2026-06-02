# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Artifact emitters for a completed :class:`TriageRun`.

Two output shapes:

- JSON: a structured, machine-readable record of the full run, suitable
  for downstream tools (Phase 2 ``triage-memory`` job uploads,
  Phase 3.5 fine-tune corpus extraction, the eventual Studio diff view).
- Markdown: human-readable artifact organized by verdict bucket
  (drop → merge → refine → promote → keep), most-impactful first. Each
  entry carries its full per-judge audit trail so a reviewer can decide
  whether to accept the proposal.

The mutation contract from ``DESIGN.md`` Phase 0 applies here: these
emitters write *staged proposals*. They never mutate the underlying
memory store. The eventual apply step is a separate, deliberate human
action.
"""

import json
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from nemo_agents_plugin.improvement.memory.proposal import MemoryProposal, Verdict
from nemo_agents_plugin.improvement.memory.triage import TriageRun

# Verdict display order in Markdown: most-impactful first so a reviewer
# scrolling the artifact sees the destructive proposals before the keep
# bucket. Mirrors the conservativeness ordering but inverted.
_VERDICT_DISPLAY_ORDER: tuple[Verdict, ...] = (
    Verdict.DROP,
    Verdict.MERGE,
    Verdict.REFINE,
    Verdict.PROMOTE_TO_PROMPT,
    Verdict.KEEP,
)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _json_default(obj: Any) -> Any:
    """JSON encoder fallback for the types ``json.dumps`` cannot handle natively.

    Dataclasses get the ``asdict`` treatment (recursive), enums collapse
    to their string value, and datetimes serialize as ISO-8601. Anything
    else falls through to ``TypeError`` so a programming error surfaces
    instead of being silently dropped.
    """
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"object of type {type(obj).__name__} is not JSON serializable")


def to_json(run: TriageRun, *, indent: int = 2) -> str:
    """Serialize a :class:`TriageRun` to a JSON string.

    ``indent=2`` is the human-review default; pass ``indent=None`` for
    compact storage. The top-level shape is the ``TriageRun`` dataclass
    with proposals, errors, and skipped_entries fully expanded; verdict
    counts and the council models list are inlined for convenience so
    downstream consumers do not have to recompute them.
    """
    payload = {
        "store_name": run.store_name,
        "council_models": run.council_models,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "elapsed_sec": run.elapsed_sec,
        "verdict_counts": run.verdict_counts,
        "proposals": run.proposals,
        "errors": run.errors,
        "skipped_entries": run.skipped_entries,
    }
    return json.dumps(payload, default=_json_default, indent=indent, sort_keys=False)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _fmt_percent(part: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{100.0 * part / total:.1f}%"


def _fmt_proposal_block(proposal: MemoryProposal, entry_content: str | None = None) -> str:
    """Render one proposal as a Markdown chunk.

    ``entry_content`` is the original entry text, included so a reviewer
    does not need to cross-reference the source store. When omitted the
    block falls back to whatever is on the proposal itself (refined text
    for refines, otherwise nothing).
    """
    lines: list[str] = []
    lines.append(f"### `{proposal.entry_id}`")
    lines.append("")
    lines.append(f"- **verdict:** `{proposal.verdict.value}` (confidence {proposal.confidence:.2f})")
    lines.append(f"- **scores:** quality={proposal.quality_score:.2f}, necessity={proposal.necessity_score:.2f}")
    if proposal.merge_with:
        lines.append(f"- **merge with:** {', '.join('`' + m + '`' for m in proposal.merge_with)}")
    lines.append("")

    if entry_content:
        lines.append("**Original entry:**")
        lines.append("")
        lines.append("> " + entry_content.replace("\n", "\n> "))
        lines.append("")

    if proposal.refined_text:
        lines.append("**Refined text proposed:**")
        lines.append("")
        lines.append("> " + proposal.refined_text.replace("\n", "\n> "))
        lines.append("")

    if proposal.justification:
        lines.append(f"**Justification:** {proposal.justification}")
        lines.append("")

    # Per-judge audit trail. Listed in the order the council declared
    # them, so the reference judge appears first if it voted at all.
    if proposal.judge_votes:
        lines.append("**Judge votes:**")
        lines.append("")
        for model, vote in proposal.judge_votes.items():
            lines.append(
                f"- `{model}` -> `{vote.verdict.value}` "
                f"(quality={vote.quality:.2f}, necessity={vote.necessity:.2f}, "
                f"{vote.elapsed_sec:.1f}s)"
            )
            if vote.justification:
                lines.append(f"  - {vote.justification}")
        lines.append("")

    return "\n".join(lines)


def to_markdown(run: TriageRun, *, entries_by_id: dict[str, str] | None = None) -> str:
    """Render a :class:`TriageRun` as a human-readable Markdown artifact.

    ``entries_by_id`` maps entry ids to their original content, used to
    inline the entry text in each proposal block. Callers typically
    build this from the same ``MemoryStore`` they triaged; omitting it
    yields a slimmer artifact that still carries every proposal field
    except the original entry body.
    """
    entries_by_id = entries_by_id or {}
    total = len(run.proposals)

    out: list[str] = []
    out.append(f"# Memory triage proposals — `{run.store_name}`")
    out.append("")
    out.append("## Run")
    out.append("")
    out.append(f"- **council:** {', '.join('`' + m + '`' for m in run.council_models)}")
    if run.started_at:
        out.append(f"- **started:** {run.started_at.isoformat()}")
    if run.finished_at:
        out.append(f"- **finished:** {run.finished_at.isoformat()}")
    out.append(f"- **elapsed:** {run.elapsed_sec:.1f}s")
    out.append(f"- **proposals:** {total}")
    out.append(f"- **errors:** {len(run.errors)}")
    out.append(f"- **skipped entries:** {len(run.skipped_entries)}")
    out.append("")

    # Verdict summary table.
    out.append("## Summary")
    out.append("")
    out.append("| verdict | count | % of proposals |")
    out.append("| --- | ---: | ---: |")
    counts = run.verdict_counts
    for v in _VERDICT_DISPLAY_ORDER:
        c = counts.get(v.value, 0)
        out.append(f"| `{v.value}` | {c} | {_fmt_percent(c, total)} |")
    out.append("")

    # Per-verdict proposal sections, in display order.
    by_verdict: dict[Verdict, list[MemoryProposal]] = defaultdict(list)
    for p in run.proposals:
        by_verdict[p.verdict].append(p)

    for v in _VERDICT_DISPLAY_ORDER:
        bucket = by_verdict.get(v, [])
        if not bucket:
            continue
        out.append(f"## `{v.value}` ({len(bucket)})")
        out.append("")
        # Stable order: confidence descending, then by id for determinism.
        bucket_sorted = sorted(bucket, key=lambda p: (-p.confidence, p.entry_id))
        for p in bucket_sorted:
            out.append(_fmt_proposal_block(p, entry_content=entries_by_id.get(p.entry_id)))

    if run.skipped_entries:
        out.append("## Skipped entries")
        out.append("")
        out.append("Every judge failed on these entries; no proposal could be aggregated.")
        out.append("Consider re-running the council against just this subset.")
        out.append("")
        for eid in run.skipped_entries:
            out.append(f"- `{eid}`")
        out.append("")

    if run.errors:
        out.append("## Per-judge errors")
        out.append("")
        out.append("| entry | model | type | message |")
        out.append("| --- | --- | --- | --- |")
        for err in run.errors:
            # Markdown table cells must not contain newlines or pipes.
            msg = err.error_message.replace("|", "\\|").replace("\n", " ")
            out.append(f"| `{err.entry_id}` | `{err.model}` | `{err.error_type}` | {msg} |")
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------


def write_artifacts(
    run: TriageRun,
    out_dir: Path,
    *,
    entries_by_id: dict[str, str] | None = None,
    basename: str = "triage",
) -> tuple[Path, Path]:
    """Write JSON and Markdown artifacts side-by-side under ``out_dir``.

    Returns ``(json_path, md_path)``. Creates the directory if absent.
    Filenames are ``{basename}.json`` and ``{basename}.md`` so a single
    run produces a matched pair; callers that drive multiple stores in
    one process can vary ``basename`` to avoid collisions (e.g.
    ``triage-user``, ``triage-memory``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{basename}.json"
    md_path = out_dir / f"{basename}.md"
    json_path.write_text(to_json(run), encoding="utf-8")
    md_path.write_text(to_markdown(run, entries_by_id=entries_by_id), encoding="utf-8")
    return json_path, md_path
