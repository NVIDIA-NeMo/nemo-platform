# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_automodel_plugin.schema import AutomodelJobInput


def test_reject_output_model() -> None:
    with pytest.raises(ValueError, match="output_model"):
        AutomodelJobInput.model_validate(
            {
                "model": "llama",
                "dataset": {"training": "default/train"},
                "training": {"training_type": "sft"},
                "output_model": "old-field",
            },
        )


def test_distillation_requires_teacher() -> None:
    with pytest.raises(ValueError, match="teacher_model"):
        AutomodelJobInput.model_validate(
            {
                "model": "llama",
                "dataset": {"training": "default/train"},
                "training": {"training_type": "distillation"},
            },
        )
