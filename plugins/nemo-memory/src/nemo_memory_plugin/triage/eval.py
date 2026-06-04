# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Baseline-vs-candidate evaluation for memory-triage runs.

Loads two triage artifact JSONs (produced by ``report.write_artifacts``)
and computes an :class:`AgreementReport` describing how closely the
candidate reproduces the baseline:

- **Strict agreement**: fraction of common entries where the aggregate
  verdict matches exactly. Bounded above by the judge's intra-stability:
  two Sonnet 4.6 runs on the same corpus disagreed on 4/71 entries (94.4%),
  so the strict ceiling is ~95% even for "perfect" reproduction.

- **Verdict-axis agreement**: two coarser views that ask whether the
  judges agree on the *practical* outcome:

  - **Retain-vs-drop** (2-way): both judges agree the entry should exist
    in some form (keep / promote / refine / merge), vs both agree it
    should be dropped. Insensitive to the promote / refine boundary.

  - **Promote-threshold** (2-way): both judges agree on whether the entry
    deserves prompt-level promotion. Sensitive to the "is this worth a
    system-prompt slot" judgment, which is where same-judge runs jitter.

- **Confusion matrix**: full 5x5 verdict-vs-verdict cross-tab so the
  shape of disagreement is visible at a glance.

- **Delta set**: per-entry list of disagreements with both verdicts and
  both justifications inline, sorted by disagreement type so reviewers
  can scan one band of disagreements at a time.

The primitive is pure data, no LLM calls. Use cases:

1. **Intra-judge stability**: Sonnet-laptop vs Sonnet-omnistation
   (sanity-check the noise floor; we measured ~95% on USER.md).
2. **Tuned-model evaluation**: Sonnet baseline vs tuned-Nemotron
   candidate (the actual production target).
3. **Cross-judge calibration**: Sonnet baseline vs Nemotron baseline
   (research signal for the v1 calibration findings in RESULTS.md).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nemo_memory_plugin.triage.proposal import Verdict

# Coarse-grained verdict groupings. These define the two-way agreement
# metrics; see module docstring for the semantics.
_RETAIN_VERDICTS: frozenset[Verdict] = frozenset(
    {Verdict.KEEP, Verdict.PROMOTE_TO_PROMPT, Verdict.REFINE, Verdict.MERGE}
)
_PROMOTE_VERDICTS: frozenset[Verdict] = frozenset({Verdict.PROMOTE_TO_PROMPT})


@dataclass(frozen=True)
class VerdictDelta:
    """One entry where baseline and candidate disagree.

    Carries both verdicts plus the reference judge's justification from
    each run so a reviewer can read why each side made its call without
    cross-referencing the source artifacts.
    """

    entry_id: str
    baseline_verdict: Verdict
    candidate_verdict: Verdict
    baseline_confidence: float
    candidate_confidence: float
    baseline_justification: str
    candidate_justification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "baseline_verdict": self.baseline_verdict.value,
            "candidate_verdict": self.candidate_verdict.value,
            "baseline_confidence": self.baseline_confidence,
            "candidate_confidence": self.candidate_confidence,
            "baseline_justification": self.baseline_justification,
            "candidate_justification": self.candidate_justification,
        }


