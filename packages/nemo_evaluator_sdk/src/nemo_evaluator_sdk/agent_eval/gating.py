# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic gating + provenance comparison over an agent-eval run bundle.

Persistence of the run bundle (``tasks.jsonl``/``attempts.jsonl``/
``results.jsonl``/``summary.json``/``report.html``) is handled by
``agent_eval.persistence`` / ``write_dashboard``. This module adds the candidate
-vs-baseline gate (pass-rate, token/cost, runtime tie-breaker) plus deterministic
provenance checks.

Relationship to :class:`~nemo_evaluator_sdk.agent_eval.types.AgentEvalSummary`:
that summary reports the *mean score per metric output* over a run. The gate's
``pass_rate`` here is a different, intentional view — a per-task pass/fail count
against a reward threshold — so it is computed separately. Token/runtime/
provenance aggregation is delegated to
:class:`~nemo_evaluator_sdk.agent_eval.measurements.AttemptMeasurements` so the
measurement keys are read in exactly one place.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval.measurements import AttemptMeasurements
from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunResult, AgentEvalTaskResult

# Metric outputs, in priority order, that represent a task's pass/reward signal.
DEFAULT_REWARD_OUTPUTS: tuple[str, ...] = ("verifier_reward", "agent_phase_success")

# Provenance fields collapsed into a single run-level summary.
_PROVENANCE_FIELDS: tuple[str, ...] = (
    "commit_sha",
    "commit_short",
    "commit_dirty",
    "branch",
    "remote_url",
    "agentic_base_image_digest",
    "pinned",
    "pinned_to_commit",
    "pinned_image_tag",
)


@dataclass(frozen=True)
class GateThresholds:
    """Knobs controlling the candidate gate (defaults are the strict CI policy)."""

    min_pass_rate: float = 1.0
    require_token_metrics: bool = False
    max_pass_rate_drop: float = 0.0
    max_token_regression_pct: float = 0.0
    max_runtime_regression_pct: float = 0.0
    allow_cross_commit: bool = False


@dataclass
class GateCheck:
    name: str
    passed: bool
    details: str


@dataclass
class GateReport:
    gate_passed: bool
    summary: dict[str, Any]
    checks: list[GateCheck] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "gate_passed": self.gate_passed,
            "summary": self.summary,
            "checks": [asdict(check) for check in self.checks],
        }


def evaluate_gate(
    result: AgentEvalRunResult,
    *,
    thresholds: GateThresholds | None = None,
    baseline_summary: dict[str, Any] | None = None,
    reward_outputs: tuple[str, ...] = DEFAULT_REWARD_OUTPUTS,
) -> GateReport:
    """Summarize a run and apply gate checks, optionally against a baseline."""
    thresholds = thresholds or GateThresholds()
    summary = summarize_run(result, reward_outputs=reward_outputs)
    checks = run_gate_checks(summary, thresholds=thresholds, baseline_summary=baseline_summary)
    return GateReport(gate_passed=all(check.passed for check in checks), summary=summary, checks=checks)


