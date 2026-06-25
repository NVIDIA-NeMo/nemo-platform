# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public NeMo-RL schema tests: field defaults and the cross-field validators."""

from __future__ import annotations

import pytest
from nmp.customization_common.schemas.values import OutputNameType
from nmp.rl.app.jobs.training.schemas import OptimizerType
from nmp.rl.schemas import DPOTraining, OutputResponse, ParallelismParams, RlJobOutput


def _make_output(name: str = "out", out_type: OutputNameType = OutputNameType.MODEL) -> OutputResponse:
    return OutputResponse(name=name, type=out_type, fileset=f"{name}-fs")


def _make_job_output(training: DPOTraining, out_type: OutputNameType = OutputNameType.MODEL) -> RlJobOutput:
    return RlJobOutput(
        model="default/base",
        dataset="default/prefs",
        training=training,
        output=_make_output(out_type=out_type),
    )


def test_dpo_training_defaults_preserve_prior_behavior() -> None:
    """The newly exposed knobs default to the values the compiler used to hardcode."""
    t = DPOTraining()
    assert t.type == "dpo"
    # Newly exposed configurability.
    assert t.optimizer_type is None  # → AdamW + cosine annealing
    assert t.adam_eps == 1e-5
    assert t.activation_checkpointing is False
    assert t.keep_top_k == 1
    # val_at_end defaults True so the final checkpoint carries validation metrics
    # and best-checkpoint selection works (otherwise NeMo-RL falls back to latest).
    assert t.val_at_end is True
    # Existing DPO hyperparameters.
    assert t.ref_policy_kl_penalty == 0.05
    assert t.sft_loss_weight == 0.0


def test_dpo_training_accepts_overrides() -> None:
    t = DPOTraining(
        optimizer_type=OptimizerType.ADAM_WITH_FLAT_LR,
        adam_eps=1e-8,
        activation_checkpointing=True,
        keep_top_k=3,
        val_at_end=True,
    )
    assert t.optimizer_type is OptimizerType.ADAM_WITH_FLAT_LR
    assert t.adam_eps == 1e-8
    assert t.activation_checkpointing is True
    assert t.keep_top_k == 3
    assert t.val_at_end is True


@pytest.mark.parametrize("bad", [0.0, -1e-5])
def test_adam_eps_must_be_positive(bad: float) -> None:
    with pytest.raises(ValueError):
        DPOTraining(adam_eps=bad)


def test_keep_top_k_must_be_positive() -> None:
    with pytest.raises(ValueError):
        DPOTraining(keep_top_k=0)


def test_validate_for_training_accepts_consistent_single_gpu() -> None:
    # 1 GPU, no model parallelism, gb divisible by micro*dp → no error.
    job = _make_job_output(DPOTraining(batch_size=32, micro_batch_size=1))
    job.validate_for_training()


def test_validate_for_training_rejects_indivisible_model_parallel() -> None:
    # total_gpus=1 but tensor_parallel_size=2 → 1 % 2 != 0.
    job = _make_job_output(
        DPOTraining(parallelism=ParallelismParams(num_gpus_per_node=1, tensor_parallel_size=2)),
    )
    with pytest.raises(ValueError, match="must be divisible by tensor_parallel_size"):
        job.validate_for_training()


def test_validate_for_training_rejects_indivisible_batch() -> None:
    # total_gpus=2, mp=1 → data_parallel=2; batch_size=3 not divisible by micro(1)*dp(2).
    job = _make_job_output(
        DPOTraining(
            parallelism=ParallelismParams(num_gpus_per_node=2),
            batch_size=3,
            micro_batch_size=1,
        ),
    )
    with pytest.raises(ValueError, match="batch_size"):
        job.validate_for_training()


def test_dpo_output_must_be_full_weight_model() -> None:
    # DPO is full-weight; an adapter output is rejected at construction time.
    with pytest.raises(ValueError, match="full-weight model"):
        _make_job_output(DPOTraining(), out_type=OutputNameType.ADAPTER)
