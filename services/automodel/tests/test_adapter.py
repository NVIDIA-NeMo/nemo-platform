# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nmp.automodel.adapter import automodel_spec_to_compiler_output
from nmp.automodel.api.v2.jobs.schemas import DistillationTraining, SFTTraining


def test_adapter_sft() -> None:
    spec = automodel_spec_to_compiler_output(
        {
            "model": "meta/llama",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "finetuning_type": "lora"},
            "output": {"name": "out", "type": "adapter", "fileset": "out-fs"},
        },
    )
    assert isinstance(spec.training, SFTTraining)
    assert spec.dataset == "default/train"


def test_adapter_distillation() -> None:
    spec = automodel_spec_to_compiler_output(
        {
            "model": "meta/llama",
            "dataset": {"training": "default/train"},
            "training": {
                "training_type": "distillation",
                "finetuning_type": "all_weights",
                "teacher_model": "meta/teacher",
            },
            "output": {"name": "out", "type": "model", "fileset": "out-fs"},
        },
    )
    assert isinstance(spec.training, DistillationTraining)
    assert spec.training.teacher_model == "meta/teacher"
