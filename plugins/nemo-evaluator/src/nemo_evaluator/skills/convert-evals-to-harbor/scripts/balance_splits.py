#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check split balance across task metadata.

Reads task.toml files under tasks/<dataset>/{train,validation,test}/ and
reports per-metadata distribution by split.

Target proportions: train = 1.5 * val = 1.5 * test.
With N total tasks the targets are:
  train      ~ N * 3/7  (~43%)
  validation ~ N * 2/7  (~28.5%)
  test       ~ N * 2/7  (~28.5%)

Usage:
  python scripts/balance_splits.py <dataset>
  python scripts/balance_splits.py tau2-bench
  python scripts/balance_splits.py tau2-bench --tolerance 0.10
  python scripts/balance_splits.py terminal-bench-ii --dimensions difficulty category
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tomllib
from collections import Counter
from pathlib import Path


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


REGISTRY_DIR = find_registry_dir()
SPLITS = ("train", "validation", "test")
# train : val : test = 1.5 : 1 : 1  →  3 : 2 : 2
SPLIT_WEIGHTS = {"train": 3, "validation": 2, "test": 2}
TOTAL_WEIGHT = sum(SPLIT_WEIGHTS.values())  # 7


def load_metadata(task_dir: Path) -> dict:
    toml_path = task_dir / "task.toml"
    if not toml_path.exists():
        return {}
    with toml_path.open("rb") as f:
        data = tomllib.load(f)
    return data.get("metadata", {})


def iter_tasks(split_dir: Path) -> list[Path]:
    tasks = []
    for entry in sorted(split_dir.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "task.toml").exists():
            tasks.append(entry)
        else:
            for sub in sorted(entry.iterdir()):
                if sub.is_dir() and (sub / "task.toml").exists():
                    tasks.append(sub)
                    break
    return tasks


def collect(dataset_dir: Path) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for split in SPLITS:
        split_dir = dataset_dir / split
        if not split_dir.exists():
            result[split] = []
            continue
        tasks = iter_tasks(split_dir)
        result[split] = [load_metadata(t) for t in tasks]
    return result


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


def metadata_value_labels(metadata: dict, dim: str) -> list[str]:
    if dim not in metadata:
        return ["<missing>"]

    value = metadata[dim]
    if value is None:
        return ["<missing>"]
    if isinstance(value, list):
        if not value:
            return ["<empty>"]
        return [format_metadata_value(item) for item in value]
    return [format_metadata_value(value)]


def target_counts(total: int) -> dict[str, int]:
    raw = {split: total * SPLIT_WEIGHTS[split] / TOTAL_WEIGHT for split in SPLITS}
    counts = {split: math.floor(raw[split]) for split in SPLITS}
    remainder = total - sum(counts.values())
    for split in sorted(SPLITS, key=lambda s: raw[s] - counts[s], reverse=True)[:remainder]:
        counts[split] += 1
    return counts


def check_balance(
    splits: dict[str, list[dict]],
    tolerance: float,
    dimensions: list[str] | None = None,
) -> bool:
    total = sum(len(v) for v in splits.values())
    if total == 0:
        print("No tasks found.")
        return False

    ok = True
    print(f"\nTotal tasks: {total}")
    print(f"Target proportions: train=3/7 ({3 / 7:.1%}), val=2/7 ({2 / 7:.1%}), test=2/7 ({2 / 7:.1%})")
    print(f"Tolerance: ±{tolerance:.0%}\n")

    for split in SPLITS:
        n = len(splits[split])
        target_frac = SPLIT_WEIGHTS[split] / TOTAL_WEIGHT
        actual_frac = n / total if total else 0
        delta = abs(actual_frac - target_frac)
        status = "OK" if delta <= tolerance else "WARN"
        if status == "WARN":
            ok = False
        print(f"  {split:12s}: {n:4d} tasks  ({actual_frac:.1%} vs target {target_frac:.1%})  [{status}]")
    # find dimensions in the metadata
    if dimensions is None:
        dimensions_set = set()
        for split in SPLITS:
            for task in splits[split]:
                dimensions_set.update(task.keys())
        dimensions = sorted(dimensions_set)
    else:
        dimensions = sorted(dimensions)
    print(f"\nDimensions: {sorted(dimensions)}")
    # per-dimension breakdown
    for dim in sorted(dimensions):
        split_counts = {
            split: Counter(label for metadata in splits[split] for label in metadata_value_labels(metadata, dim))
            for split in SPLITS
        }
        all_vals = sorted({label for counts in split_counts.values() for label in counts})
        if not all_vals:
            continue
        print(f"\n  {dim} breakdown:")
        for val in all_vals:
            counts = {s: split_counts[s][val] for s in SPLITS}
            row = "  ".join(f"{s}={counts[s]}" for s in SPLITS)
            totals_for_val = sum(counts.values())
            expected = target_counts(totals_for_val)
            allowed_delta = max(1, math.ceil(tolerance * totals_for_val))
            imbalanced = any(abs(counts[s] - expected[s]) > allowed_delta for s in SPLITS)
            flag = "  WARN" if imbalanced else ""
            if imbalanced:
                ok = False
            target_row = "  ".join(f"{s}~{expected[s]}" for s in SPLITS)
            print(f"    {val[:80]:80s}: {row}  target {target_row}{flag}")

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", help="Dataset name (subdirectory of tasks/)")
    parser.add_argument(
        "--tolerance", type=float, default=0.05, help="Allowed deviation from target proportion (default 0.05 = 5%%)"
    )
    parser.add_argument(
        "--dimensions",
        nargs="+",
        help="Metadata dimensions to check (default: all dimensions present in task.toml)",
    )
    args = parser.parse_args()

    dataset_dir = REGISTRY_DIR / "tasks" / args.dataset
    if not dataset_dir.exists():
        print(f"ERROR: {dataset_dir} does not exist.")
        sys.exit(1)

    splits = collect(dataset_dir)
    ok = check_balance(splits, args.tolerance, args.dimensions)
    print()
    if ok:
        print("Balance OK.")
    else:
        print("Balance WARN: splits deviate from target proportions.")
        sys.exit(1)


if __name__ == "__main__":
    main()
