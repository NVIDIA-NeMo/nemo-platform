# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guards checked-in Experimentalist example configs that select an evaluator."""

from pathlib import Path

import yaml
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig


def test_tau3_smoke_config_uses_sdk_harbor_evaluator() -> None:
    config_path = Path(__file__).parents[1] / "examples" / "tau3-nooa-agent" / "experimentalist-smoke.yaml"

    config = EvolutionaryOptimizerConfig.model_validate(yaml.safe_load(config_path.read_text(encoding="utf-8")))

    assert config.evaluator_type == "harbor_evaluator"
