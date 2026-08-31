# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical Harbor TrialResult dumps for native vs SDK parity tests.

Both Harbor-backed evaluators parse a finished job through ``trials_from_job_dir``.
Raw ``list[TrialResult]`` equality fails across runs: ``id`` is Harbor's random
trial name, ``attempt`` is inferred from an all-digit ShortUUID suffix, and every
``ResourceRef.uri`` is a ``file://`` path into a different experiment directory.
This helper rewrites those fields so the adapter output can be compared as JSON.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from nemo_experimentalist_plugin.entities import (
    DataValue,
    MetricResult,
    ResourceRef,
    TrialResult,
    local_path_from_uri,
)

_JOB_DIR_TOKEN = "$JOB_DIR"


def canonical_trials_json(trials: Sequence[TrialResult]) -> str:
    """Return a sorted, URI-canonical JSON dump of Harbor adapter trials.

    Args:
        trials: ``trials_from_job_dir`` results (or the evaluator's ``.trials``).

    Returns:
        Compact JSON array, one object per trial, ordered by ``task_id``.

    Raises:
        ValueError: If two trials share a ``task_id``, or a trial has no usable
            ``resources["trial_dir"]`` URI.
    """
    dumped: list[dict[str, Any]] = []
    seen: dict[str, None] = {}
    for trial in sorted(trials, key=lambda item: item.task_id):
        if trial.task_id in seen:
            raise ValueError(f"Duplicate canonical trial task_id {trial.task_id!r}")
        seen[trial.task_id] = None
        dumped.append(_canonical_trial(trial))
    return json.dumps(dumped, sort_keys=True, separators=(",", ":"))


def assert_comparable_trials_dump(left: Sequence[TrialResult], right: Sequence[TrialResult]) -> None:
    """Assert two Harbor adapter trial lists canonicalize to the same JSON.

    Args:
        left: Trials from one orchestrator.
        right: Trials from the other orchestrator.

    Raises:
        ValueError: If either side cannot be canonicalized.
        AssertionError: If the dumps differ. The message names the first
            differing ``task_id`` (or the side that has extra trials).
    """
    left_json = canonical_trials_json(left)
    right_json = canonical_trials_json(right)
    if left_json == right_json:
        return

    left_by_id = {entry["task_id"]: entry for entry in json.loads(left_json)}
    right_by_id = {entry["task_id"]: entry for entry in json.loads(right_json)}
    left_only = sorted(set(left_by_id) - set(right_by_id))
    right_only = sorted(set(right_by_id) - set(left_by_id))
    if left_only:
        raise AssertionError(f"Canonical trial dump missing on right: {left_only[0]}")
    if right_only:
        raise AssertionError(f"Canonical trial dump missing on left: {right_only[0]}")
    for task_id in sorted(left_by_id):
        if left_by_id[task_id] != right_by_id[task_id]:
            raise AssertionError(f"Canonical trial dump differs for task_id {task_id}")
    raise AssertionError("Canonical trial dumps differ")


def _canonical_trial(trial: TrialResult) -> dict[str, Any]:
    trial_dir = _trial_dir_path(trial)
    rewrite = _uri_rewriter(trial_dir, trial.task_id)
    canonical = trial.model_copy(
        update={
            "id": trial.task_id,
            "attempt": None,
            "trace": _rewrite_ref(trial.trace, rewrite),
            "outputs": _rewrite_outputs(trial.outputs, rewrite),
            "resources": {key: _rewrite_ref(ref, rewrite) for key, ref in trial.resources.items()},
            "metrics": {name: _rewrite_metric(metric, rewrite) for name, metric in trial.metrics.items()},
        }
    )
    return canonical.model_dump(mode="json")


def _trial_dir_path(trial: TrialResult) -> Path:
    trial_dir_ref = trial.resources.get("trial_dir")
    if trial_dir_ref is None:
        raise ValueError(f"Trial {trial.task_id!r} is missing resources['trial_dir']")
    try:
        return local_path_from_uri(trial_dir_ref.uri, context="Harbor trial_dir").resolve()
    except ValueError as exc:
        raise ValueError(f"Trial {trial.task_id!r} has an unparseable trial_dir URI: {trial_dir_ref.uri}") from exc


def _uri_rewriter(trial_dir: Path, task_id: str) -> Callable[[str], str]:
    prefix = f"{_JOB_DIR_TOKEN}/{task_id}"

    def rewrite(uri: str) -> str:
        try:
            path = local_path_from_uri(uri, context="Harbor resource").resolve()
        except ValueError:
            return uri
        try:
            relative = path.relative_to(trial_dir)
        except ValueError:
            return uri
        relative_posix = relative.as_posix()
        if relative_posix == ".":
            return prefix
        return f"{prefix}/{relative_posix}"

    return rewrite


def _rewrite_ref(ref: ResourceRef | None, rewrite: Callable[[str], str]) -> ResourceRef | None:
    if ref is None:
        return None
    return ref.model_copy(update={"uri": rewrite(ref.uri)})


def _rewrite_outputs(
    outputs: Mapping[str, DataValue | ResourceRef],
    rewrite: Callable[[str], str],
) -> dict[str, DataValue | ResourceRef]:
    rewritten: dict[str, DataValue | ResourceRef] = {}
    for key, value in outputs.items():
        rewritten[key] = _rewrite_ref(value, rewrite) if isinstance(value, ResourceRef) else value
    return rewritten


def _rewrite_metric(metric: MetricResult, rewrite: Callable[[str], str]) -> MetricResult:
    spec = metric.spec
    if spec is None or spec.ref is None:
        return metric
    return metric.model_copy(update={"spec": spec.model_copy(update={"ref": _rewrite_ref(spec.ref, rewrite)})})