def write_gate_report(report: GateReport, output_dir: str | Path, *, filename: str = "gate.json") -> Path:
    """Persist the gate report alongside the run bundle."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    gate_path = path / filename
    gate_path.write_text(json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return gate_path


def load_baseline_summary(path: str | Path) -> dict[str, Any]:
    """Load + normalize a baseline summary (raw summary or a prior gate.json)."""
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Baseline summary must be a JSON object: {source}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
    _validate_baseline_summary(summary, source)
    return summary


def summarize_run(
    result: AgentEvalRunResult,
    *,
    reward_outputs: tuple[str, ...] = DEFAULT_REWARD_OUTPUTS,
) -> dict[str, Any]:
    """Aggregate pass-rate, token, runtime, and provenance for one run.

    Token/runtime/provenance are read via :class:`AttemptMeasurements`; the
    reward used for pass-rate prefers a scored metric output (``reward_outputs``)
    and falls back to the attempt's recorded reward.
    """
    attempts_by_task = {attempt.task_id: attempt for attempt in result.attempts}
    reward_by_task = _rewards_by_task(result.results, reward_outputs)
    task_ids = sorted({task.id for task in result.tasks} | set(attempts_by_task))

    passed = 0
    token_sum = 0
    token_count = 0
    token_unavailable: list[str] = []
    runtime_sum = 0.0
    runtime_count = 0
    runtime_unavailable: list[str] = []
    provenance_inputs: list[dict[str, Any]] = []

    for task_id in task_ids:
        attempt = attempts_by_task.get(task_id)
        measurements = AttemptMeasurements.from_metadata(attempt.metadata if attempt is not None else {})

        reward_value = reward_by_task.get(task_id)
        if reward_value is None:
            reward_value = measurements.reward if measurements.reward is not None else 0.0
        if reward_value >= 1.0:
            passed += 1

        if measurements.total_tokens is not None:
            token_sum += measurements.total_tokens
            token_count += 1
        else:
            token_unavailable.append(task_id)

        if measurements.runtime_sec is not None:
            runtime_sum += measurements.runtime_sec
            runtime_count += 1
        else:
            runtime_unavailable.append(task_id)

        if measurements.provenance:
            provenance_inputs.append(measurements.provenance)

    total = len(task_ids)
    return {
        "run_id": result.run_id,
        "benchmark": result.benchmark,
        "total_tasks": total,
        "passed_tasks": passed,
        "pass_rate": (passed / total) if total else 0.0,
        "task_names": task_ids,
        "total_tokens_sum": token_sum if token_count else None,
        "avg_total_tokens": (token_sum / token_count) if token_count else None,
        "token_metrics_coverage": (token_count / total) if total else 0.0,
        "token_metrics_available_tasks": token_count,
        "token_metrics_unavailable_tasks": sorted(token_unavailable),
        "runtime_sec_sum": runtime_sum if runtime_count else None,
        "avg_runtime_sec": (runtime_sum / runtime_count) if runtime_count else None,
        "runtime_metrics_coverage": (runtime_count / total) if total else 0.0,
        "runtime_metrics_available_tasks": runtime_count,
        "runtime_metrics_unavailable_tasks": sorted(runtime_unavailable),
        "provenance": _aggregate_provenance(provenance_inputs),
    }


def run_gate_checks(
    summary: dict[str, Any],
    *,
    thresholds: GateThresholds,
    baseline_summary: dict[str, Any] | None = None,
) -> list[GateCheck]:
    """Apply absolute + relative (vs baseline) gate checks to a summary."""
    checks: list[GateCheck] = []
    total_tasks = int(summary["total_tasks"])
    pass_rate = float(summary["pass_rate"])
    provenance = summary.get("provenance") or {}

    checks.append(GateCheck("non_empty_result_set", total_tasks > 0, f"total_tasks={total_tasks}"))
    checks.append(
        GateCheck(
            "min_pass_rate",
            pass_rate >= thresholds.min_pass_rate,
            f"pass_rate={pass_rate:.3f}, min_pass_rate={thresholds.min_pass_rate:.3f}",
        )
    )
    checks.append(_commit_consistency_check(provenance))

    if thresholds.require_token_metrics:
        token_coverage = float(summary["token_metrics_coverage"])
        runtime_coverage = float(summary["runtime_metrics_coverage"])
        checks.append(
            GateCheck(
                "token_metrics_available_for_all_tasks",
                token_coverage == 1.0,
                f"token_metrics_coverage={token_coverage:.3f}",
            )
        )
        checks.append(
            GateCheck(
                "runtime_metrics_available_for_all_tasks",
                runtime_coverage == 1.0,
                f"runtime_metrics_coverage={runtime_coverage:.3f}",
            )
        )

    if baseline_summary is not None:
        checks.extend(_baseline_checks(summary, baseline_summary, thresholds))

    return checks


def _baseline_checks(
    summary: dict[str, Any],
    baseline_summary: dict[str, Any],
    thresholds: GateThresholds,
) -> list[GateCheck]:
    checks: list[GateCheck] = []
    pass_rate = float(summary["pass_rate"])
    total_tokens_sum = summary["total_tokens_sum"]
    runtime_sec_sum = summary["runtime_sec_sum"]
    provenance = summary.get("provenance") or {}

    # Regression checks only make sense when both runs measured the same tasks.
    baseline_tasks = baseline_summary.get("task_names")
    candidate_tasks = summary.get("task_names")
    task_sets_comparable = True
    if isinstance(baseline_tasks, list) and isinstance(candidate_tasks, list):
        comparable = sorted(baseline_tasks) == sorted(candidate_tasks)
        task_sets_comparable = comparable
        checks.append(
            GateCheck(
                "baseline_candidate_task_sets_match",
                comparable,
                (
                    f"both runs measured {len(candidate_tasks)} tasks"
                    if comparable
                    else f"baseline={sorted(baseline_tasks)} candidate={sorted(candidate_tasks)}; "
                    "regression checks short-circuited"
                ),
            )
        )
    else:
        checks.append(
            GateCheck(
                "baseline_candidate_task_sets_match",
                True,
                "task_names not present on baseline and/or candidate; skipping equality guard",
            )
        )

    checks.append(_cross_commit_check(provenance, baseline_summary, thresholds.allow_cross_commit))

    if not task_sets_comparable:
        return checks

    baseline_pass_rate = float(baseline_summary.get("pass_rate", 0.0))
    checks.append(
        GateCheck(
            "no_pass_rate_regression_vs_baseline",
            pass_rate >= baseline_pass_rate - thresholds.max_pass_rate_drop,
            f"pass_rate={pass_rate:.3f}, baseline={baseline_pass_rate:.3f}, max_drop={thresholds.max_pass_rate_drop:.3f}",
        )
    )

    baseline_tokens = baseline_summary.get("total_tokens_sum")
    if isinstance(total_tokens_sum, int) and isinstance(baseline_tokens, int):
        max_allowed = baseline_tokens * (1.0 + thresholds.max_token_regression_pct / 100.0)
        checks.append(
            GateCheck(
                "tokens_not_worse_than_baseline",
                total_tokens_sum <= max_allowed,
                f"total_tokens_sum={total_tokens_sum}, baseline={baseline_tokens}, "
                f"max_regression_pct={thresholds.max_token_regression_pct:.2f}",
            )
        )
    else:
        checks.append(
            GateCheck(
                "tokens_not_worse_than_baseline",
                False,
                "Missing token totals for candidate or baseline; cannot run deterministic token comparison.",
            )
        )

    # Runtime is only a tie-breaker when token totals match exactly.
    baseline_runtime = baseline_summary.get("runtime_sec_sum")
    tokens_tied = (
        isinstance(total_tokens_sum, int) and isinstance(baseline_tokens, int) and total_tokens_sum == baseline_tokens
    )
    if not tokens_tied:
        checks.append(
            GateCheck(
                "runtime_tie_breaker_not_worse_than_baseline",
                True,
                "Not applicable (token totals differ from baseline).",
            )
        )
    elif isinstance(runtime_sec_sum, int | float) and isinstance(baseline_runtime, int | float):
        max_allowed_runtime = float(baseline_runtime) * (1.0 + thresholds.max_runtime_regression_pct / 100.0)
        checks.append(
            GateCheck(
                "runtime_tie_breaker_not_worse_than_baseline",
                float(runtime_sec_sum) <= max_allowed_runtime,
                f"runtime_sec_sum={float(runtime_sec_sum):.3f}, baseline={float(baseline_runtime):.3f}, "
                f"max_regression_pct={thresholds.max_runtime_regression_pct:.2f}",
            )
        )
    else:
        checks.append(
            GateCheck(
                "runtime_tie_breaker_not_worse_than_baseline",
                False,
                "Token totals tied with baseline but runtime totals missing; cannot run tie-breaker.",
            )
        )

    return checks


def _commit_consistency_check(provenance: dict[str, Any]) -> GateCheck:
    commit_observed = provenance.get("commit_sha_observed")
    if isinstance(commit_observed, list) and len(commit_observed) > 1:
        return GateCheck(
            "commit_sha_consistent_within_run",
            False,
            f"Multiple commit_sha values observed across tasks: {commit_observed}. Re-run from a single commit.",
        )
    commit_sha = provenance.get("commit_sha")
    if commit_sha:
        return GateCheck(
            "commit_sha_consistent_within_run",
            True,
            f"commit={provenance.get('commit_short') or commit_sha[:12]}, branch={provenance.get('branch') or 'detached'}",
        )
    return GateCheck(
        "commit_sha_consistent_within_run",
        True,
        "provenance not recorded (legacy artifacts); skipping commit consistency check.",
    )


def _cross_commit_check(
    provenance: dict[str, Any],
    baseline_summary: dict[str, Any],
    allow_cross_commit: bool,
) -> GateCheck:
    baseline_commit = (baseline_summary.get("provenance") or {}).get("commit_sha")
    candidate_commit = provenance.get("commit_sha")
    if not (baseline_commit and candidate_commit):
        return GateCheck(
            "commit_sha_matches_baseline",
            True,
            "commit_sha not present on baseline and/or candidate; skipping cross-commit guard.",
        )
    commits_match = baseline_commit == candidate_commit
    if commits_match:
        detail = f"both runs at commit={baseline_commit[:12]}"
    elif allow_cross_commit:
        detail = (
            f"baseline={baseline_commit[:12]} != candidate={candidate_commit[:12]}; "
            "comparison allowed by allow_cross_commit (numbers may not be apples-to-apples)."
        )
    else:
        detail = (
            f"baseline={baseline_commit[:12]} != candidate={candidate_commit[:12]}. "
            "Re-run candidate at the baseline commit, or set allow_cross_commit."
        )
    return GateCheck("commit_sha_matches_baseline", commits_match or allow_cross_commit, detail)


def _rewards_by_task(results: list[AgentEvalTaskResult], reward_outputs: tuple[str, ...]) -> dict[str, float]:
    rewards: dict[str, float] = {}
    for task_result in results:
        for output_name in reward_outputs:
            value = _numeric_output(task_result, output_name)
            if value is not None:
                # Highest-priority output wins; don't overwrite with later metrics.
                rewards.setdefault(task_result.task_id, value)
                break
    return rewards


def _numeric_output(task_result: AgentEvalTaskResult, name: str) -> float | None:
    for output in task_result.outputs:
        if output.name == name:
            try:
                return float(output.value)
            except (TypeError, ValueError):
                return None
    return None


def _aggregate_provenance(provenances: list[dict[str, Any]]) -> dict[str, Any]:
    observed: dict[str, set[Any]] = {field_name: set() for field_name in _PROVENANCE_FIELDS}
    for prov in provenances:
        for field_name in _PROVENANCE_FIELDS:
            value = prov.get(field_name)
            if value is not None:
                observed[field_name].add(value)

    aggregated: dict[str, Any] = {"available": bool(provenances)}
    for field_name in _PROVENANCE_FIELDS:
        values = observed[field_name]
        if len(values) == 1:
            aggregated[field_name] = next(iter(values))
        else:
            aggregated[field_name] = None
            if len(values) > 1:
                aggregated[f"{field_name}_observed"] = sorted(map(str, values))
    return aggregated


def _validate_baseline_summary(summary: dict[str, Any], source: Path) -> None:
    missing = [key for key in ("pass_rate", "total_tokens_sum", "runtime_sec_sum") if key not in summary]
    if missing:
        raise ValueError(
            f"Baseline summary {source} is missing required key(s): {', '.join(missing)}. "
            "Expected a raw summary object or a gate.json with a `summary`."
        )
    if not isinstance(summary.get("pass_rate"), int | float):
        raise ValueError(f"Baseline summary {source} has invalid `pass_rate`; expected a number.")