@dataclass(frozen=True)
class AgreementReport:
    """Output of :func:`compare_runs`.

    All counts are over *common* entries (those judged by both runs).
    Entries that appear in only one run are recorded separately in
    ``baseline_only_entries`` / ``candidate_only_entries`` and do not
    affect the agreement rates.
    """

    # Provenance: where the two runs came from.
    baseline_store_name: str
    candidate_store_name: str
    baseline_council: list[str]
    candidate_council: list[str]
    baseline_elapsed_sec: float
    candidate_elapsed_sec: float

    # Coverage: how many entries the two runs share.
    total_baseline_entries: int
    total_candidate_entries: int
    common_entries: int
    baseline_only_entries: list[str]
    candidate_only_entries: list[str]

    # Agreement metrics, all in [0.0, 1.0]; counts are absolute.
    strict_agreements: int
    strict_rate: float
    retain_vs_drop_agreements: int
    retain_vs_drop_rate: float
    promote_threshold_agreements: int
    promote_threshold_rate: float

    # 5x5 confusion: confusion[baseline_verdict][candidate_verdict] = count.
    confusion: dict[Verdict, dict[Verdict, int]]

    # Per-entry deltas, sorted by (baseline_verdict, candidate_verdict)
    # so reviewers see all the keep-to-promote flips together, then all
    # the keep-to-refine flips, etc.
    deltas: list[VerdictDelta] = field(default_factory=list)

    # Aggregate verdict distributions, useful for sanity-checking before
    # diving into the per-entry deltas.
    baseline_verdict_counts: dict[str, int] = field(default_factory=dict)
    candidate_verdict_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializable form for JSON output."""
        return {
            "baseline": {
                "store_name": self.baseline_store_name,
                "council": self.baseline_council,
                "elapsed_sec": self.baseline_elapsed_sec,
                "total_entries": self.total_baseline_entries,
                "verdict_counts": self.baseline_verdict_counts,
            },
            "candidate": {
                "store_name": self.candidate_store_name,
                "council": self.candidate_council,
                "elapsed_sec": self.candidate_elapsed_sec,
                "total_entries": self.total_candidate_entries,
                "verdict_counts": self.candidate_verdict_counts,
            },
            "coverage": {
                "common_entries": self.common_entries,
                "baseline_only_entries": self.baseline_only_entries,
                "candidate_only_entries": self.candidate_only_entries,
            },
            "agreement": {
                "strict": {
                    "matches": self.strict_agreements,
                    "rate": self.strict_rate,
                },
                "retain_vs_drop": {
                    "matches": self.retain_vs_drop_agreements,
                    "rate": self.retain_vs_drop_rate,
                },
                "promote_threshold": {
                    "matches": self.promote_threshold_agreements,
                    "rate": self.promote_threshold_rate,
                },
            },
            "confusion": {b.value: {c.value: n for c, n in row.items()} for b, row in self.confusion.items()},
            "deltas": [d.to_dict() for d in self.deltas],
        }


def load_triage_artifact(path: Path) -> Mapping[str, Any]:
    """Load + lightly validate a triage artifact JSON.

    Validates that the top-level keys we need are present (and produce
    a friendlier error than a KeyError deep in :func:`compare_runs`).
    We don't try to schema-check the whole document. Drift in unused
    fields shouldn't break the eval.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"store_name", "council_models", "proposals"}
    missing = required - set(raw.keys())
    if missing:
        raise ValueError(
            f"Triage artifact at {path} is missing required top-level keys: "
            f"{sorted(missing)}. Was it produced by report.write_artifacts?"
        )
    return raw


