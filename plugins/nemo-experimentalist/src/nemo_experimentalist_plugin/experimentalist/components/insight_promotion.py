# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rank Insight-suite tasks for possible manual promotion into validation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from nemo_eval_author_plugin.evaluator import (
    Dataset,
    EvaluationResult,
    Task,
    TrialResult,
)
from nemo_eval_author_plugin.evaluator.models import local_path_from_uri
from nemo_experimentalist_plugin.entities import Candidate

_GENERIC_METRIC_NAMES = frozenset({"reward", "score"})
_MAX_REPEAT_SPREAD = 0.1
_MIN_DISCRIMINATION = 1e-9
_REPORT_SECTION_START = "<!-- insight-suite-promotion-suggestions:start -->"
_REPORT_SECTION_END = "<!-- insight-suite-promotion-suggestions:end -->"
_COMPARISON_SECTION_START = "<!-- insight-suite-comparison:start -->"
_COMPARISON_SECTION_END = "<!-- insight-suite-comparison:end -->"


@dataclass(frozen=True, slots=True)
class InsightSuiteProvenance:
    """Runtime identities and local location for one finalized Insight suite."""

    identity: str
    scorer_identity: str
    suite_path: Path
    task_hashes: dict[str, dict[str, str]]


@dataclass(frozen=True, slots=True)
class InsightPromotionSuggestion:
    """Evidence-backed recommendation to review one Insight-suite task."""

    task_id: str
    task_path: str
    suite_identity: str
    task_content_hash: str
    verifier_hash: str
    metric_name: str
    discrimination: float
    baseline_score: float
    winner_score: float
    completed_attempts: int
    total_attempts: int
    repeat_spread: float
    candidate_count: int
    diversity_score: float | None = None


@dataclass(frozen=True, slots=True)
class _TaskEvidence:
    suggestion: InsightPromotionSuggestion
    profile: dict[tuple[str, str], float]


def insight_suite_provenance(dataset: Dataset) -> InsightSuiteProvenance:
    """Return validated content provenance carried by a finalized suite dataset."""
    identity = dataset.metadata.get("insight_suite_identity")
    scorer_identity = dataset.metadata.get("insight_suite_scorer_identity")
    raw_task_hashes = dataset.metadata.get("insight_suite_task_hashes")
    if not isinstance(identity, str) or not identity.startswith("sha256:"):
        raise ValueError("Finalized Insight suite is missing its content identity")
    if not isinstance(scorer_identity, str) or not scorer_identity.startswith("sha256:"):
        raise ValueError("Finalized Insight suite is missing its scorer identity")
    if dataset.source is None:
        raise ValueError("Finalized Insight suite is missing its local source path")
    suite_path = local_path_from_uri(dataset.source.uri, context="Finalized Insight suite").resolve()
    if not isinstance(raw_task_hashes, dict):
        raise ValueError("Finalized Insight suite is missing task and verifier hashes")
    task_hashes: dict[str, dict[str, str]] = {}
    for task_id, raw_hashes in raw_task_hashes.items():
        if not isinstance(task_id, str) or not isinstance(raw_hashes, dict):
            raise ValueError("Finalized Insight suite has invalid task hash provenance")
        content_hash = raw_hashes.get("content_hash")
        verifier_hash = raw_hashes.get("verifier_hash")
        if not isinstance(content_hash, str) or not isinstance(verifier_hash, str):
            raise ValueError(f"Finalized Insight task {task_id!r} has invalid content hashes")
        task_hashes[task_id] = {
            "content_hash": content_hash,
            "verifier_hash": verifier_hash,
        }
    return InsightSuiteProvenance(
        identity=identity,
        scorer_identity=scorer_identity,
        suite_path=suite_path,
        task_hashes=task_hashes,
    )


def _validated_metric_value(value: float | int, *, context: str) -> float:
    metric_value = float(value)
    if not math.isfinite(metric_value) or not 0.0 <= metric_value <= 1.0:
        raise ValueError(f"{context} must be finite and within [0, 1], got {value!r}")
    return metric_value


