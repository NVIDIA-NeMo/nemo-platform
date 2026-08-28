# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parse Harbor CLI output into walkthrough gap progress phases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

HARBOR_TRIAL_RE = re.compile(r"^\s*(\d+)/(\d+)\s")
ORACLE_AGENT_RE = re.compile(r"\boracle\b", re.IGNORECASE)
HARBOR_RUN_ORACLE_RE = re.compile(r"harbor\s+run\b.*\s-a\s+oracle\b", re.IGNORECASE)
HARBOR_JOBS_START_RE = re.compile(r"harbor\s+jobs\s+start\b", re.IGNORECASE)
RETRY_HINT_RE = re.compile(r"\b(retry|rerun|re-run|again|revising|revise)\b", re.IGNORECASE)


class GapPhase(StrEnum):
    WAITING = "waiting"
    ORACLE = "oracle"
    TRIAL_1 = "trial-1"
    TRIAL_2 = "trial-2"
    MEASURE = "measure"
    VERIFY = "verify"
    RETRY = "retry"
    ACCEPTED = "accepted"
    FAILED = "failed"


@dataclass(slots=True)
class HarborProgressUpdate:
    """One derived progress tick from Harbor output or workspace state."""

    phase: GapPhase
    detail: str
    completed: int = 0
    total: int = 0
    attempt: int = 1
    trial_index: int = 0


@dataclass(slots=True)
class HarborProgressTracker:
    """Track oracle vs rho trial phases and detect retries from Harbor progress lines."""

    run_kind: str = "idle"
    trial_completed: int = 0
    trial_total: int = 0
    attempt: int = 1
    phase: GapPhase = GapPhase.WAITING
    detail: str = "waiting"
    trial_index: int = 0

    def start_oracle(self) -> HarborProgressUpdate:
        self.run_kind = "oracle"
        self.trial_completed = 0
        self.trial_total = 1
        self.phase = GapPhase.RETRY if self.attempt > 1 else GapPhase.ORACLE
        self.detail = _attempt_detail("oracle", self.attempt)
        self.trial_index = 0
        return self._update()

    def start_trials(self, *, total: int = 2) -> HarborProgressUpdate:
        self.run_kind = "trial"
        self.trial_completed = 0
        self.trial_total = total
        self.phase = GapPhase.RETRY if self.attempt > 1 else GapPhase.TRIAL_1
        self.trial_index = 1
        self.detail = _attempt_detail(f"rho-agent run 1/{total}", self.attempt)
        return self._update()

    def start_measure(self, *, index: int, total: int = 2) -> HarborProgressUpdate:
        self.run_kind = "measure"
        self.phase = GapPhase.MEASURE
        self.trial_index = index
        self.trial_completed = index - 1
        self.trial_total = total
        self.detail = f"measure repeat-{index}/{total}"
        return self._update()

    def start_verify(self) -> HarborProgressUpdate:
        self.run_kind = "verify"
        self.phase = GapPhase.VERIFY
        self.detail = "verify"
        self.trial_completed = self.trial_total
        return self._update()

    def mark_accepted(self) -> HarborProgressUpdate:
        self.phase = GapPhase.ACCEPTED
        self.detail = "accepted"
        return self._update()

    def mark_failed(self, reason: str) -> HarborProgressUpdate:
        self.phase = GapPhase.FAILED
        self.detail = reason
        return self._update()

    def feed_line(self, line: str) -> HarborProgressUpdate | None:
        """Update state from one Harbor stdout line; return when phase changes."""
        if HARBOR_RUN_ORACLE_RE.search(line) or (self.run_kind == "oracle" and ORACLE_AGENT_RE.search(line)):
            return self.start_oracle()
        if HARBOR_JOBS_START_RE.search(line) and self.run_kind != "trial":
            return self.start_trials()

        match = HARBOR_TRIAL_RE.match(line)
        if match is None:
            if RETRY_HINT_RE.search(line) and self.run_kind in {"oracle", "trial"}:
                self.attempt += 1
                self.trial_completed = 0
                self.phase = GapPhase.RETRY
                self.detail = _attempt_detail("backtracking after failure", self.attempt)
                return self._update()
            return None

        completed = int(match.group(1))
        total = int(match.group(2))
        previous_completed = self.trial_completed
        if self.trial_total and completed < previous_completed:
            self.attempt += 1

        self.trial_completed = completed
        self.trial_total = total

        if total <= 1:
            self.run_kind = "oracle"
            self.phase = GapPhase.RETRY if self.attempt > 1 else GapPhase.ORACLE
            self.detail = _attempt_detail("oracle", self.attempt)
        elif completed <= 0:
            self.run_kind = "trial"
            self.phase = GapPhase.RETRY if self.attempt > 1 else GapPhase.TRIAL_1
            self.trial_index = 1
            self.detail = _attempt_detail(f"rho-agent run 1/{total}", self.attempt)
        elif completed < total:
            self.run_kind = "trial"
            self.phase = GapPhase.TRIAL_2
            self.trial_index = 2
            self.detail = _attempt_detail(f"rho-agent run {completed + 1}/{total}", self.attempt)
        else:
            self.run_kind = "trial"
            self.phase = GapPhase.TRIAL_2
            self.trial_index = total
            self.detail = _attempt_detail(f"rho-agent runs {total}/{total} done", self.attempt)

        if self.attempt > 1 and self.phase in {GapPhase.ORACLE, GapPhase.TRIAL_1, GapPhase.TRIAL_2}:
            self.phase = GapPhase.RETRY

        return self._update()

    def _update(self) -> HarborProgressUpdate:
        return HarborProgressUpdate(
            phase=self.phase,
            detail=self.detail,
            completed=self.trial_completed,
            total=self.trial_total,
            attempt=self.attempt,
            trial_index=self.trial_index,
        )


