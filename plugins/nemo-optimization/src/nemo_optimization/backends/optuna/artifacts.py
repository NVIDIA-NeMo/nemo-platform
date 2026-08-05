# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NAT-compatible optimizer artifact writers.

Ported from https://github.com/NVIDIA/NeMo-Agent-Toolkit/blob/main/packages/nvidia_nat_config_optimizer/src/nat/plugins/config_optimizer/parameters/optimizer.py
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import optuna
from optuna.study import StudyDirection

logger = logging.getLogger(__name__)


def write_trials_dataframe(
    *,
    study: optuna.Study,
    metric_names: Sequence[str],
    output_dir: Path,
) -> Path:
    """Write ``trials_dataframe_params.csv`` with NAT-compatible core columns."""
    path = output_dir / "trials_dataframe_params.csv"
    pareto_numbers = _pareto_trial_numbers(study)
    rows = [_trial_row(trial, metric_names, pareto_numbers) for trial in study.trials]
    columns = _ordered_columns(rows, metric_names)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def maybe_write_pareto_plots(
    *,
    study: optuna.Study,
    metric_names: Sequence[str],
    directions: Sequence[StudyDirection],
    output_dir: Path,
) -> list[Path]:
    """Write Pareto plots; return written paths."""
    if len(metric_names) < 2:
        return []

    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    values = _trial_values(study.trials, len(metric_names))
    pareto_numbers = _pareto_trial_numbers(study)
    pareto_indexes = [index for index, trial in enumerate(study.trials) if trial.number in pareto_numbers]

    if len(metric_names) == 2:
        path = plots_dir / "pareto_front_2d.png"
        _plot_2d(plt, values, pareto_indexes, metric_names, directions, path)
        written.append(path)

    parallel_path = plots_dir / "pareto_parallel_coordinates.png"
    _plot_parallel(plt, values, pareto_indexes, metric_names, directions, parallel_path)
    written.append(parallel_path)

    pairwise_path = plots_dir / "pareto_pairwise_matrix.png"
    _plot_pairwise(plt, values, pareto_indexes, metric_names, pairwise_path)
    written.append(pairwise_path)
    return written


def _trial_row(
    trial: optuna.trial.FrozenTrial,
    metric_names: Sequence[str],
    pareto_numbers: set[int],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "number": trial.number,
        "state": trial.state.name,
        "datetime_start": _datetime_to_str(trial.datetime_start),
        "datetime_complete": _datetime_to_str(trial.datetime_complete),
        "duration": str(trial.duration) if trial.duration is not None else "",
        "rep_scores": json.dumps(trial.user_attrs.get("rep_scores")),
        "pareto_optimal": trial.number in pareto_numbers,
    }
    values = list(trial.values or ([] if trial.value is None else [trial.value]))
    for index, metric_name in enumerate(metric_names):
        row[f"values_{metric_name}"] = values[index] if index < len(values) else ""
    for name, value in sorted(trial.params.items()):
        row[f"params_{name}"] = value
    return row


def _ordered_columns(rows: list[dict[str, Any]], metric_names: Sequence[str]) -> list[str]:
    fixed = ["number", "state", "datetime_start", "datetime_complete", "duration"]
    value_cols = [f"values_{name}" for name in metric_names]
    param_cols = sorted({key for row in rows for key in row if key.startswith("params_")})
    tail = ["rep_scores", "pareto_optimal"]
    return [*fixed, *value_cols, *param_cols, *tail]


def _pareto_trial_numbers(study: optuna.Study) -> set[int]:
    completed = [trial for trial in study.trials if trial.state == optuna.trial.TrialState.COMPLETE]
    if not completed:
        return set()
    if len(study.directions) == 1:
        return {study.best_trial.number}
    return {trial.number for trial in study.best_trials}


