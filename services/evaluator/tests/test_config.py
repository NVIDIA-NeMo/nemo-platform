# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from unittest import mock

import pytest
from nmp.evaluator.config import EvaluatorSettings


def test_defaults():
    settings = EvaluatorSettings()
    assert settings.jobs.configs_dir == "/configs"


@pytest.mark.unit_test
@mock.patch.dict(
    os.environ,
    {
        "NMP_EVALUATOR_JOBS": '{"configs_dir": "/new/configs/path"}',
    },
)
def test_env_override():
    settings = EvaluatorSettings()
    assert settings.jobs.configs_dir == "/new/configs/path"
