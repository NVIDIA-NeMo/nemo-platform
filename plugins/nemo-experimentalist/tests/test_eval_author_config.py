# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist config wiring for the nested Eval Author settings block."""

import pytest
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizerConfig


def test_evolutionary_optimizer_uses_top_level_eval_author_config() -> None:
    config = EvolutionaryOptimizerConfig().eval_author

    assert type(config) is EvalAuthorConfig
    assert config.max_validation_repair_attempts == 5


def test_evolutionary_optimizer_tolerates_unknown_eval_author_config() -> None:
    config = EvolutionaryOptimizerConfig.model_validate({"eval_author": {"bogus": 1}})
    assert type(config.eval_author) is EvalAuthorConfig


def test_evolutionary_optimizer_rejects_legacy_curator_config() -> None:
    with pytest.raises(ValueError, match="'curator' was renamed to 'eval_author'"):
        EvolutionaryOptimizerConfig.model_validate({"curator": {"max_traces": 1}})