def _attempt_detail(base: str, attempt: int) -> str:
    if attempt <= 1:
        return base
    return f"retry {attempt}: {base}"


def parse_harbor_trial_line(line: str) -> tuple[int, int] | None:
    """Return ``(completed, total)`` when ``line`` looks like Harbor trial progress."""
    match = HARBOR_TRIAL_RE.match(line)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def trial_dirs_under(root: Path) -> list[Path]:
    """Return sorted Harbor trial directories under ``root``."""
    if not root.is_dir():
        return []
    return sorted({path.parent.parent for path in root.rglob("agent/trajectory.json")})


def infer_gap_phase(workspace: Path, tool: str, task_slug: str) -> HarborProgressUpdate:
    """Derive the finest-grained gap phase available from workspace artifacts."""
    tracker = HarborProgressTracker()
    draft = workspace / ".eval-author" / "task-drafts" / task_slug
    if not draft.is_dir():
        return tracker._update()

    required = (
        draft / "instruction.md",
        draft / "solution" / "solve.sh",
        draft / "tests" / "test.sh",
        draft / "task.toml",
    )
    if not all(path.is_file() for path in required):
        tracker.detail = "completing Harbor files"
        tracker.phase = GapPhase.WAITING
        return tracker._update()

    measurements = workspace / ".eval-author" / "task-measurements" / task_slug
    repeat_dirs = [measurements / "repeat-1", measurements / "repeat-2"]
    reports = [measurements / "repeat-1-report.json", measurements / "repeat-2-report.json"]
    if all(report.is_file() for report in reports):
        return tracker.start_verify()

    measured = [
        (index, (repeat / "tool_calls" / "coverage.json").is_file())
        for index, repeat in enumerate(repeat_dirs, start=1)
    ]
    if any(done for _, done in measured):
        done_count = sum(1 for _, done in measured if done)
        next_index = done_count + 1 if done_count < 2 else 2
        return tracker.start_measure(index=min(next_index, 2), total=2)

    jobs_dir = workspace / ".eval-author" / "gap-jobs" / task_slug
    trials = trial_dirs_under(jobs_dir)
    attempt = _estimate_attempt(workspace, task_slug, draft=draft, jobs_dir=jobs_dir)
    tracker.attempt = attempt

    if len(trials) >= 2:
        tracker.trial_completed = 2
        tracker.trial_total = 2
        tracker.phase = GapPhase.TRIAL_2
        tracker.detail = _attempt_detail("rho-agent runs 2/2 done", attempt)
        return tracker._update()
    if len(trials) == 1:
        tracker.trial_completed = 1
        tracker.trial_total = 2
        tracker.phase = GapPhase.TRIAL_2 if attempt == 1 else GapPhase.RETRY
        tracker.trial_index = 2
        tracker.detail = _attempt_detail("rho-agent run 2/2", attempt)
        return tracker._update()

    if _draft_was_revised_after_trials(draft, jobs_dir):
        tracker.attempt = max(attempt, 2)
        return tracker.start_oracle()

    tracker.phase = GapPhase.RETRY if attempt > 1 else GapPhase.ORACLE
    tracker.detail = _attempt_detail("oracle", tracker.attempt)
    tracker.trial_total = 1
    return tracker._update()


def _estimate_attempt(workspace: Path, task_slug: str, *, draft: Path, jobs_dir: Path) -> int:
    """Guess retry attempt from job directories and draft rewrites."""
    attempt = 1
    if jobs_dir.is_dir():
        attempt = max(attempt, len(trial_dirs_under(jobs_dir)))
    parent = workspace / ".eval-author" / "gap-jobs"
    if parent.is_dir():
        sibling_runs = sum(1 for path in parent.iterdir() if path.is_dir() and task_slug in path.name)
        attempt = max(attempt, sibling_runs)
    if _draft_was_revised_after_trials(draft, jobs_dir):
        attempt = max(attempt, 2)
    return attempt


def _draft_was_revised_after_trials(draft: Path, jobs_dir: Path) -> bool:
    if not jobs_dir.is_dir():
        return False
    try:
        draft_mtime = max(path.stat().st_mtime_ns for path in draft.rglob("*") if path.is_file())
    except OSError:
        return False
    for path in jobs_dir.rglob("*"):
        if path.is_file() and path.stat().st_mtime_ns < draft_mtime:
            return True
    return False
