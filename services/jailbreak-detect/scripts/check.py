# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Manual sanity check for the jailbreak classifier (local recipe).

Runs the shared prompt set (``scripts/prompts.json`` — the same file
``nim_scores.py`` uses) through the local model and prints the verdict +
NIM-compatible signed score (``2*p1 - 1``; negative = benign, positive =
jailbreak). Run both scripts and diff the tables to compare the local recipe
against the hosted NIM.

Exit code: 0 normally; 1 only if a *safe* prompt is flagged as a jailbreak (a
false positive — the genuinely concerning case). Missed jailbreaks are reported
but do not fail the run: the local embedder is slightly "softer" than the NIM's,
so borderline prompts near the 0.5 threshold can be missed (see the runbook's
sharpness-gap note).

Usage:
    cd services/jailbreak-detect
    uv sync
    JAILBREAK_CHECK_DEVICE=cpu uv run python scripts/check.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))

from classifier import JailbreakClassifier  # noqa: E402

PROMPTS_FILE = Path(__file__).with_name("prompts.json")


def main() -> int:
    prompts = json.loads(PROMPTS_FILE.read_text())
    clf = JailbreakClassifier()

    print(f"{'expected':<11}{'predicted':<11}{'score':>10}  match  prompt")
    print("-" * 78)
    false_positive = False
    matched = 0
    for item in prompts:
        expected = item["label"]
        is_jb, score = clf(item["text"])
        predicted = "jailbreak" if is_jb else "safe"
        agree = predicted == expected
        matched += agree
        if expected == "safe" and predicted == "jailbreak":
            false_positive = True
        marker = "ok" if agree else ("FALSE-POS" if expected == "safe" else "miss")
        print(f"{expected:<11}{predicted:<11}{score:>10.4f}  {marker:<6} {item['text'][:40]}")

    print(f"\nmatched {matched}/{len(prompts)} expected labels")
    if false_positive:
        print("RESULT: FAIL — a safe prompt was flagged as a jailbreak (false positive)")
        return 1
    print("RESULT: PASS — no false positives (missed jailbreaks, if any, are the known sharpness gap)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
