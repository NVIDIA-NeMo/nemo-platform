# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import data_designer.config as dd
import pytest
from data_designer_nemo.errors import NDDInvalidConfigError
from data_designer_nemo.model_configs import get_model_configs


def _make_model_config(alias: str) -> dd.ModelConfig:
    return dd.ModelConfig(
        alias=alias,
        model="nvidia/nemotron-3",
        provider="default/nvidia",
    )


@pytest.fixture
def model_configs() -> dict[str, dd.ModelConfig]:
    return {
        "text": _make_model_config("text"),
        "judge": _make_model_config("judge"),
        "reasoner": _make_model_config("reasoner"),
    }


def test_get_model_configs_simple(model_configs: dict[str, dd.ModelConfig]) -> None:
    text = model_configs["text"]
    judge = model_configs["judge"]

    dd_config = dd.DataDesignerConfig(
        model_configs=[text, judge],
        columns=[
            dd.LLMTextColumnConfig(
                name="storytime",
                model_alias="text",
                prompt="Tell me a story",
            )
        ],
        profilers=[dd.JudgeScoreProfilerConfig(model_alias="judge")],
    )

    used_model_configs = get_model_configs(dd_config)

    assert len(used_model_configs) == 2
    assert text in used_model_configs
    assert judge in used_model_configs


def test_get_model_configs_some_unused(model_configs: dict[str, dd.ModelConfig]) -> None:
    text = model_configs["text"]
    reasoner = model_configs["reasoner"]

    dd_config = dd.DataDesignerConfig(
        model_configs=[text, reasoner],
        columns=[
            dd.LLMTextColumnConfig(
                name="storytime",
                model_alias="text",
                prompt="Tell me a story",
            )
        ],
    )

    used_model_configs = get_model_configs(dd_config)

    assert len(used_model_configs) == 1
    assert text in used_model_configs


def test_get_model_configs_unknown_model_alias(model_configs: dict[str, dd.ModelConfig]) -> None:
    text = model_configs["text"]

    unrecognized_1 = "unrecognized-1"
    unrecognized_2 = "unrecognized-2"

    dd_config = dd.DataDesignerConfig(
        model_configs=[text],
        columns=[
            dd.LLMTextColumnConfig(
                name="storytime",
                model_alias=unrecognized_1,
                prompt="Tell me a story",
            )
        ],
        profilers=[dd.JudgeScoreProfilerConfig(model_alias=unrecognized_2)],
    )

    with pytest.raises(NDDInvalidConfigError) as excinfo:
        get_model_configs(dd_config)

    assert unrecognized_1 in str(excinfo.value)
    assert unrecognized_2 in str(excinfo.value)