def validate_insight_evaluation_result(
    result: EvaluationResult,
    *,
    expected_metric_keys: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Validate metrics before they become adaptive analysis or promotion evidence."""
    aggregate_keys = set(result.aggregate_metrics)
    if not aggregate_keys:
        raise ValueError("Insight evaluation produced no aggregate metrics")
    if not aggregate_keys - _GENERIC_METRIC_NAMES:
        raise ValueError("Insight evaluation produced no Insight-specific metric")
    if expected_metric_keys is not None and aggregate_keys != set(expected_metric_keys):
        raise ValueError(
            "Insight evaluation aggregate metric keys are inconsistent: "
            f"expected {sorted(expected_metric_keys)}, got {sorted(aggregate_keys)}"
        )
    for metric_name, value in result.aggregate_metrics.items():
        _validated_metric_value(value, context=f"Insight aggregate metric {metric_name!r}")

    completed = [trial for trial in result.trials if trial.status == "completed"]
    if not completed:
        raise ValueError("Insight evaluation produced no completed trial evidence")
    for trial in completed:
        trial_keys = set(trial.metrics)
        if trial_keys != aggregate_keys:
            raise ValueError(
                f"Insight trial {trial.id!r} metric keys are inconsistent: "
                f"expected {sorted(aggregate_keys)}, got {sorted(trial_keys)}"
            )
        for metric_name, metric in trial.metrics.items():
            _validated_metric_value(
                metric.value,
                context=f"Insight trial {trial.id!r} metric {metric_name!r}",
            )
    return tuple(sorted(aggregate_keys))


def stamp_insight_evaluation_result(
    result: EvaluationResult,
    provenance: InsightSuiteProvenance,
) -> EvaluationResult:
    """Attach suite identity to aggregate and per-trial evidence."""
    suite_metadata = {
        "insight_suite_identity": provenance.identity,
        "insight_suite_scorer_identity": provenance.scorer_identity,
    }
    return result.model_copy(
        update={
            "metadata": {**result.metadata, **suite_metadata},
            "trials": [
                trial.model_copy(update={"metadata": {**trial.metadata, **suite_metadata}}) for trial in result.trials
            ],
        }
    )


def _task_metric_values(
    trials: Sequence[TrialResult],
    *,
    required_metrics: set[str],
) -> dict[str, list[float]] | None:
    if len(trials) < 2 or any(trial.status != "completed" for trial in trials):
        return None
    values: dict[str, list[float]] = {metric_name: [] for metric_name in required_metrics}
    for trial in trials:
        if set(trial.metrics) != required_metrics:
            return None
        for metric_name, metric in trial.metrics.items():
            try:
                value = _validated_metric_value(
                    metric.value,
                    context=f"Insight trial {trial.id!r} metric {metric_name!r}",
                )
            except ValueError:
                return None
            values[metric_name].append(value)
    return values


def _task_evidence(
    task: Task,
    candidates: Sequence[Candidate],
    *,
    baseline: Candidate,
    winner: Candidate,
    provenance: InsightSuiteProvenance,
) -> _TaskEvidence | None:
    suite_candidates = [
        candidate for candidate in candidates if candidate.insight_suite_identity == provenance.identity
    ]
    metric_key_sets = {tuple(sorted(candidate.insight_metric_keys or ())) for candidate in suite_candidates}
    if len(metric_key_sets) != 1:
        return None
    required_metrics = set(next(iter(metric_key_sets), ()))
    insight_metrics = required_metrics - _GENERIC_METRIC_NAMES
    if not insight_metrics:
        return None

    trials_by_candidate = {
        candidate.label: [trial for trial in candidate.insight_reward_details or () if trial.task_id == task.id]
        for candidate in suite_candidates
    }
    values_by_candidate: dict[str, dict[str, list[float]]] = {}
    for label, trials in trials_by_candidate.items():
        values = _task_metric_values(trials, required_metrics=required_metrics)
        if values is None:
            return None
        values_by_candidate[label] = values

    if baseline.label not in values_by_candidate or winner.label not in values_by_candidate:
        return None
    total_attempts = sum(len(trials) for trials in trials_by_candidate.values())
    if not total_attempts:
        return None

    profile: dict[tuple[str, str], float] = {}
    repeat_spread = 0.0
    metric_improvements: dict[str, tuple[float, float, float]] = {}
    for metric_name in sorted(insight_metrics):
        candidate_means: dict[str, float] = {}
        for candidate_label in sorted(values_by_candidate):
            metric_values = values_by_candidate[candidate_label][metric_name]
            candidate_mean = sum(metric_values) / len(metric_values)
            profile[(candidate_label, metric_name)] = candidate_mean
            candidate_means[candidate_label] = candidate_mean
            repeat_spread = max(repeat_spread, max(metric_values) - min(metric_values))
        baseline_score = candidate_means[baseline.label]
        winner_score = candidate_means[winner.label]
        metric_improvements[metric_name] = (
            winner_score - baseline_score,
            baseline_score,
            winner_score,
        )

    if repeat_spread > _MAX_REPEAT_SPREAD:
        return None
    metric_name, (discrimination, baseline_score, winner_score) = max(
        metric_improvements.items(),
        key=lambda item: (item[1][0], item[0]),
    )
    if baseline_score >= 1.0 or discrimination <= _MIN_DISCRIMINATION:
        return None
    hashes = provenance.task_hashes.get(task.id)
    if hashes is None or not task.uri:
        return None
    try:
        task_path = str(local_path_from_uri(task.uri, context=f"Insight task {task.id!r}").resolve())
    except ValueError:
        return None

    return _TaskEvidence(
        suggestion=InsightPromotionSuggestion(
            task_id=task.id,
            task_path=task_path,
            suite_identity=provenance.identity,
            task_content_hash=hashes["content_hash"],
            verifier_hash=hashes["verifier_hash"],
            metric_name=metric_name,
            discrimination=discrimination,
            baseline_score=baseline_score,
            winner_score=winner_score,
            completed_attempts=total_attempts,
            total_attempts=total_attempts,
            repeat_spread=repeat_spread,
            candidate_count=len(suite_candidates),
        ),
        profile=profile,
    )


def _profile_distance(left: _TaskEvidence, right: _TaskEvidence) -> float:
    common_keys = set(left.profile) & set(right.profile)
    if not common_keys:
        return 1.0
    return sum(min(abs(left.profile[key] - right.profile[key]), 1.0) for key in common_keys) / len(common_keys)


def select_insight_promotion_suggestions(
    dataset: Dataset,
    candidates: Sequence[Candidate],
    *,
    winner: Candidate | None = None,
    limit: int = 3,
) -> list[InsightPromotionSuggestion]:
    """Select repeated, complete baseline-to-winner improvements for manual review."""
    if limit <= 0 or winner is None:
        return []
    provenance = insight_suite_provenance(dataset)
    evaluated_candidates = [
        candidate
        for candidate in candidates
        if candidate.insight_reward_details is not None and candidate.insight_suite_identity == provenance.identity
    ]
    if len(evaluated_candidates) < 2:
        return []
    baseline = next((candidate for candidate in evaluated_candidates if candidate.round == 0), None)
    if baseline is None or winner not in evaluated_candidates:
        return []

    remaining = [
        evidence
        for task in dataset.list_tasks()
        if (
            evidence := _task_evidence(
                task,
                evaluated_candidates,
                baseline=baseline,
                winner=winner,
                provenance=provenance,
            )
        )
        is not None
    ]
    remaining.sort(
        key=lambda evidence: (
            -evidence.suggestion.discrimination,
            evidence.suggestion.repeat_spread,
            evidence.suggestion.task_id,
        )
    )
    if not remaining:
        return []

    selected = [remaining.pop(0)]
    while remaining and len(selected) < limit:
        ranked: list[tuple[float, _TaskEvidence]] = [
            (
                min(_profile_distance(evidence, chosen) for chosen in selected),
                evidence,
            )
            for evidence in remaining
        ]
        diversity_score, next_evidence = max(
            ranked,
            key=lambda item: (
                item[0],
                item[1].suggestion.discrimination,
                -item[1].suggestion.repeat_spread,
                item[1].suggestion.task_id,
            ),
        )
        if diversity_score <= _MIN_DISCRIMINATION:
            break
        selected.append(
            replace(
                next_evidence,
                suggestion=replace(
                    next_evidence.suggestion,
                    diversity_score=diversity_score,
                ),
            )
        )
        remaining.remove(next_evidence)

    return [evidence.suggestion for evidence in selected]


def _markdown_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")


def render_insight_promotion_section(
    suggestions: Sequence[InsightPromotionSuggestion],
) -> str:
    """Render an advisory-only final-report section."""
    lines = [
        "## Insight Suite Promotion Suggestions",
        "",
        (
            "Advisory adaptive/development evidence only, not independent validation evidence. "
            "These tasks were not copied into the validation dataset; review them manually before "
            "changing the canonical validation set."
        ),
        "",
    ]
    if not suggestions:
        lines.append(
            "No task had complete repeated evidence reproducing a baseline failure and showing a winner improvement."
        )
        return "\n".join(lines)

    lines.extend(
        [
            "| Task | Local task path | Evidence |",
            "| --- | --- | --- |",
        ]
    )
    for suggestion in suggestions:
        diversity = (
            "highest discriminative signal"
            if suggestion.diversity_score is None
            else f"score-profile distance {suggestion.diversity_score:.2f}"
        )
        evidence = (
            f"{suggestion.metric_name} baseline {suggestion.baseline_score:.2f} → "
            f"winner {suggestion.winner_score:.2f} ({suggestion.discrimination:+.2f}) across "
            f"{suggestion.candidate_count} candidates; "
            f"{suggestion.completed_attempts}/{suggestion.total_attempts} attempts completed; "
            f"repeat spread {suggestion.repeat_spread:.2f}; "
            f"suite {suggestion.suite_identity}; task {suggestion.task_content_hash}; "
            f"verifier {suggestion.verifier_hash}; {diversity}"
        )
        lines.append(
            f"| `{_markdown_cell(suggestion.task_id)}` | "
            f"`{_markdown_cell(suggestion.task_path)}` | {_markdown_cell(evidence)} |"
        )
    return "\n".join(lines)


def _write_marked_section(
    report_path: Path,
    *,
    rendered: str,
    start_marker: str,
    end_marker: str,
) -> None:
    report = report_path.read_text() if report_path.exists() else "# Optimization Report\n"
    section = f"{start_marker}\n{rendered}\n{end_marker}"
    if start_marker in report and end_marker in report:
        before, _, marked = report.partition(start_marker)
        _, _, after = marked.partition(end_marker)
        report = f"{before.rstrip()}\n\n{section}{after}"
    else:
        report = f"{report.rstrip()}\n\n{section}\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(f"{report.rstrip()}\n")


def write_insight_promotion_section(
    report_path: Path,
    suggestions: Sequence[InsightPromotionSuggestion],
) -> None:
    """Append or replace the advisory promotion section in the final report."""
    _write_marked_section(
        report_path,
        rendered=render_insight_promotion_section(suggestions),
        start_marker=_REPORT_SECTION_START,
        end_marker=_REPORT_SECTION_END,
    )


def render_insight_comparison_section(
    baseline: Candidate,
    winner: Candidate,
    provenance: InsightSuiteProvenance,
) -> str:
    """Render the deterministic baseline-versus-winner Insight comparison."""
    for candidate in (baseline, winner):
        if candidate.insight_suite_identity != provenance.identity:
            raise ValueError(
                f"Candidate {candidate.label!r} Insight evidence does not match finalized suite {provenance.identity}"
            )
    baseline_reward = baseline.insight_reward or {}
    winner_reward = winner.insight_reward or {}
    metric_names = sorted(set(baseline_reward) | set(winner_reward))
    lines = [
        "## Deterministic Insight Suite Comparison",
        "",
        (
            "Adaptive/development evidence only; canonical validation remains the direct "
            "Pareto and winner-selection criterion."
        ),
        "",
        (f"Suite: `{provenance.suite_path}` (suite `{provenance.identity}`; scorer `{provenance.scorer_identity}`)"),
        "",
        "| Metric | Baseline | Winner | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for metric_name in metric_names:
        baseline_value = baseline_reward.get(metric_name)
        winner_value = winner_reward.get(metric_name)
        if baseline_value is None or winner_value is None:
            baseline_text = "—" if baseline_value is None else f"{baseline_value:.3f}"
            winner_text = "—" if winner_value is None else f"{winner_value:.3f}"
            delta_text = "—"
        else:
            baseline_text = f"{baseline_value:.3f}"
            winner_text = f"{winner_value:.3f}"
            delta_text = f"{winner_value - baseline_value:+.3f}"
        lines.append(f"| `{_markdown_cell(metric_name)}` | {baseline_text} | {winner_text} | {delta_text} |")
    return "\n".join(lines)


def write_insight_comparison_section(
    report_path: Path,
    baseline: Candidate,
    winner: Candidate,
    provenance: InsightSuiteProvenance,
) -> None:
    """Append or replace the deterministic baseline-versus-winner section."""
    _write_marked_section(
        report_path,
        rendered=render_insight_comparison_section(baseline, winner, provenance),
        start_marker=_COMPARISON_SECTION_START,
        end_marker=_COMPARISON_SECTION_END,
    )
