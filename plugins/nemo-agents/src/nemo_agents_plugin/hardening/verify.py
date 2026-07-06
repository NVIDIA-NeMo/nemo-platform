# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify stage: check attack and benign prompts against the guardrail config.

The ``check`` callable takes a single user message and returns the guardrail
check status: "blocked", "success", or "unknown". Verification runs in isolation
against the config (no agent process). Attack replay passes when the guardrail
blocks the attack; the benign suite passes when the guardrail lets a legitimate
request through (proving the rail did not over-block).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

from nemo_agents_plugin.hardening.models import AttackHit, VerifyResult

Check = Callable[[str], str]  # user_message -> "blocked" | "success" | "unknown"


def load_benign_cases(csv_path: Path) -> list[dict[str, str]]:
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def replay_attacks(hits: list[AttackHit], check: Check) -> VerifyResult:
    """Replay each attack prompt through the guardrail; blocked = passed."""
    passed = failed = errored = 0
    detail: list[dict[str, Any]] = []
    for hit in hits:
        try:
            status = check(hit.prompt)
        except Exception as exc:  # record and continue: one check error must not abort the suite
            errored += 1
            detail.append({"probe": hit.probe, "status": "error", "error": str(exc)})
            continue
        if status == "blocked":
            passed += 1
        elif status == "success":
            failed += 1
        else:
            errored += 1
        detail.append({"probe": hit.probe, "status": status})
    return VerifyResult(total=len(hits), passed=passed, failed=failed, errored=errored, detail=detail)


def run_benign_suite(cases: list[dict[str, Any]], check: Check) -> VerifyResult:
    """Run each benign request through the guardrail; allowed (success) = passed."""
    passed = failed = errored = 0
    detail: list[dict[str, Any]] = []
    for case in cases:
        try:
            status = check(case.get("payload", ""))
        except Exception as exc:  # record and continue
            errored += 1
            detail.append({"tool": case.get("tool"), "status": "error", "error": str(exc)})
            continue
        if status == "success":
            passed += 1
        elif status == "blocked":
            failed += 1
        else:
            errored += 1
        detail.append({"tool": case.get("tool"), "status": status})
    return VerifyResult(total=len(cases), passed=passed, failed=failed, errored=errored, detail=detail)
