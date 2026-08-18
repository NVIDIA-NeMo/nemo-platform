# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public NeMo-RL schema tests: field defaults and the cross-field validators."""

from __future__ import annotations

from typing import Any

import pytest
from nmp.customization_common.schemas.values import OutputNameType
from nmp.rl.app.jobs.training.schemas import OptimizerType
from nmp.rl.schemas import DPOTraining, GRPOTraining, OutputResponse, ParallelismParams, RlJobOutput


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
    t = DPOTraining(type="dpo")
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
        type="dpo",
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
        DPOTraining(type="dpo", adam_eps=bad)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("learning_rate", 0.0),
        ("learning_rate", -1e-4),
        ("min_learning_rate", -1e-4),
        ("weight_decay", -0.01),
        ("adam_beta1", -0.1),
        ("adam_beta1", 1.0),
        ("adam_beta2", -0.1),
        ("adam_beta2", 1.0),
    ],
)
def test_optimizer_bounds(field: str, bad: float) -> None:
    kwargs: dict[str, Any] = {field: bad}
    with pytest.raises(ValueError):
        DPOTraining(type="dpo", **kwargs)


def test_keep_top_k_must_be_positive() -> None:
    with pytest.raises(ValueError):
        DPOTraining(type="dpo", keep_top_k=0)


def test_validate_for_training_accepts_consistent_single_gpu() -> None:
    # 1 GPU, no model parallelism, gb divisible by micro*dp → no error.
    job = _make_job_output(DPOTraining(type="dpo", batch_size=32, micro_batch_size=1))
    job.validate_for_training()


def test_validate_for_training_rejects_indivisible_model_parallel() -> None:
    # total_gpus=1 but tensor_parallel_size=2 → 1 % 2 != 0.
    job = _make_job_output(
        DPOTraining(type="dpo", parallelism=ParallelismParams(num_gpus_per_node=1, tensor_parallel_size=2)),
    )
    with pytest.raises(ValueError, match="must be divisible by tensor_parallel_size"):
        job.validate_for_training()


def test_validate_for_training_rejects_indivisible_batch() -> None:
    # total_gpus=2, mp=1 → data_parallel=2; batch_size=3 not divisible by micro(1)*dp(2).
    job = _make_job_output(
        DPOTraining(
            type="dpo",
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
        _make_job_output(DPOTraining(type="dpo"), out_type=OutputNameType.ADAPTER)


def test_grpo_requires_environment() -> None:
    job = RlJobOutput(
        model="default/base",
        dataset="default/gym-data",
        training=GRPOTraining(type="grpo"),
        output=_make_output(),
    )
    with pytest.raises(ValueError, match="environment fileset"):
        job.validate_for_training()


def test_grpo_training_discriminator() -> None:
    t = GRPOTraining(type="grpo")
    assert t.type == "grpo"
    assert t.num_generations_per_prompt == 8
    assert t.finetuning_type == "all_weights"
    assert t.lora is None


def test_grpo_lora_defaults_params() -> None:
    t = GRPOTraining(type="grpo", finetuning_type="lora")
    assert t.lora is not None
    assert t.lora.rank == 16
    assert t.lora.alpha == 32


def test_grpo_lora_rejects_params_with_all_weights() -> None:
    from nmp.rl.schemas import LoRAParams

    with pytest.raises(ValueError, match="lora must be omitted"):
        GRPOTraining(type="grpo", finetuning_type="all_weights", lora=LoRAParams(rank=8))


def test_grpo_lora_rejects_lora_merged() -> None:
    # `type` is required, so omitting it raises before finetuning_type is ever
    # looked at -- this would pass even if lora_merged were accepted. Match on the
    # field name so the assertion is about lora_merged and nothing else.
    with pytest.raises(ValueError, match="finetuning_type"):
        GRPOTraining(type="grpo", finetuning_type="lora_merged")  # type: ignore[arg-type]


def test_grpo_lora_requires_adapter_output() -> None:
    with pytest.raises(ValueError, match="adapter"):
        RlJobOutput(
            model="default/base",
            dataset="default/gym-data",
            environment="default/env",
            training=GRPOTraining(type="grpo", finetuning_type="lora"),
            output=_make_output(out_type=OutputNameType.MODEL),
        )


def test_grpo_lora_accepts_adapter_output() -> None:
    job = RlJobOutput(
        model="default/base",
        dataset="default/gym-data",
        environment="default/env",
        training=GRPOTraining(type="grpo", finetuning_type="lora", lora=None),
        output=_make_output(out_type=OutputNameType.ADAPTER),
    )
    assert job.output.type is OutputNameType.ADAPTER
    job.validate_for_training()


def test_grpo_sampling_defaults_preserve_previous_behaviour() -> None:
    """These were hardcoded in the compiler; the defaults must reproduce them exactly."""
    t = GRPOTraining(type="grpo")
    assert t.temperature == 1.0
    # None means "use the whole context", which is what max_seq_length gave before.
    assert t.max_new_tokens is None


def test_grpo_rejects_greedy_temperature() -> None:
    """Temperature 0 makes every rollout in a group identical.

    GRPO's advantage is the spread of rewards within a prompt group. With no spread the
    advantage is zero for every sample and the run trains on nothing -- silently, since
    rewards still look plausible. Cheaper to reject at submit time than to discover after
    150 steps of flat loss.
    """
    with pytest.raises(ValueError):
        GRPOTraining(type="grpo", temperature=0.0)


def test_grpo_rejects_max_new_tokens_larger_than_context() -> None:
    with pytest.raises(ValueError, match="cannot exceed max_seq_length"):
        GRPOTraining(type="grpo", max_seq_length=2048, max_new_tokens=4096)


def test_grpo_accepts_max_new_tokens_up_to_the_context() -> None:
    t = GRPOTraining(type="grpo", max_seq_length=2048, max_new_tokens=2048)
    assert t.max_new_tokens == 2048
