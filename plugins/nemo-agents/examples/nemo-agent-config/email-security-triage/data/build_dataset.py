# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regenerate smaller_test.csv with an assembled, sender-inclusive ``email`` column.

The upstream NAT dataset carries ``sender``/``subject``/``body`` as separate
columns, but the NAT eval fed the agent ``body`` only — dropping the sender, a
top phishing tell. This script derives an ``email`` column holding an
RFC-822-ish message (``From:``/``Subject:`` + blank line + body) so the agent
(and the extract_iocs tool) see the sender. The eval's question_key is ``email``.

Run from this directory:

    uv run python build_dataset.py
"""

from __future__ import annotations

import csv
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# Source of truth: the sibling NAT example's dataset.
_SOURCE = (
    _HERE.parents[2] / "email-phishing-analyzer" / "src" / "nat_email_phishing_analyzer" / "data" / "smaller_test.csv"
)
_DEST = _HERE / "smaller_test.csv"


def assemble_email(row: dict[str, str]) -> str:
    """Build an RFC-822-ish message including the From: sender header."""
    sender = (row.get("sender") or "").strip()
    if not sender:
        raise ValueError("sender is required to preserve the phishing signal")
    subject = (row.get("subject") or "").strip()
    body = (row.get("body") or "").strip()
    return f"From: {sender}\nSubject: {subject}\n\n{body}"


def main() -> None:
    with _SOURCE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise SystemExit(f"no rows read from {_SOURCE}")

    subjects = [(row.get("subject") or "").strip() for row in rows]
    duplicates = sorted({s for s in subjects if subjects.count(s) > 1})
    if duplicates:
        raise SystemExit(f"eval id_key 'subject' must be unique; duplicates: {duplicates}")

    fieldnames = [*rows[0].keys()]
    if "email" not in fieldnames:
        fieldnames.append("email")

    for row in rows:
        row["email"] = assemble_email(row)

    with _DEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows with an assembled 'email' column to {_DEST}")


if __name__ == "__main__":
    main()
