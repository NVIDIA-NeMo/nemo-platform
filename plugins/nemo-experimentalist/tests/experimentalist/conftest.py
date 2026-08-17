# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for the evaluator test modules.

Test directories carry no ``__init__.py`` in this repo, so helpers are shared as
fixtures rather than imports.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest


def _comparable_trials(trials: Sequence[Any], *, include_id: bool = False) -> list[dict[str, Any]]:
    projected = []
    for trial in trials:
        entry: dict[str, Any] = {
            "task_id": trial.task_id,
            "attempt": trial.attempt,
            "status": trial.status,
            "error": trial.error,
            "metrics": {name: metric.value for name, metric in trial.metrics.items()},
            "has_trace": trial.trace is not None,
            "resource_kinds": sorted({key.split(":")[0] for key in trial.resources}),
        }
        if include_id:
            entry["id"] = trial.id
        projected.append(entry)
    return sorted(projected, key=lambda entry: str(entry["task_id"]))


@pytest.fixture
def comparable_trials() -> Callable[..., list[dict[str, Any]]]:
    """Project trials down to the fields the optimizer loop actually consumes.

    Both A/B parity tests compare evaluator output through this one projection, so
    they cannot drift on what "equivalent trials" means — which is the single thing
    those tests exist to pin down. ``resources`` is compared by key *kind* (the part
    before ``:``) rather than by full key, because artifact keys embed per-trial file
    names that legitimately differ between runs.

    Pass ``include_id=True`` to also compare trial ids. That is only meaningful when
    both sides read the same job directory — Harbor mints a random suffix per run.
    """
    return _comparable_trials
