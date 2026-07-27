# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rank Insight-suite tasks for possible manual promotion into validation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    Task,
    TrialResult,
    local_path_from_uri,
)

_GENERIC_METRIC_NAMES = frozenset({"reward", "score"})
_MAX_REPEAT_SPREAD = 0.1
_MIN_DISCRIMINATION = 1e-9
_REPORT_SECTION_START = "<!-- insight-suite-promotion-suggestions:start -->"
_REPORT_SECTION_END = "<!-- insight-suite-promotion-suggestions:end -->"


@dataclass(frozen=True, slots=True)
class InsightPromotionSuggestion:
    """Evidence-backed recommendation to review one Insight-suite task."""

    task_id: str
    task_path: str
    metric_name: str
    discrimination: float
    completed_attempts: int
    total_attempts: int
    repeat_spread: float
    candidate_count: int
    diversity_score: float | None = None


@dataclass(frozen=True, slots=True)
class _TaskEvidence:
    suggestion: InsightPromotionSuggestion
    profile: dict[tuple[str, str], float]


def _completed_metric_values(
    trials: Sequence[TrialResult],
) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for trial in trials:
        if trial.status != "completed":
            continue
        for metric_name, metric in trial.metrics.items():
            values.setdefault(metric_name, []).append(float(metric.value))
    return values


def _task_evidence(task: Task, candidates: Sequence[Candidate]) -> _TaskEvidence | None:
    trials_by_candidate = {
        candidate.label: [trial for trial in candidate.insight_reward_details or () if trial.task_id == task.id]
        for candidate in candidates
    }
    values_by_candidate = {label: _completed_metric_values(trials) for label, trials in trials_by_candidate.items()}
    common_metrics = set.intersection(*(set(metric_values) for metric_values in values_by_candidate.values()))
    if not common_metrics:
        return None

    insight_metrics = common_metrics - _GENERIC_METRIC_NAMES
    selected_metrics = sorted(insight_metrics or common_metrics)
    total_attempts = sum(max(len(trials), 1) for trials in trials_by_candidate.values())
    completed_attempts = sum(
        1
        for trials in trials_by_candidate.values()
        for trial in trials
        if trial.status == "completed" and all(metric in trial.metrics for metric in selected_metrics)
    )
    if completed_attempts != total_attempts:
        return None

    profile: dict[tuple[str, str], float] = {}
    repeat_spread = 0.0
    metric_ranges: dict[str, float] = {}
    for metric_name in selected_metrics:
        candidate_means: list[float] = []
        for candidate_label in sorted(values_by_candidate):
            metric_values = values_by_candidate[candidate_label][metric_name]
            candidate_mean = sum(metric_values) / len(metric_values)
            profile[(candidate_label, metric_name)] = candidate_mean
            candidate_means.append(candidate_mean)
            repeat_spread = max(repeat_spread, max(metric_values) - min(metric_values))
        metric_ranges[metric_name] = max(candidate_means) - min(candidate_means)

    if repeat_spread > _MAX_REPEAT_SPREAD:
        return None
    metric_name, discrimination = max(
        metric_ranges.items(),
        key=lambda item: (item[1], item[0]),
    )
    if discrimination <= _MIN_DISCRIMINATION:
        return None

    return _TaskEvidence(
        suggestion=InsightPromotionSuggestion(
            task_id=task.id,
            task_path=_task_path(task),
            metric_name=metric_name,
            discrimination=discrimination,
            completed_attempts=completed_attempts,
            total_attempts=total_attempts,
            repeat_spread=repeat_spread,
            candidate_count=len(candidates),
        ),
        profile=profile,
    )


def _task_path(task: Task) -> str:
    if not task.uri:
        return "-"
    try:
        return str(local_path_from_uri(task.uri, context=f"Insight task {task.id!r}"))
    except ValueError:
        return task.uri


def _profile_distance(left: _TaskEvidence, right: _TaskEvidence) -> float:
    common_keys = set(left.profile) & set(right.profile)
    if not common_keys:
        return 1.0
    return sum(min(abs(left.profile[key] - right.profile[key]), 1.0) for key in common_keys) / len(common_keys)


def select_insight_promotion_suggestions(
    dataset: Dataset,
    candidates: Sequence[Candidate],
    *,
    limit: int = 3,
) -> list[InsightPromotionSuggestion]:
    """Select stable, discriminative tasks with distinct observed score profiles."""
    if limit <= 0:
        return []
    evaluated_candidates = [candidate for candidate in candidates if candidate.insight_reward_details is not None]
    if len(evaluated_candidates) < 2:
        return []

    remaining = [
        evidence
        for task in dataset.list_tasks()
        if (evidence := _task_evidence(task, evaluated_candidates)) is not None
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
            "Advisory only: these tasks were not copied into the validation dataset. "
            "Review them manually before changing the canonical validation set."
        ),
        "",
    ]
    if not suggestions:
        lines.append(
            "No task had complete, repeat-consistent results that discriminated between at least two candidates."
        )
        return "\n".join(lines)

    lines.extend(
        [
            "| Task | Path | Evidence |",
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
            f"{suggestion.metric_name} range {suggestion.discrimination:.2f} across "
            f"{suggestion.candidate_count} candidates; "
            f"{suggestion.completed_attempts}/{suggestion.total_attempts} attempts completed; "
            f"repeat spread {suggestion.repeat_spread:.2f}; {diversity}"
        )
        lines.append(
            f"| `{_markdown_cell(suggestion.task_id)}` | "
            f"`{_markdown_cell(suggestion.task_path)}` | {_markdown_cell(evidence)} |"
        )
    return "\n".join(lines)


def write_insight_promotion_section(
    report_path: Path,
    suggestions: Sequence[InsightPromotionSuggestion],
) -> None:
    """Append or replace the advisory promotion section in the final report."""
    report = report_path.read_text() if report_path.exists() else "# Optimization Report\n"
    rendered = render_insight_promotion_section(suggestions)
    section = f"{_REPORT_SECTION_START}\n{rendered}\n{_REPORT_SECTION_END}"
    if _REPORT_SECTION_START in report and _REPORT_SECTION_END in report:
        before, _, marked = report.partition(_REPORT_SECTION_START)
        _, _, after = marked.partition(_REPORT_SECTION_END)
        report = f"{before.rstrip()}\n\n{section}{after}"
    else:
        report = f"{report.rstrip()}\n\n{section}\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(f"{report.rstrip()}\n")
