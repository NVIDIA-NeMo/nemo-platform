# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixture wrappers around the doubles in ``doubles.py``."""

from pathlib import Path

import pytest
from doubles import FakeBackend, FakeEvaluator, make_context
from nemo_experimentalist_plugin.experimentalist.context import ExperimentContext


@pytest.fixture
def fake_backend() -> FakeBackend:
    """An in-memory backend that records every entity it is handed."""
    return FakeBackend()


@pytest.fixture
def fake_evaluator() -> FakeEvaluator:
    """An evaluator that scores everything 0.5 and records the options each run got."""
    return FakeEvaluator()


@pytest.fixture
def experiment_context(tmp_path: Path, fake_backend: FakeBackend, fake_evaluator: FakeEvaluator) -> ExperimentContext:
    """A context over ``tmp_path`` wired to the fake backend and evaluator."""
    return make_context(root=tmp_path, backend=fake_backend, evaluator=fake_evaluator)
