# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-run analyzer for the nemo-guardrails IGW benchmark.

Reads the ``profile_export_aiperf.csv`` files produced by both benchmark
variants in a single run directory and prints a side-by-side latency table:
``with``, ``without``, and the ``Δ`` per concurrency level.

The delta is what answers the question "how much latency does the guardrails
middleware add", since the only thing that differs between the two variants
is whether the middleware is attached to the targeted VirtualModel.

Used two ways:

* Standalone:
  ``python -m nemo_guardrails_plugin.benchmarks.analyze <run-dir>``
* Auto-invoked from ``run.py`` at the end of a sweep that ran both variants.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from nemo_guardrails_plugin.benchmarks.constants import (
    VARIANT_WITH_GUARDRAILS,
    VARIANT_WITHOUT_GUARDRAILS,
)

log = logging.getLogger(__name__)

# Concurrency levels we expect from the sweep config. The analyzer only
# reports on levels that exist in both variants; missing rungs are skipped
# silently rather than failing, since a partial run can still be informative.
_EXPECTED_CONCURRENCIES = (1, 2, 4, 8, 16, 32, 64)

# Metric we read from `profile_export_aiperf.csv`. AIPerf reports a number of
# metrics; this one is end-to-end request wall time including the shim hop,
# IGW, middleware, and any mock-NIM round-trips.
_LATENCY_METRIC = "Request Latency (ms)"


@dataclass(frozen=True)
class LatencyRow:
    """Per-concurrency latency stats parsed from one AIPerf CSV."""

    concurrency: int
    avg: float
    p50: float
    p90: float
    p99: float
    std: float


@dataclass(frozen=True)
class ComparisonRow:
    """Side-by-side comparison of one concurrency level across variants."""

    concurrency: int
    with_guardrails: LatencyRow
    without_guardrails: LatencyRow

    @property
    def delta_p50(self) -> float:
        return self.with_guardrails.p50 - self.without_guardrails.p50

    @property
    def delta_p90(self) -> float:
        return self.with_guardrails.p90 - self.without_guardrails.p90

    @property
    def delta_avg(self) -> float:
        return self.with_guardrails.avg - self.without_guardrails.avg


def load_variant_results(variant_output_dir: Path) -> dict[int, LatencyRow]:
    """Load per-concurrency latency stats for one variant.

    Walks the same ``<batch>/<timestamp>/concurrency<N>/`` layout that
    ``collect_sweep_results`` produces. Missing files are logged and skipped
    rather than raising, so a partial run still produces a useful table.
    """
    if not variant_output_dir.is_dir():
        return {}

    rows: dict[int, LatencyRow] = {}
    for batch_dir in sorted(p for p in variant_output_dir.iterdir() if p.is_dir()):
        for timestamp_dir in sorted(p for p in batch_dir.iterdir() if p.is_dir()):
            for sweep_dir in sorted(p for p in timestamp_dir.iterdir() if p.is_dir()):
                concurrency = _parse_concurrency_from_label(sweep_dir.name)
                if concurrency is None:
                    continue
                csv_path = sweep_dir / "profile_export_aiperf.csv"
                row = _read_latency_row(csv_path, concurrency)
                if row is not None:
                    rows[concurrency] = row
    return rows


def compare(
    with_rows: dict[int, LatencyRow],
    without_rows: dict[int, LatencyRow],
) -> list[ComparisonRow]:
    """Build per-concurrency comparison rows, ordered by concurrency.

    Only concurrencies present in *both* variants are included; an asymmetry
    means one variant failed for that level and the comparison is undefined.
    """
    shared = sorted(set(with_rows) & set(without_rows))
    return [ComparisonRow(c, with_rows[c], without_rows[c]) for c in shared]


def format_table(rows: list[ComparisonRow]) -> str:
    """Render the comparison as a fixed-width text table."""
    if not rows:
        return "No comparable sweep results found (need both variants to share concurrency levels)."

    header = ("conc", "with p50", "w/o p50", "Δ p50", "with p90", "w/o p90", "Δ p90", "with avg", "w/o avg", "Δ avg")
    fmt = "{:>4}  {:>9}  {:>9}  {:>9}  {:>9}  {:>9}  {:>9}  {:>9}  {:>9}  {:>9}"
    lines = [fmt.format(*header), "-" * 109]
    for r in rows:
        lines.append(
            fmt.format(
                r.concurrency,
                f"{r.with_guardrails.p50:.0f}",
                f"{r.without_guardrails.p50:.0f}",
                f"{r.delta_p50:+.0f}",
                f"{r.with_guardrails.p90:.0f}",
                f"{r.without_guardrails.p90:.0f}",
                f"{r.delta_p90:+.0f}",
                f"{r.with_guardrails.avg:.0f}",
                f"{r.without_guardrails.avg:.0f}",
                f"{r.delta_avg:+.0f}",
            )
        )
    lines.append("")
    lines.append("All values in milliseconds. 'Δ' = with-guardrails minus without-guardrails.")
    return "\n".join(lines)


