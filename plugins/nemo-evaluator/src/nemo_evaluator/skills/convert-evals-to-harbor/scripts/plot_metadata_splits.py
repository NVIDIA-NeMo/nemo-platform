#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generate SVG pie charts for dataset metadata split distributions.

Reads task.toml files under tasks/<dataset>/{train,validation,test}/ and writes:
  - one <metadata>_by_split_pies.svg per metadata dimension
  - metadata_split_counts.json
  - index.html

Usage:
  python scripts/plot_metadata_splits.py terminal-bench-ii
  python scripts/plot_metadata_splits.py terminal-bench-ii --dimensions difficulty category
  python scripts/plot_metadata_splits.py cve-analysis --output-dir /tmp/dataset_registry_plots
"""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from collections import Counter
from pathlib import Path

SPLITS = ("train", "validation", "test")
SPLIT_TITLES = {"train": "Train", "validation": "Validation", "test": "Test"}
COLORS = (
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
    "#9c755f",
    "#bab0ac",
    "#2f4b7c",
    "#665191",
    "#a05195",
    "#d45087",
    "#f95d6a",
    "#ff7c43",
    "#ffa600",
    "#1b9e77",
    "#d95f02",
    "#7570b3",
    "#e7298a",
    "#66a61e",
    "#e6ab02",
    "#a6761d",
    "#666666",
    "#17becf",
    "#bcbd22",
    "#8c564b",
    "#9467bd",
    "#7f7f7f",
)


def find_registry_dir() -> Path:
    """Find repo root containing tasks/ from either cwd or script location."""
    candidates = [Path.cwd(), *Path.cwd().parents]
    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir, *script_dir.parents])

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "tasks").is_dir():
            return candidate
    return script_dir.parent.parent


def escape(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def format_metadata_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def metadata_value_labels(metadata: dict, dimension: str) -> list[str]:
    if dimension not in metadata:
        return ["<missing>"]

    value = metadata[dimension]
    if value is None:
        return ["<missing>"]
    if isinstance(value, list):
        if not value:
            return ["<empty>"]
        return [format_metadata_value(item) for item in value]
    return [format_metadata_value(value)]


def iter_task_dirs(split_dir: Path) -> list[Path]:
    if not split_dir.exists():
        return []

    tasks = []
    for entry in sorted(split_dir.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "task.toml").exists():
            tasks.append(entry)
            continue
        for subdir in sorted(entry.iterdir()):
            if subdir.is_dir() and (subdir / "task.toml").exists():
                tasks.append(subdir)
                break
    return tasks


def collect_rows(dataset_dir: Path) -> list[dict]:
    rows = []
    for split in SPLITS:
        for task_dir in iter_task_dirs(dataset_dir / split):
            with (task_dir / "task.toml").open("rb") as f:
                data = tomllib.load(f)
            rows.append(
                {
                    "split": split,
                    "task": task_dir.name,
                    "metadata": data.get("metadata", {}),
                }
            )
    return rows


def polar(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def render_pie(
    counts: Counter[str],
    values: list[str],
    color_for: dict[str, str],
    cx: float,
    cy: float,
    radius: float,
) -> str:
    total = sum(counts.get(value, 0) for value in values)
    if total == 0:
        return ""

    angle = -math.pi / 2
    parts = []
    for value in values:
        count = counts.get(value, 0)
        if count == 0:
            continue

        frac = count / total
        next_angle = angle + frac * 2 * math.pi
        x1, y1 = polar(cx, cy, radius, angle)
        x2, y2 = polar(cx, cy, radius, next_angle)
        large_arc = 1 if next_angle - angle > math.pi else 0
        if frac >= 0.999999:
            path = (
                f"M {cx} {cy} m 0 {-radius} "
                f"a {radius} {radius} 0 1 1 0 {2 * radius} "
                f"a {radius} {radius} 0 1 1 0 {-2 * radius}"
            )
        else:
            path = f"M {cx} {cy} L {x1:.2f} {y1:.2f} A {radius} {radius} 0 {large_arc} 1 {x2:.2f} {y2:.2f} Z"

        parts.append(
            f'<path d="{path}" fill="{color_for[value]}" stroke="#fff" stroke-width="1">'
            f"<title>{escape(value)}: {count} ({frac:.1%})</title></path>"
        )
        if frac >= 0.08:
            label_x, label_y = polar(cx, cy, radius * 0.63, (angle + next_angle) / 2)
            parts.append(
                f'<text x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="middle" '
                f'dominant-baseline="middle" class="slice-label">{count}</text>'
            )
        angle = next_angle
    return "\n".join(parts)


def render_svg(dataset: str, dimension: str, by_split: dict[str, Counter[str]], totals: Counter[str]) -> str:
    values = sorted(totals, key=lambda value: (-totals[value], value))
    color_for = {value: COLORS[index % len(COLORS)] for index, value in enumerate(values)}

    width = 1280
    pie_y = 230
    pie_radius = 118
    pie_xs = (220, 640, 1060)
    legend_cols = 3 if len(values) > 35 else 2 if len(values) > 16 else 1
    legend_col_width = 410 if legend_cols == 3 else 600 if legend_cols == 2 else 1000
    rows_per_col = math.ceil(len(values) / legend_cols)
    legend_y = 410
    row_height = 23
    height = legend_y + rows_per_col * row_height + 78

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        (
            "<style>"
            "text{font-family:Inter,Arial,sans-serif;fill:#1f2933}"
            ".title{font-size:26px;font-weight:700}"
            ".subtitle{font-size:14px;fill:#52606d}"
            ".split-title{font-size:18px;font-weight:700}"
            ".split-total{font-size:13px;fill:#52606d}"
            ".slice-label{font-size:14px;font-weight:700;fill:#fff;paint-order:stroke;stroke:#25313f;stroke-width:2px}"
            ".legend{font-size:12px}"
            ".legend-count{font-size:11px;fill:#52606d}"
            "</style>"
        ),
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="48" y="48" class="title">{escape(dataset)}: {escape(dimension)} by split</text>',
        (
            '<text x="48" y="74" class="subtitle">'
            "Pie charts show split composition. Legend totals are train / validation / test counts."
            "</text>"
        ),
    ]

    for index, split in enumerate(SPLITS):
        cx = pie_xs[index]
        total = sum(by_split[split].values())
        parts.append(f'<text x="{cx}" y="112" text-anchor="middle" class="split-title">{SPLIT_TITLES[split]}</text>')
        parts.append(f'<text x="{cx}" y="134" text-anchor="middle" class="split-total">{total} labels</text>')
        parts.append(render_pie(by_split[split], values, color_for, cx, pie_y, pie_radius))

    parts.append(f'<text x="48" y="{legend_y - 26}" class="split-title">Legend</text>')
    for index, value in enumerate(values):
        col = index // rows_per_col
        row = index % rows_per_col
        x = 48 + col * legend_col_width
        y = legend_y + row * row_height
        train_count, val_count, test_count = (by_split[split].get(value, 0) for split in SPLITS)
        shown = value if len(value) <= 42 else value[:39] + "..."
        parts.append(f'<rect x="{x}" y="{y - 12}" width="13" height="13" fill="{color_for[value]}"/>')
        parts.append(f'<text x="{x + 20}" y="{y}" class="legend"><title>{escape(value)}</title>{escape(shown)}</text>')
        parts.append(
            f'<text x="{x + 275}" y="{y}" class="legend-count">'
            f"{totals[value]} total; {train_count}/{val_count}/{test_count}</text>"
        )

    parts.append("</svg>")
    return "\n".join(parts)


def write_outputs(dataset: str, rows: list[dict], dimensions: list[str], output_root: Path) -> Path:
    output_dir = output_root / dataset
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "dataset": dataset,
        "num_tasks": len(rows),
        "split_counts": dict(Counter(row["split"] for row in rows)),
        "metadata": {},
    }
    svg_files = []

    for dimension in dimensions:
        by_split: dict[str, Counter[str]] = {split: Counter() for split in SPLITS}
        totals: Counter[str] = Counter()
        for row in rows:
            for value in metadata_value_labels(row["metadata"], dimension):
                by_split[row["split"]][value] += 1
                totals[value] += 1

        summary["metadata"][dimension] = {
            "totals": dict(sorted(totals.items(), key=lambda item: (-item[1], item[0]))),
            "by_split": {
                split: dict(sorted(by_split[split].items(), key=lambda item: (-item[1], item[0]))) for split in SPLITS
            },
        }

        svg_name = f"{dimension}_by_split_pies.svg"
        (output_dir / svg_name).write_text(render_svg(dataset, dimension, by_split, totals))
        svg_files.append(svg_name)

    (output_dir / "metadata_split_counts.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    html = [
        f'<!doctype html><meta charset="utf-8"><title>{escape(dataset)}</title>',
        '<body style="margin:24px;font-family:Inter,Arial,sans-serif">',
        f"<h1>{escape(dataset)}</h1>",
    ]
    for svg_name in svg_files:
        html.append(
            f"<h2>{escape(svg_name)}</h2>"
            f'<img src="{escape(svg_name)}" style="max-width:100%;height:auto;border:1px solid #d9e2ec">'
        )
    html.append("</body>")
    (output_dir / "index.html").write_text("\n".join(html) + "\n")
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", help="Dataset name under tasks/")
    parser.add_argument(
        "--dimensions",
        nargs="+",
        help="Metadata dimensions to plot (default: all dimensions present in task.toml)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/dataset_registry_plots"),
        help="Root output directory (default: /tmp/dataset_registry_plots)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_dir = find_registry_dir()
    dataset_dir = registry_dir / "tasks" / args.dataset
    if not dataset_dir.exists():
        raise SystemExit(f"ERROR: {dataset_dir} does not exist.")

    rows = collect_rows(dataset_dir)
    if not rows:
        raise SystemExit(f"ERROR: no tasks found under {dataset_dir}.")

    if args.dimensions:
        dimensions = sorted(dict.fromkeys(args.dimensions))
    else:
        dimensions = sorted({key for row in rows for key in row["metadata"].keys()})
    if not dimensions:
        raise SystemExit("ERROR: no metadata dimensions found.")

    output_dir = write_outputs(args.dataset, rows, dimensions, args.output_dir)
    print(f"Output: {output_dir}")
    print(f"Tasks: {len(rows)}")
    print(f"Dimensions: {', '.join(dimensions)}")


if __name__ == "__main__":
    main()
