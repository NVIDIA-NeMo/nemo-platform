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


def test_the_compiled_metric_list_is_used(finetune: ModuleType) -> None:
    recipe = _Recipe({"_progress_reporting": {"time_series_metrics": ["train_loss", "*_lr"]}})

    assert finetune._resolve_time_series_metrics(recipe) == ["train_loss", "*_lr"]


def test_an_empty_list_is_kept_rather_than_read_as_absent(finetune: ModuleType) -> None:
    """`[]` records nothing and absent takes the default; they must not collapse.

    An empty list is a legitimate request -- current values with no history at
    all -- and it is the one value a truthiness check would silently convert into
    its opposite.
    """
    assert finetune._resolve_time_series_metrics(_Recipe({"_progress_reporting": {"time_series_metrics": []}})) == []


@pytest.mark.parametrize(
    "cfg",
    [
        {},  # a config compiled before the knob existed
        {"_progress_reporting": {}},
        {"_progress_reporting": {"time_series_metrics": None}},  # stated explicitly
        None,
    ],
)
def test_an_absent_list_takes_the_backend_default(finetune: ModuleType, cfg: object) -> None:
    """Absent means the backend's default, not everything.

    `["*"]` is how a user asks for every metric, which matters because the two
    now differ: the default drops automodel's five throughput and accounting
    counters.
    """
    assert finetune._resolve_time_series_metrics(_Recipe(cfg)) == finetune.DIAGNOSTIC_TIME_SERIES


def test_the_default_keeps_the_diagnostic_metrics_and_drops_the_counters(finetune: ModuleType) -> None:
    """Pinned against automodel's real metric names, read out of the recipes.

    Train comes from `train_ft.py` `_run_train_optim_step`, validation from
    `_run_validation_epoch` after `strip_val_prefix`. If a recipe adds a metric,
    this says whether it lands in the default set or not.
    """
    from fnmatch import fnmatchcase

    patterns = finetune.DIAGNOSTIC_TIME_SERIES
    kept = {
        name
        for name in (
            "train_loss",
            "train_grad_norm",
            "train_lr",
            "train_mem",
            "train_tps",
            "train_tps_per_gpu",
            "train_num_tokens_per_step",
            "train_num_label_tokens",
            "val_loss",
            "val_lr",
            "val_num_label_tokens",
            "val_mem",
        )
        if any(fnmatchcase(name, p) for p in patterns)
    }

    assert kept == {"train_loss", "train_grad_norm", "train_lr", "val_loss", "val_lr"}


@pytest.mark.parametrize(
    "names",
    ["train_loss", {"train_loss": True}, ["train_loss", 3], [None], 7],
)
def test_an_unusable_list_falls_back_to_the_default_and_says_so(
    finetune: ModuleType, caplog: pytest.LogCaptureFixture, names: object
) -> None:
    """Discarded whole: half a malformed list is a silently arbitrary set of curves.

    A bare string is the trap worth naming -- `time_series_metrics: train_loss`
    in YAML is iterable, and taken as a list it would look for metrics named
    `t`, `r`, `a` and so on.
    """
    recipe = _Recipe({"_progress_reporting": {"time_series_metrics": names}})
    with caplog.at_level(logging.WARNING):
        assert finetune._resolve_time_series_metrics(recipe) == finetune.DIAGNOSTIC_TIME_SERIES

    assert "time_series_metrics" in caplog.text