def compare_runs(
    baseline_path: Path,
    candidate_path: Path,
) -> AgreementReport:
    """Compute the agreement report between a baseline and a candidate run.

    Both arguments point at the JSON half of a
    ``report.write_artifacts`` output. The function is deterministic
    and offline; no LLM calls.

    Entries are matched by ``entry_id``. When the two runs were taken
    over the same underlying store the IDs match deterministically
    (the corpus is content-hashed). When the underlying stores differ,
    only entries with the same ID in both runs are compared and the
    rest are surfaced as ``baseline_only_entries`` /
    ``candidate_only_entries`` for the caller's awareness.
    """
    baseline = load_triage_artifact(baseline_path)
    candidate = load_triage_artifact(candidate_path)

    bl_by_id = {p["entry_id"]: p for p in baseline["proposals"]}
    cd_by_id = {p["entry_id"]: p for p in candidate["proposals"]}
    common_ids = sorted(set(bl_by_id) & set(cd_by_id))

    # Pre-seed the confusion matrix with every Verdict on both axes so
    # downstream rendering doesn't have to handle sparse-missing-row
    # cases. The unused cells stay at zero.
    confusion: dict[Verdict, dict[Verdict, int]] = {b: {c: 0 for c in Verdict} for b in Verdict}

    strict_match = 0
    retain_match = 0
    promote_match = 0
    deltas: list[VerdictDelta] = []

    for eid in common_ids:
        bv = Verdict(bl_by_id[eid]["verdict"])
        cv = Verdict(cd_by_id[eid]["verdict"])
        confusion[bv][cv] += 1

        if bv == cv:
            strict_match += 1
        else:
            deltas.append(
                VerdictDelta(
                    entry_id=eid,
                    baseline_verdict=bv,
                    candidate_verdict=cv,
                    baseline_confidence=float(bl_by_id[eid].get("confidence", 0.0)),
                    candidate_confidence=float(cd_by_id[eid].get("confidence", 0.0)),
                    baseline_justification=str(bl_by_id[eid].get("justification", "")),
                    candidate_justification=str(cd_by_id[eid].get("justification", "")),
                )
            )

        if (bv in _RETAIN_VERDICTS) == (cv in _RETAIN_VERDICTS):
            retain_match += 1
        if (bv in _PROMOTE_VERDICTS) == (cv in _PROMOTE_VERDICTS):
            promote_match += 1

    # Sort the deltas so all flips of the same kind cluster. Reviewers
    # tend to scan "all the keep->promote disagreements" as a band, then
    # "all the refine->keep disagreements", etc.
    deltas.sort(key=lambda d: (d.baseline_verdict.value, d.candidate_verdict.value, d.entry_id))

    n = len(common_ids)

    def rate(matches: int) -> float:
        return matches / n if n else 0.0

    return AgreementReport(
        baseline_store_name=str(baseline["store_name"]),
        candidate_store_name=str(candidate["store_name"]),
        baseline_council=list(baseline["council_models"]),
        candidate_council=list(candidate["council_models"]),
        baseline_elapsed_sec=float(baseline.get("elapsed_sec", 0.0)),
        candidate_elapsed_sec=float(candidate.get("elapsed_sec", 0.0)),
        total_baseline_entries=len(bl_by_id),
        total_candidate_entries=len(cd_by_id),
        common_entries=n,
        baseline_only_entries=sorted(set(bl_by_id) - set(cd_by_id)),
        candidate_only_entries=sorted(set(cd_by_id) - set(bl_by_id)),
        strict_agreements=strict_match,
        strict_rate=rate(strict_match),
        retain_vs_drop_agreements=retain_match,
        retain_vs_drop_rate=rate(retain_match),
        promote_threshold_agreements=promote_match,
        promote_threshold_rate=rate(promote_match),
        confusion=confusion,
        deltas=deltas,
        baseline_verdict_counts=dict(baseline.get("verdict_counts", {})),
        candidate_verdict_counts=dict(candidate.get("verdict_counts", {})),
    )


