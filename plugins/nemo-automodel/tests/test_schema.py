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


def test_training_recipe_defaults_to_auto() -> None:
    spec = AutomodelJobInput.model_validate(
        {
            "model": "llama",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "finetuning_type": "all_weights"},
        }
    )

    assert spec.training.recipe == "auto"
    assert spec.optimizer.optimizer == "auto"


@pytest.mark.parametrize("optimizer", ["auto", "Adam", "AdamW", "FusedAdam"])
def test_optimizer_is_selectable(optimizer: str) -> None:
    spec = AutomodelJobInput.model_validate(
        {
            "model": "llama",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "finetuning_type": "all_weights"},
            "optimizer": {"optimizer": optimizer},
        }
    )

    assert spec.optimizer.optimizer == optimizer


def test_distillation_rejects_encoder_recipe() -> None:
    with pytest.raises(ValueError, match="only supports the sft recipe"):
        AutomodelJobInput.model_validate(
            {
                "model": "llama",
                "dataset": {"training": "default/train"},
                "training": {
                    "training_type": "distillation",
                    "teacher_model": "default/teacher",
                    "recipe": "cross_encoder",
                },
            }
        )


def test_encoder_recipes_apply_nemotron_job_defaults() -> None:
    embed = AutomodelJobInput.model_validate(
        {
            "model": "embed",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "recipe": "bi_encoder", "finetuning_type": "all_weights"},
        }
    )
    rerank = AutomodelJobInput.model_validate(
        {
            "model": "rerank",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "recipe": "cross_encoder", "finetuning_type": "all_weights"},
        }
    )

    assert embed.batch.global_batch_size == 128
    assert embed.batch.micro_batch_size == 4
    assert embed.optimizer.learning_rate == 1e-5
    assert embed.optimizer.warmup_steps == 5
    assert rerank.optimizer.learning_rate == 3e-6
    assert rerank.optimizer.warmup_steps == 100


def test_encoder_recipe_defaults_do_not_override_explicit_hparams() -> None:
    spec = AutomodelJobInput.model_validate(
        {
            "model": "embed",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "recipe": "bi_encoder", "finetuning_type": "all_weights"},
            "batch": {"global_batch_size": 16, "micro_batch_size": 2},
            "optimizer": {"learning_rate": 2e-5, "warmup_steps": 1},
        }
    )
    assert spec.batch.global_batch_size == 16
    assert spec.batch.micro_batch_size == 2
    assert spec.optimizer.learning_rate == 2e-5
    assert spec.optimizer.warmup_steps == 1
