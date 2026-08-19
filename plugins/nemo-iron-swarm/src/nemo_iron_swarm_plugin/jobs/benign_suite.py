# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read/write iron-swarm's benign suite (``requests.csv``).

The plugin runs iron-swarm by subprocess (separate venv), so it can't import iron-swarm to parse the
suite. This module reproduces the CSV shape ``tool,payload,label,rationale,persona`` (iron-swarm
``profile_writer`` writer / ``smart_benign.validator._load_requests`` reader). The plugin hands the
written file to ``iron-swarm run --benign-suite <path>``, which seeds it into the target's own
``requests.csv`` — so the plugin no longer needs to mirror iron-swarm's internal on-disk layout.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Column order iron-swarm's profile_writer emits and _load_requests expects.
SUITE_FIELDS = ("tool", "payload", "label", "rationale", "persona")


def read_suite(csv_path: str | Path) -> list[dict[str, str]]:
    """Parse a benign ``requests.csv`` into a list of row dicts.

    Skips rows missing ``tool``/``payload`` (mirrors iron-swarm's ``_load_requests``). Returns ``[]`` when
    the file is absent so callers can detect an unsynthesized suite.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    suite: list[dict[str, str]] = []
    for row in rows:
        if not (row.get("tool") and row.get("payload")):
            continue
        suite.append({field: (row.get(field) or "") for field in SUITE_FIELDS})
    return suite


def write_suite(csv_path: str | Path, suite: list[dict[str, str]]) -> None:
    """Write *suite* back to ``requests.csv`` in iron-swarm's column order.

    Creates the parent dir if needed. Never touches ``input_hash.txt`` so ``--reuse-benign`` still treats
    the suite as a valid cache hit.
    """
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(SUITE_FIELDS)
        for row in suite:
            writer.writerow([row.get(field, "") for field in SUITE_FIELDS])