def _datetime_to_str(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _trial_values(trials: Sequence[optuna.trial.FrozenTrial], n_metrics: int) -> list[list[float]]:
    values: list[list[float]] = []
    for trial in trials:
        trial_values = list(trial.values or ([] if trial.value is None else [trial.value]))
        if len(trial_values) == n_metrics:
            values.append([float(value) for value in trial_values])
    return values


def _plot_2d(plt: Any, values: list[list[float]], pareto_indexes: list[int], metric_names: Sequence[str], directions: Sequence[StudyDirection], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 8))
    xs = [value[0] for value in values]
    ys = [value[1] for value in values]
    ax.scatter(xs, ys, alpha=0.6, s=50, c="lightblue", edgecolors="navy", linewidths=0.5, label=f"All Trials (n={len(values)})")
    if pareto_indexes:
        px = [values[index][0] for index in pareto_indexes if index < len(values)]
        py = [values[index][1] for index in pareto_indexes if index < len(values)]
        ax.scatter(px, py, alpha=0.9, s=100, c="red", edgecolors="darkred", linewidths=1.5, marker="*", label=f"Pareto Optimal (n={len(px)})")
    ax.set_xlabel(f"{metric_names[0]} {'↑' if directions[0] == StudyDirection.MAXIMIZE else '↓'}")
    ax.set_ylabel(f"{metric_names[1]} {'↑' if directions[1] == StudyDirection.MAXIMIZE else '↓'}")
    ax.set_title("Parameter Optimization: Pareto Front")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_parallel(plt: Any, values: list[list[float]], pareto_indexes: list[int], metric_names: Sequence[str], directions: Sequence[StudyDirection], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 8))
    normalized = _normalized_columns(values, directions)
    x_positions = list(range(len(metric_names)))
    for index, row in enumerate(normalized):
        color = "red" if index in pareto_indexes else "blue"
        alpha = 0.8 if index in pareto_indexes else 0.15
        linewidth = 3 if index in pareto_indexes else 1
        ax.plot(x_positions, row, color=color, alpha=alpha, linewidth=linewidth)
    ax.set_xticks(x_positions)
    ax.set_xticklabels([f"{name}\n({direction.name.lower()})" for name, direction in zip(metric_names, directions, strict=True)])
    ax.set_ylabel("Normalized Performance (Higher Is Better)")
    ax.set_title("Parameter Optimization: Parallel Coordinates")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_pairwise(plt: Any, values: list[list[float]], pareto_indexes: list[int], metric_names: Sequence[str], path: Path) -> None:
    n_metrics = len(metric_names)
    fig, axes = plt.subplots(n_metrics, n_metrics, figsize=(4 * n_metrics, 4 * n_metrics))
    if n_metrics == 1:
        axes = [[axes]]
    for row_index in range(n_metrics):
        for col_index in range(n_metrics):
            ax = axes[row_index][col_index] if n_metrics > 1 else axes[0][0]
            if row_index == col_index:
                ax.hist([value[col_index] for value in values], bins=min(10, max(1, len(values))))
            else:
                xs = [value[col_index] for value in values]
                ys = [value[row_index] for value in values]
                ax.scatter(xs, ys, alpha=0.4, c="lightblue", s=25)
                if pareto_indexes:
                    ax.scatter(
                        [values[index][col_index] for index in pareto_indexes if index < len(values)],
                        [values[index][row_index] for index in pareto_indexes if index < len(values)],
                        c="red",
                        s=50,
                        marker="*",
                    )
            if row_index == n_metrics - 1:
                ax.set_xlabel(metric_names[col_index])
            if col_index == 0:
                ax.set_ylabel(metric_names[row_index])
    fig.suptitle("Parameter Optimization: Pairwise Matrix")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _normalized_columns(values: list[list[float]], directions: Sequence[StudyDirection]) -> list[list[float]]:
    if not values:
        return []
    columns = list(zip(*values, strict=True))
    normalized_columns: list[list[float]] = []
    for column, direction in zip(columns, directions, strict=True):
        min_value = min(column)
        max_value = max(column)
        if max_value == min_value:
            normalized = [0.5 for _ in column]
        elif direction == StudyDirection.MINIMIZE:
            normalized = [1 - ((value - min_value) / (max_value - min_value)) for value in column]
        else:
            normalized = [(value - min_value) / (max_value - min_value) for value in column]
        normalized_columns.append(normalized)
    return [list(row) for row in zip(*normalized_columns, strict=True)]
