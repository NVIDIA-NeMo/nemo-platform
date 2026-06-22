# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``build_model_load_kwargs`` in the unsloth SFT driver.

These exercise the torch-free kwargs assembly only, so the module imports
fine on a CPU box without ``unsloth``/``torch`` installed.
"""

from __future__ import annotations

from nmp.unsloth.schemas import (
    DatasetSpec,
    ModelLoadSpec,
    OutputResponse,
    TrainingSpec,
    UnslothJobOutput,
)
from nmp.unsloth.tasks.training.backends.unsloth_sft import build_model_load_kwargs


def _spec(*, finetuning_type: str, load_in_4bit: bool) -> UnslothJobOutput:
    return UnslothJobOutput(
        model=ModelLoadSpec(name="meta/llama-3.1-8b", load_in_4bit=load_in_4bit),
        dataset=DatasetSpec(path="ws/train"),
        training=TrainingSpec(finetuning_type=finetuning_type),
        output=OutputResponse(name="out", type="model", save_method="lora", fileset="out"),
    )


def test_all_weights_sets_full_finetuning() -> None:
    # all-weights FT loads in 16-bit (validator forbids 4/8-bit upstream) and
    # MUST request full_finetuning so Unsloth uses the full-FT load path.
    kwargs = build_model_load_kwargs(_spec(finetuning_type="all_weights", load_in_4bit=False), "/local/model")
    assert kwargs["full_finetuning"] is True
    assert kwargs["load_in_4bit"] is False
    assert kwargs["model_name"] == "/local/model"


def test_lora_does_not_set_full_finetuning() -> None:
    kwargs = build_model_load_kwargs(_spec(finetuning_type="lora", load_in_4bit=True), "/local/model")
    assert kwargs["full_finetuning"] is False
    assert kwargs["load_in_4bit"] is True


def test_dtype_not_included() -> None:
    # dtype mapping needs torch and stays in train_sft; the helper must not emit it.
    kwargs = build_model_load_kwargs(_spec(finetuning_type="lora", load_in_4bit=True), "/local/model")
    assert "dtype" not in kwargs