def analyze_run(run_dir: Path) -> str:
    """Top-level: read both variants from one run dir and return a printable table."""
    aiperf_dir = run_dir / "aiperf_results"
    with_rows = load_variant_results(aiperf_dir / VARIANT_WITH_GUARDRAILS)
    without_rows = load_variant_results(aiperf_dir / VARIANT_WITHOUT_GUARDRAILS)

    if not with_rows and not without_rows:
        return f"No AIPerf results found under {aiperf_dir}"
    if not with_rows or not without_rows:
        # Single-variant run: dump whichever side is present without trying
        # to compute deltas.
        only = with_rows or without_rows
        which = VARIANT_WITH_GUARDRAILS if with_rows else VARIANT_WITHOUT_GUARDRAILS
        return _format_single_variant(which, only)

    rows = compare(with_rows, without_rows)
    return format_table(rows)


def _format_single_variant(variant: str, rows: dict[int, LatencyRow]) -> str:
    """Render one variant's table when the other variant didn't run."""
    fmt = "{:>4}  {:>9}  {:>9}  {:>9}  {:>9}"
    lines = [
        f"Only one variant present: {variant}",
        fmt.format("conc", "avg", "p50", "p90", "std"),
        "-" * 49,
    ]
    for c in sorted(rows):
        r = rows[c]
        lines.append(fmt.format(c, f"{r.avg:.0f}", f"{r.p50:.0f}", f"{r.p90:.0f}", f"{r.std:.0f}"))
    lines.append("")
    lines.append("All values in milliseconds.")
    return "\n".join(lines)


def _parse_concurrency_from_label(label: str) -> int | None:
    """Extract the integer N from a sweep label like ``concurrency16``.

    Returns ``None`` for labels that don't match the expected pattern so
    unrelated subdirectories (logs, etc.) are skipped silently.
    """
    if not label.startswith("concurrency"):
        return None
    try:
        return int(label.removeprefix("concurrency"))
    except ValueError:
        return None


def _read_latency_row(csv_path: Path, concurrency: int) -> LatencyRow | None:
    """Pull the ``Request Latency (ms)`` line out of an AIPerf CSV.

    AIPerf writes a header row followed by one ``Metric,avg,min,max,sum,p1,...``
    row per metric, then a blank line and a second small block. We only care
    about the first block.
    """
    if not csv_path.is_file():
        log.debug("Missing CSV at %s; skipping", csv_path)
        return None

    try:
        with csv_path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header or header[0] != "Metric":
                log.warning("Unexpected header in %s: %s", csv_path, header)
                return None
            try:
                col = {name: header.index(name) for name in ("avg", "p50", "p90", "p99", "std")}
            except ValueError as exc:
                log.warning("Missing expected column in %s: %s", csv_path, exc)
                return None
            for row in reader:
                if not row:
                    break  # end of first block
                if row[0] == _LATENCY_METRIC:
                    return LatencyRow(
                        concurrency=concurrency,
                        avg=float(row[col["avg"]]),
                        p50=float(row[col["p50"]]),
                        p90=float(row[col["p90"]]),
                        p99=float(row[col["p99"]]),
                        std=float(row[col["std"]]),
                    )
    except (OSError, ValueError, IndexError) as exc:
        log.warning("Failed to parse %s: %s", csv_path, exc)
        return None

    log.warning("Did not find '%s' row in %s", _LATENCY_METRIC, csv_path)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nemo-guardrails-benchmark-analyze",
        description=__doc__,
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help=("Path to a run directory under `plugins/nemo-guardrails/benchmarks/artifacts/runs/<timestamp>/`."),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    run_dir: Path = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"Not a directory: {run_dir}", file=sys.stderr)
        return 2

    print(analyze_run(run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
