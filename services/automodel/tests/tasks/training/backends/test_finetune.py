# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Automodel training entry point's metric naming.

The shared callback's rule is that the backend passes its framework's own metric
name and the phase supplies the prefix. Automodel is the one backend whose
framework already prefixes some of its validation metrics, so it has to undo
that first -- otherwise the prefix arrives twice.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from types import ModuleType
from unittest.mock import MagicMock

import pytest

#: The leaf modules finetune.py imports from. nemo_automodel exists only inside
#: the training image, so the module cannot be imported in a plain checkout.
#: Only the leaves are needed: `from a.b.c import D` consults sys.modules for
#: `a.b.c` before it ever reaches for the parents.
_STUBBED_MODULES = (
    "nemo_automodel.components.checkpoint.checkpointing",
    "nemo_automodel.components.config._arg_parser",
    "nemo_automodel.components.training.step_scheduler",
    "nemo_automodel.recipes.llm.kd",
    "nemo_automodel.recipes.llm.train_ft",
    "nemo_automodel.recipes.retrieval.train_bi_encoder",
)
_FINETUNE = "nmp.automodel.tasks.training.backends.finetune"


@pytest.fixture
def finetune(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import finetune.py under throwaway stubs.

    The stubs go in via monkeypatch rather than a bare ``sys.modules``
    assignment so they are torn down with the test: a module-scope stub outlives
    the file that installed it and leaks into whatever else shares the xdist
    worker. finetune itself is popped for the same reason -- left behind, it is
    a cached module holding references to mocks.
    """
    for name in _STUBBED_MODULES:
        monkeypatch.setitem(sys.modules, name, MagicMock())
    monkeypatch.delitem(sys.modules, _FINETUNE, raising=False)
    yield importlib.import_module(_FINETUNE)
    sys.modules.pop(_FINETUNE, None)


def test_the_recipes_own_val_prefix_comes_off(finetune: ModuleType) -> None:
    """Otherwise the phase prefix arrives twice: `val_loss` as `val_val_loss`."""
    assert finetune.strip_val_prefix({"val_loss": 0.5}) == {"loss": 0.5}


def test_every_prefixed_name_is_stripped_not_just_the_loss(finetune: ModuleType) -> None:
    """train_bi_encoder reports val_acc1 and val_mrr alongside val_loss.

    Special-casing `val_loss` fixes the one curve Studio charts and leaves the
    rest as `val_val_acc1` / `val_val_mrr`.
    """
    stripped = finetune.strip_val_prefix({"val_loss": 0.5, "val_acc1": 0.8, "val_mrr": 0.7})

    assert stripped == {"loss": 0.5, "acc1": 0.8, "mrr": 0.7}


def test_an_unprefixed_name_is_left_alone(finetune: ModuleType) -> None:
    """The recipes are inconsistent: train_ft pairs `val_loss` with a bare `lr`."""
    stripped = finetune.strip_val_prefix({"val_loss": 0.5, "lr": 5e-06, "num_label_tokens": 128, "mem": 4.2})

    assert stripped == {"loss": 0.5, "lr": 5e-06, "num_label_tokens": 128, "mem": 4.2}


def test_only_a_leading_occurrence_is_removed(finetune: ModuleType) -> None:
    """`removeprefix`, not a replace: an interior `val_` is part of the name."""
    assert finetune.strip_val_prefix({"interval_val_x": 1.0}) == {"interval_val_x": 1.0}


def test_an_empty_metric_dict_survives(finetune: ModuleType) -> None:
    assert finetune.strip_val_prefix({}) == {}
