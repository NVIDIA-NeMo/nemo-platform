# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic verifier-phase mechanic: collect a reward + stamp attempt metadata.

This is the backend-agnostic core. *What* the verifier runs (command, env,
mounts) and *how* it is invoked are caller concerns — the caller executes its
verifier through an environment handle, then uses :func:`collect_verifier_outcome`
to read the reward/stdout convention out of the verifier's log dir, and
:func:`apply_verify_to_metadata` to stamp the result onto an attempt so a
reward metric can score it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerifierOutcome:
    """Result of a verifier phase for one task."""

    ran: bool
    passed: bool
    reward: int
    exit_code: int
    stdout: str
    verifier_log_dir: Path | None


def skipped_outcome() -> VerifierOutcome:
    """Outcome representing a verifier that did not run."""
    return VerifierOutcome(ran=False, passed=False, reward=0, exit_code=0, stdout="", verifier_log_dir=None)


def collect_verifier_outcome(
    *,
    ok: bool,
    exit_code: int,
    log_dir: str | Path,
    reward_filename: str = "reward.txt",
    stdout_filename: str = "test-stdout.txt",
) -> VerifierOutcome:
    """Build a :class:`VerifierOutcome` from a verifier run's log dir.

    Reads ``reward.txt`` (``1``/``0``) when present; otherwise derives the reward
    from ``ok`` and writes the file so reruns are stable. Reads ``test-stdout.txt``
    when present.
    """
    log_dir = Path(log_dir)
    passed = ok

    stdout = ""
    stdout_path = log_dir / stdout_filename
    if stdout_path.is_file():
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")

    reward_path = log_dir / reward_filename
    if reward_path.is_file():
        reward = 1 if reward_path.read_text(encoding="utf-8").strip() == "1" else 0
    else:
        reward = 1 if passed else 0
        reward_path.parent.mkdir(parents=True, exist_ok=True)
        reward_path.write_text("1\n" if passed else "0\n", encoding="utf-8")

    return VerifierOutcome(
        ran=True,
        passed=passed,
        reward=reward,
        exit_code=exit_code,
        stdout=stdout,
        verifier_log_dir=log_dir,
    )


def apply_verify_to_metadata(metadata: dict[str, Any], outcome: VerifierOutcome) -> None:
    """Stamp verifier reward/status onto attempt metadata for scoring + gating."""
    if not outcome.ran:
        metadata.setdefault("verify_status", "skipped")
        return
    metadata["verify_status"] = "ok" if outcome.passed else "failed"
    metadata["passed"] = outcome.passed
    metadata["reward"] = outcome.reward
    metadata["verifier_log_dir"] = str(outcome.verifier_log_dir) if outcome.verifier_log_dir else None
