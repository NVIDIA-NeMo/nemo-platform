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
import logging
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


def test_a_collision_keeps_the_prefixed_value(finetune: ModuleType) -> None:
    """Stripping can map two names onto one, and the wrong winner is undetectable.

    No recipe reports both today, but the loser vanishes silently and the
    validation curve then charts whatever else was in the dict. The prefixed name
    wins, being the one the recipe marked as validation.
    """
    assert finetune.strip_val_prefix({"val_loss": 0.5, "loss": 0.7}) == {"loss": 0.5}
    assert finetune.strip_val_prefix({"loss": 0.7, "val_loss": 0.5}) == {"loss": 0.5}


def test_a_collision_is_logged(finetune: ModuleType, caplog: pytest.LogCaptureFixture) -> None:
    """Silently dropping a metric is how this would go unnoticed for a release."""
    with caplog.at_level(logging.WARNING):
        finetune.strip_val_prefix({"val_loss": 0.5, "loss": 0.7})

    assert "val_loss" in caplog.text


# --------------------------------------------------------------------------- #
# The reporting budget, read back off the compiled recipe config
# --------------------------------------------------------------------------- #


class _Recipe:
    """A recipe carrying only the config attribute the resolver reads."""

    def __init__(self, cfg: object) -> None:
        self.cfg = cfg


def test_the_compiled_reporting_budget_is_used(finetune: ModuleType) -> None:
    """The `_progress_reporting` block config.py writes is the whole channel."""
    recipe = _Recipe({"_progress_reporting": {"max_points": 25}})

    assert finetune._resolve_max_points(recipe) == 25


@pytest.mark.parametrize(
    "cfg",
    [
        {},  # a config compiled before the knob existed
        {"_progress_reporting": {}},  # the block, without the field
        {"_progress_reporting": None},
        {"_progress_reporting": {"max_points": None}},
        {"_progress_reporting": {"max_points": 0}},  # would make an empty curve
        {"_progress_reporting": {"max_points": -5}},
        {"_progress_reporting": {"max_points": "many"}},
        {"_progress_reporting": {"max_points": True}},  # bool is an int subclass
        {"_progress_reporting": "not a block"},
        None,  # no cfg at all
    ],
)
def test_an_unusable_budget_falls_back_rather_than_failing(finetune: ModuleType, cfg: object) -> None:
    """The recipe config is also loadable from a hand-written YAML.

    A run whose config predates this block, or spells it wrong, should report at
    the shared default rather than fail to start over a reporting knob. This runs
    in the wrapper's constructor, outside any try, so raising here kills training.
    """
    assert finetune._resolve_max_points(_Recipe(cfg)) == finetune.DEFAULT_MAX_POINTS


def test_the_compiled_curve_list_is_used(finetune: ModuleType) -> None:
    recipe = _Recipe({"_progress_reporting": {"curves": ["loss", "lr"]}})

    assert finetune._resolve_curves(recipe) == ["loss", "lr"]


def test_an_empty_curve_list_is_kept_rather_than_read_as_absent(finetune: ModuleType) -> None:
    """`[]` charts nothing and `None` charts everything; they must not collapse."""
    assert finetune._resolve_curves(_Recipe({"_progress_reporting": {"curves": []}})) == []


@pytest.mark.parametrize(
    "cfg",
    [
        {},  # a config compiled before the knob existed
        {"_progress_reporting": {}},
        {"_progress_reporting": {"curves": None}},  # the default, stated explicitly
        None,
    ],
)
def test_an_absent_curve_list_charts_everything(finetune: ModuleType, cfg: object) -> None:
    """None is a real configuration here, not only a fallback -- it is the default."""
    assert finetune._resolve_curves(_Recipe(cfg)) is None


@pytest.mark.parametrize(
    "curves",
    ["loss", {"loss": True}, ["loss", 3], [None], 7],
)
def test_an_unusable_curve_list_charts_everything_and_says_so(
    finetune: ModuleType, caplog: pytest.LogCaptureFixture, curves: object
) -> None:
    """Discarded whole: charting some of a malformed list is stranger than charting all.

    A bare string is the trap worth naming -- `curves: loss` in YAML is iterable,
    and taken as a list it would chart the metrics `l`, `o` and `s`.
    """
    recipe = _Recipe({"_progress_reporting": {"curves": curves}})
    with caplog.at_level(logging.WARNING):
        assert finetune._resolve_curves(recipe) is None

    assert "curves" in caplog.text
