# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared data types for the eval runner, analyzer, and self-improvement loop."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class EvalStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class EvalSpec:
    """Discovered eval metadata from task.toml."""

    name: str
    path: Path
    difficulty: Difficulty
    category: str
    tags: list[str]
    agent_timeout_sec: float
    verifier_timeout_sec: float


@dataclass
class EvalTiming:
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_sec: float = 0.0


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ToolCallSummary:
    total: int = 0
    by_name: dict[str, int] = field(default_factory=dict)
    error_count: int = 0


@dataclass
class EvalResult:
    """Result of an eval — single trial OR median aggregate of N trials."""

    eval_name: str
    status: EvalStatus
    reward: float | None = None
    timing: EvalTiming = field(default_factory=EvalTiming)
    agent_timing: EvalTiming = field(default_factory=EvalTiming)
    tokens: TokenUsage = field(default_factory=TokenUsage)
    tool_calls: ToolCallSummary = field(default_factory=ToolCallSummary)
    exception: str | None = None
    job_dir: Path | None = None
    session_file: Path | None = None
    # Variance metadata — populated when repeats > 1
    trials_count: int = 1
    trial_pass_count: int = 0  # number of trials that passed (out of trials_count)

    @property
    def passed(self) -> bool:
        return self.status == EvalStatus.PASS


@dataclass
class BatchResult:
    """Results from a full batch run."""

    batch_id: str
    started_at: datetime
    finished_at: datetime | None = None
    model: str = ""
    agent: str = "claude-code"
    results: list[EvalResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == EvalStatus.FAIL)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.status == EvalStatus.ERROR)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return self.pass_count / len(self.results)

    def get_result(self, eval_name: str) -> EvalResult | None:
        for r in self.results:
            if r.eval_name == eval_name:
                return r
        return None


@dataclass
class BaselineSnapshot:
    """A single point-in-time observation for an eval."""

    timestamp: str
    batch_id: str
    status: str
    duration_sec: float
    tool_calls: int


@dataclass
class BaselineEntry:
    eval_name: str
    best_duration_sec: float
    best_batch_id: str
    pass_count: int
    total_count: int
    avg_duration_sec: float
    avg_tool_calls: int
    history: list[BaselineSnapshot] = field(default_factory=list)


# --- Analyzer types ---


class GapCategory(str, Enum):
    MISSING_SKILL = "missing_skill"
    INADEQUATE_SKILL = "inadequate_skill"
    CLI_GAP = "cli_gap"
    CLI_ERGONOMICS = "cli_ergonomics"
    FUNDAMENTAL = "fundamental"


@dataclass
class EvalCluster:
    """A group of evals that share error patterns or behavioral signals."""

    cluster_id: str
    eval_names: list[str]
    shared_patterns: list[str]
    signal_type: str  # "error_pattern", "missing_skill", "unclustered", "new_eval", "slow_outlier", "tool_heavy"
    description: str = ""


@dataclass
class Hypothesis:
    cluster_id: str
    eval_names: list[str]
    root_cause: str
    category: GapCategory
    proposed_fix: str
    affected_files: list[str]
    expected_impact: str
    confidence: float  # 0.0-1.0

    @property
    def eval_name(self) -> str:
        """Back-compat: return first eval or summary.

        ``llm._parse_hypotheses()`` and ``load_loop_state()`` can both produce
        a Hypothesis with ``eval_names=[]``; fall back to the cluster id so
        callers don't IndexError before validation runs.
        """
        if not self.eval_names:
            return self.cluster_id or "(unknown)"
        if len(self.eval_names) == 1:
            return self.eval_names[0]
        return f"{self.eval_names[0]}+{len(self.eval_names) - 1}more"


@dataclass
class SkillUsage:
    """Tracks which skills were loaded per eval."""

    skills_by_eval: dict[str, list[str]]  # eval_name -> [skill names loaded]
    evals_without_skills: list[str]  # evals where no skill was loaded


@dataclass
class MechanicalAnalysis:
    """Python-computed analysis without LLM."""

    failing_evals: list[str]
    slowest_evals: list[tuple[str, float]]  # (name, duration_sec)
    highest_tool_count: list[tuple[str, int]]  # (name, count)
    error_patterns: dict[str, list[str]]  # pattern -> eval_names
    regressions: list[str]  # vs baseline
    tool_usage_distribution: dict[str, int]  # tool_name -> total_calls
    skill_usage: SkillUsage | None = None  # which skills were loaded per eval


@dataclass
class GapAnalysis:
    batch_id: str
    mechanical: MechanicalAnalysis
    clusters: list[EvalCluster]
    hypotheses: list[Hypothesis]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Loop types ---


@dataclass
class AppliedHypothesis:
    """One hypothesis's edits, captured as a standalone commit on the iteration branch.

    Carries enough attribution to revert this hypothesis alone (commit_sha) and
    to ask "which evals was this hypothesis claiming to fix" (cluster_id maps
    back to the matching Hypothesis in IterationRecord.hypotheses).
    """

    cluster_id: str
    commit_sha: str
    changed_files: list[str]
    explanation: str = ""


@dataclass
class IterationRecord:
    iteration: int
    hypotheses: list[Hypothesis]
    branch_name: str
    changes_made: list[str]
    eval_results_before: dict[str, float]  # eval_name -> duration
    eval_results_after: dict[str, float]
    improvement_pct: float
    status: str  # "improved", "regressed", "neutral", "error"
    mr_url: str | None = None
    applied: list[AppliedHypothesis] = field(default_factory=list)


@dataclass
class LoopState:
    iteration: int = 0
    iterations: list[IterationRecord] = field(default_factory=list)
    current_baseline_batch: str = ""

    def was_tried(self, hypothesis: Hypothesis) -> bool:
        """Check if a similar hypothesis was already tried this run.

        Keys on ``cluster_id`` + ``category`` only. The previous version also
        compared ``proposed_fix`` verbatim, which let the LLM bypass dedup by
        rephrasing the same fix — observed in practice when a destructive
        broad-refactor hypothesis got picked twice in two consecutive
        iterations under slightly different wording.
        """
        for record in self.iterations:
            for prev_h in record.hypotheses:
                if prev_h.cluster_id == hypothesis.cluster_id and prev_h.category == hypothesis.category:
                    return True
        return False


# --- Serialization helpers ---


def _serialize(obj: object) -> Any:
    """JSON serialization helper for dataclasses."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [_serialize(item) for item in obj]
    return obj


def _serialize_dict(obj: object) -> dict[str, Any]:
    """Serialize a dataclass-like object that is expected to produce a mapping."""
    serialized = _serialize(obj)
    if not isinstance(serialized, dict):
        raise TypeError(f"Expected serialized {type(obj).__name__} to be a mapping, got {type(serialized).__name__}.")
    result: dict[str, Any] = {}
    for key, value in serialized.items():
        if not isinstance(key, str):
            raise TypeError(f"Expected serialized {type(obj).__name__} key to be str, got {type(key).__name__}.")
        result[key] = value
    return result


def to_json(obj: object, indent: int = 2) -> str:
    """Serialize a dataclass to JSON string."""
    return json.dumps(_serialize(obj), indent=indent)