def to_json(report: AgreementReport) -> str:
    """Render the report as a pretty-printed JSON string."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=False)


def to_markdown(report: AgreementReport) -> str:
    """Render the report as a human-readable Markdown document.

    The Markdown is laid out so a reviewer can scan top-down: header
    block (provenance + headline rates), confusion matrix, then the
    per-entry delta band. Each delta carries both justifications inline
    so reviewing the disagreement does not need a second window.
    """
    lines: list[str] = []

    def pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    lines.append("# Memory-triage agreement report")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Baseline store: `{report.baseline_store_name}`")
    lines.append(f"- Baseline council: `{', '.join(report.baseline_council)}`")
    lines.append(f"- Baseline entries: {report.total_baseline_entries}, elapsed {report.baseline_elapsed_sec:.1f}s")
    lines.append(f"- Candidate store: `{report.candidate_store_name}`")
    lines.append(f"- Candidate council: `{', '.join(report.candidate_council)}`")
    lines.append(f"- Candidate entries: {report.total_candidate_entries}, elapsed {report.candidate_elapsed_sec:.1f}s")
    lines.append("")

    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Common entries (matched by ID): **{report.common_entries}**")
    if report.baseline_only_entries:
        lines.append(f"- Baseline-only entries: {len(report.baseline_only_entries)}")
    if report.candidate_only_entries:
        lines.append(f"- Candidate-only entries: {len(report.candidate_only_entries)}")
    lines.append("")

    lines.append("## Headline agreement")
    lines.append("")
    lines.append("| metric | matches | rate |")
    lines.append("| --- | ---: | ---: |")
    lines.append(
        f"| Strict (exact verdict match) | {report.strict_agreements} / "
        f"{report.common_entries} | **{pct(report.strict_rate)}** |"
    )
    lines.append(
        f"| Retain vs drop (2-way) | {report.retain_vs_drop_agreements} / "
        f"{report.common_entries} | {pct(report.retain_vs_drop_rate)} |"
    )
    lines.append(
        f"| Promote threshold (2-way) | {report.promote_threshold_agreements} / "
        f"{report.common_entries} | {pct(report.promote_threshold_rate)} |"
    )
    lines.append("")

    lines.append("## Verdict distribution")
    lines.append("")
    lines.append("| verdict | baseline | candidate |")
    lines.append("| --- | ---: | ---: |")
    all_verdicts = sorted(set(report.baseline_verdict_counts) | set(report.candidate_verdict_counts))
    for v in all_verdicts:
        b = report.baseline_verdict_counts.get(v, 0)
        c = report.candidate_verdict_counts.get(v, 0)
        lines.append(f"| `{v}` | {b} | {c} |")
    lines.append("")

    lines.append("## Confusion matrix")
    lines.append("")
    lines.append("Rows: baseline verdict. Columns: candidate verdict. Diagonal = agreement.")
    lines.append("")
    verdict_list = list(Verdict)
    header = "| baseline \\ candidate |" + "".join(f" `{v.value}` |" for v in verdict_list)
    sep = "| --- |" + " ---: |" * len(verdict_list)
    lines.append(header)
    lines.append(sep)
    for b in verdict_list:
        row_cells = [f"`{b.value}`"]
        for c in verdict_list:
            n = report.confusion[b][c]
            cell = f"**{n}**" if b == c and n > 0 else str(n)
            row_cells.append(cell)
        lines.append("| " + " | ".join(row_cells) + " |")
    lines.append("")

    if report.deltas:
        lines.append(f"## Per-entry disagreements ({len(report.deltas)})")
        lines.append("")
        lines.append("Sorted by (baseline -> candidate) so all flips of the same kind cluster.")
        lines.append("")
        # Group by (bv, cv) for readability — header per band, then the
        # entries in that band.
        current_band: tuple[str, str] | None = None
        for d in report.deltas:
            band = (d.baseline_verdict.value, d.candidate_verdict.value)
            if band != current_band:
                lines.append("")
                lines.append(
                    f"### `{band[0]}` -> `{band[1]}` "
                    f"({sum(1 for x in report.deltas if (x.baseline_verdict.value, x.candidate_verdict.value) == band)} entries)"
                )
                lines.append("")
                current_band = band
            lines.append(
                f"**`{d.entry_id}`** (baseline conf {d.baseline_confidence:.2f}, candidate conf {d.candidate_confidence:.2f})"
            )
            lines.append("")
            lines.append(f"- Baseline: {d.baseline_justification}")
            lines.append(f"- Candidate: {d.candidate_justification}")
            lines.append("")
    else:
        lines.append("## Per-entry disagreements")
        lines.append("")
        lines.append("None. Every common entry got the same verdict in both runs.")
        lines.append("")

    return "\n".join(lines)


def write_report_artifacts(
    report: AgreementReport,
    output_dir: Path,
    *,
    basename: str,
) -> tuple[Path, Path]:
    """Write ``{basename}.json`` and ``{basename}.md`` into *output_dir*.

    Mirrors the ``report.write_artifacts`` convention from
    ``memory.report`` so the two job types produce same-shaped output
    pairs and the same fileset / upload machinery works.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basename}.json"
    md_path = output_dir / f"{basename}.md"
    json_path.write_text(to_json(report) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, md_path


__all__ = [
    "AgreementReport",
    "VerdictDelta",
    "compare_runs",
    "load_triage_artifact",
    "to_json",
    "to_markdown",
    "write_report_artifacts",
]
