# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical NeMo-RL job / training schemas — consumed by the compiler and drivers."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self, Union

from nemo_platform_plugin.integrations import IntegrationsSpec
from nmp.customization_common.schema import NamespacedModel
from nmp.customization_common.schemas.values import OutputNameType
from nmp.customization_common.training.reporting import ProgressReportingConfig
from nmp.rl.app.jobs.training.schemas import OptimizerType
from nmp.rl.entities.values import TrainingType
from pydantic import ConfigDict, Discriminator, Field, model_validator


class RlSchema(NamespacedModel):
    """Backend base: every RL-owned model emits an ``Rl``-prefixed OpenAPI schema
    name (``DPOTraining`` -> ``RlDPOTraining``), so it can't collide with another
    backend's same-named model in the merged ``/apis/customization`` spec.
    """

    __schema_namespace__ = "Rl"


class ParallelismParams(RlSchema):
    """Distributed training parallelism configuration."""

    num_gpus_per_node: int = Field(default=1, gt=0, description="Number of GPUs per node.")
    num_nodes: int = Field(default=1, gt=0, description="Number of nodes (>1 → multi-node Ray cluster).")
    tensor_parallel_size: int = Field(default=1, gt=0, description="Tensor parallel size.")
    pipeline_parallel_size: int = Field(default=1, gt=0, description="Pipeline parallel size.")
    context_parallel_size: int = Field(default=1, gt=0, description="Context parallel size.")
    expert_parallel_size: int = Field(
        default=1,
        gt=0,
        description="Expert parallel size for MoE models. GRPO only; a value above 1 selects the DTensor v2 backend.",
    )
    sequence_parallel: bool = Field(default=False, description="Enable sequence parallelism.")


class LoRAParams(RlSchema):
    """LoRA hyperparameters for GRPO (DTensor ``lora_cfg``). No merge-at-export."""

    rank: int = Field(default=16, gt=0, description="LoRA rank (r); maps to NeMo-RL lora_cfg.dim.")
    alpha: int = Field(default=32, gt=0, description="LoRA scaling factor (effective lr multiplier = alpha/rank).")
    dropout: float = Field(default=0.0, ge=0.0, le=1.0, description="LoRA dropout probability.")
    target_modules: list[str] | None = Field(
        default=None,
        description="Module names to adapt. Empty/None with match_all_linear applies to all linear layers.",
    )
    exclude_modules: list[str] | None = Field(
        default=None,
        description="Module name patterns to exclude from LoRA.",
    )
    use_triton: bool = Field(
        default=True,
        description="Use Triton LoRA kernels (DTensor v2). Set false when tensor_parallel_size > 1.",
    )


class _TrainingBase(RlSchema):
    """Common training configuration shared by all RL methods."""

    model_config = ConfigDict(protected_namespaces=())

    # --- Optimizer ---
    optimizer_type: OptimizerType | None = Field(
        default=None,
        description="Optimizer + LR-scheduler combination (AdamW/Adam × cosine-annealing/flat-LR). "
        "Defaults to AdamW with cosine annealing.",
    )
    learning_rate: float = Field(default=1e-4, gt=0.0, description="Peak learning rate.")
    min_learning_rate: float | None = Field(default=None, ge=0.0, description="Minimum LR for cosine decay.")
    weight_decay: float = Field(default=0.01, ge=0.0, description="Weight decay coefficient.")
    adam_beta1: float = Field(default=0.9, ge=0.0, lt=1.0, description="Adam beta1.")
    adam_beta2: float = Field(default=0.999, ge=0.0, lt=1.0, description="Adam beta2.")
    adam_eps: float = Field(default=1e-5, gt=0.0, description="Adam epsilon (numerical stability term).")
    warmup_steps: int = Field(default=0, ge=0, description="Linear warmup steps.")

    # --- Schedule ---
    epochs: int = Field(default=1, gt=0, description="Number of passes through the dataset.")
    max_steps: int | None = Field(default=None, gt=0, description="Max training steps (overrides epochs if set).")
    val_check_interval: float | None = Field(
        default=None,
        description="Validation interval. Float <= 1.0 is fraction of epoch; > 1.0 is step count.",
    )
    val_at_end: bool = Field(
        default=True,
        description="Run a final validation pass after the last training step. Keep enabled so the "
        "final checkpoint carries validation metrics and best-checkpoint selection works; "
        "set False only to skip the extra eval. GRPO ignores this when the dataset ships no "
        "validation.jsonl.",
    )
    progress_reporting: ProgressReportingConfig = Field(default_factory=ProgressReportingConfig)

    # --- Checkpointing ---
    keep_top_k: int = Field(
        default=1, gt=0, description="Number of best checkpoints to retain (ranked by validation loss)."
    )

    # --- Batch ---
    batch_size: int = Field(default=32, gt=0, description="Global batch size across all GPUs.")
    micro_batch_size: int = Field(default=1, gt=0, description="Per-GPU micro batch size.")
    activation_checkpointing: bool = Field(
        default=False,
        description="Recompute activations during the backward pass to reduce memory at the cost of compute. "
        "Enable to fit larger models or longer sequences.",
    )

    # --- Model ---
    max_seq_length: int = Field(default=2048, gt=0, description="Maximum token sequence length for training.")
    seed: int | None = Field(default=None, description="Random seed for reproducibility.")

    # --- Infrastructure ---
    parallelism: ParallelismParams = Field(default_factory=ParallelismParams)
    execution_profile: str | None = Field(
        default=None,
        min_length=1,
        description="Execution profile for the GPU training step (operator-configured). "
        "Falls back to the service default when omitted.",
    )


class DPOTraining(_TrainingBase):
    """Direct Preference Optimization (full-weight only — PEFT unsupported)."""

    # No default: ``TrainingMethod`` is a discriminated union, so the tag has to be
    # present in the submitted JSON. Defaulting it here would make the generated
    # OpenAPI schema advertise the field as optional while the server rejects it.
    type: Literal["dpo"]
    ref_policy_kl_penalty: float = Field(
        default=0.05, ge=0.0, description="KL penalty coefficient (beta in the DPO paper)."
    )
    preference_average_log_probs: bool = Field(
        default=False, description="Average log probabilities for preference loss calculation."
    )
    sft_average_log_probs: bool = Field(
        default=False, description="Average log probabilities for SFT regularization loss."
    )
    preference_loss_weight: float = Field(default=1.0, ge=0.0, description="Weight for the preference (DPO) loss term.")
    sft_loss_weight: float = Field(
        default=0.0, ge=0.0, description="Weight for SFT regularization loss (0 = disabled)."
    )
    max_grad_norm: float = Field(default=1.0, ge=0.0, description="Maximum gradient norm for clipping.")


class GRPOTraining(_TrainingBase):
    """Group Relative Policy Optimization with NeMo Gym environments.

    ``finetuning_type`` is ``all_weights`` (default) or ``lora`` only.
    ``lora_merged`` is not supported for GRPO on the platform DTensor path.
    """

    # No default: ``TrainingMethod`` is a discriminated union, so the tag has to be
    # present in the submitted JSON (same as DPOTraining.type).
    type: Literal["grpo"]
    finetuning_type: Literal["all_weights", "lora"] = Field(
        default="all_weights",
        description="Full-weight GRPO or LoRA adapter training. lora_merged is not supported.",
    )
    lora: LoRAParams | None = Field(
        default=None,
        description="LoRA hyperparameters. Defaults applied when finetuning_type is lora.",
    )
    val_at_start: bool = Field(
        default=False,
        description="Run a validation pass before the first training step. Enable it to measure "
        "uplift: the baseline and the trained result then come from one job, on the same data with "
        "the same generation settings, instead of a separate baseline run that has to be kept in "
        "sync. Off by default because a GRPO baseline costs a full rollout pass. Ignored when the "
        "dataset ships no validation.jsonl. DPO always validates at step 0 and has no such knob, "
        "since its validation needs no generation.",
    )
    num_generations_per_prompt: int = Field(
        default=8, gt=0, description="Group size: rollouts sampled per prompt, used for relative advantages."
    )
    num_prompts_per_step: int | None = Field(
        default=None,
        gt=0,
        description="Prompts sampled per training step. Derived from batch_size / "
        "num_generations_per_prompt when omitted; the product of the two must be a "
        "multiple of batch_size.",
    )
    temperature: float = Field(
        default=1.0,
        gt=0.0,
        le=2.0,
        description="Sampling temperature for rollout generation. Must be greater than 0: "
        "GRPO's advantage is the spread of rewards inside a prompt group, so greedy sampling "
        "makes every rollout in a group identical, the spread zero, and the whole run a no-op. "
        "Applies to validation rollouts too, which are generated with the same settings.",
    )
    max_new_tokens: int | None = Field(
        default=None,
        gt=0,
        description="Cap on tokens generated per rollout turn. Defaults to max_seq_length, "
        "which lets a rollout run until the context is exhausted; vLLM clamps it to whatever "
        "the prompt leaves. Cannot exceed max_seq_length. NOTE: NeMo Gym's verifiers_agent "
        "does not yet honour this -- it reads max_tokens from its own environment config and "
        "drops the per-row value, so the effective cap is "
        "min(agent max_tokens, max_seq_length - prompt_len). Until that is fixed, bound "
        "response length through max_seq_length or the environment's own max_tokens.",
    )
    normalize_rewards: bool = Field(default=True, description="Normalize rewards within each prompt group.")
    overlong_filtering: bool = Field(
        default=False,
        description="Zero the loss contribution of rollouts truncated by the generation limit. "
        "Enable when a low max_new_tokens truncates many rollouts, so the policy is not penalised "
        "for responses it was cut off from finishing.",
    )
    max_rollout_turns: int = Field(
        default=1, gt=0, description="Maximum agent turns per rollout. Single-turn environments use 1."
    )
    ref_policy_kl_penalty: float = Field(
        default=0.0, ge=0.0, description="KL penalty coefficient against the reference policy."
    )
    ratio_clip_min: float = Field(default=0.2, ge=0.0, description="Lower PPO-style importance ratio clip bound.")
    ratio_clip_max: float = Field(default=0.28, ge=0.0, description="Upper PPO-style importance ratio clip bound.")
    max_grad_norm: float = Field(default=1.0, ge=0.0, description="Maximum gradient norm for clipping.")

    # --- Per-architecture backend settings ---
    automodel_kwargs: dict[str, Any] | None = Field(
        default=None,
        description="Passed to policy.dtensor_cfg.automodel_kwargs; selects the DTensor v2 backend. "
        "{'force_hf': true} loads the stock HuggingFace modules; a {'backend': {...}} block picks "
        "the Transformer-Engine / DeepEP MoE implementation. Unset means Automodel auto-detects.",
    )
    router_aux_loss_coef: float | None = Field(
        default=None,
        ge=0.0,
        description="MoE router auxiliary-loss coefficient, applied as a HuggingFace config override. "
        "Use 0.0 to drop the load-balancing term during RL. Unset keeps the model's own value.",
    )
    vllm_tensor_parallel_size: int | None = Field(
        default=None,
        gt=0,
        description="Tensor parallel size for the vLLM rollout engine, independent of the policy's. "
        "Defaults to min(parallelism.tensor_parallel_size, parallelism.num_gpus_per_node).",
    )
    vllm_gpu_memory_utilization: float = Field(
        default=0.5,
        gt=0.0,
        le=1.0,
        description="Fraction of each GPU vLLM reserves for weights plus KV cache. Raise toward 0.7 "
        "for large models; the rest is left for the colocated policy.",
    )

    @model_validator(mode="after")
    def _lora_defaults(self) -> Self:
        if self.finetuning_type == "lora" and self.lora is None:
            self.lora = LoRAParams()
        if self.finetuning_type == "all_weights" and self.lora is not None:
            raise ValueError("lora must be omitted when finetuning_type is all_weights")
        return self

    @model_validator(mode="after")
    def _generation_length_fits_context(self) -> Self:
        # max_seq_length is the whole context, prompt included. Asking for more generated
        # tokens than that is always unsatisfiable, and vLLM would silently clamp it
        # rather than say so.
        if self.max_new_tokens is not None and self.max_new_tokens > self.max_seq_length:
            raise ValueError(
                f"max_new_tokens ({self.max_new_tokens}) cannot exceed max_seq_length "
                f"({self.max_seq_length}); max_seq_length is the total prompt + generation budget"
            )
        return self


TrainingMethod = Annotated[Union[DPOTraining, GRPOTraining], Discriminator("type")]


class _OutputBase(RlSchema):
    name: str = Field(max_length=255, examples=["my-dpo-llama"])


class OutputRequest(_OutputBase):
    """Output artifact configuration provided by the user."""


class OutputResponse(_OutputBase):
    """Resolved output artifact details."""

    type: OutputNameType = Field(default=OutputNameType.MODEL)
    fileset: str = Field(max_length=255)


class RlJobOutput(RlSchema):
    """Canonical NeMo-RL job spec (output of the plugin transform)."""

    model_config = ConfigDict(protected_namespaces=())

    name: str | None = Field(default=None)
    model: str = Field(description="Model entity reference ('name' or 'workspace/name').")
    dataset: str = Field(description="Dataset fileset reference ('name' or 'workspace/name').")
    environment: str | None = Field(default=None)
    training: TrainingMethod = Field(description="Training method and hyperparameters.")
    integrations: IntegrationsSpec | None = Field(default=None)
    output: OutputResponse = Field(description="Output artifact created by this job.")

    @property
    def training_type(self) -> TrainingType:
        return TrainingType(self.training.type)

    def validate_for_training(self) -> None:
        """Validate parallelism/batch consistency before compiling."""
        training = self.training
        p = training.parallelism
        total_gpus = p.num_gpus_per_node * p.num_nodes
        # NeMo-RL derives dp_size = world_size // (tp * cp * ep), so ep belongs in this product.
        model_parallel_size = (
            p.tensor_parallel_size * p.pipeline_parallel_size * p.context_parallel_size * p.expert_parallel_size
        )
        if total_gpus % model_parallel_size != 0:
            raise ValueError(
                f"Total GPUs ({total_gpus}) must be divisible by tensor_parallel_size "
                f"({p.tensor_parallel_size}) * pipeline_parallel_size ({p.pipeline_parallel_size}) * "
                f"context_parallel_size ({p.context_parallel_size}) * expert_parallel_size "
                f"({p.expert_parallel_size}) = {model_parallel_size}"
            )
        derived_dp = total_gpus // model_parallel_size
        gb, mb = training.batch_size, training.micro_batch_size
        divisor = mb * derived_dp
        if gb % divisor != 0:
            raise ValueError(
                f"batch_size ({gb}) must be divisible by micro_batch_size ({mb}) * "
                f"data_parallel_size ({derived_dp}) = {divisor}."
            )
        if isinstance(training, GRPOTraining):
            if not self.environment:
                raise ValueError("GRPO jobs require an environment fileset reference.")
            # The rollout engine meshes over the same GPUs under its own rule: vllm_generation.py
            # asserts world_size % tp == 0, and one engine does not span nodes.
            vllm_tp = training.vllm_tensor_parallel_size
            if vllm_tp is not None:
                if vllm_tp > p.num_gpus_per_node:
                    raise ValueError(
                        f"vllm_tensor_parallel_size ({vllm_tp}) cannot exceed num_gpus_per_node "
                        f"({p.num_gpus_per_node}); a single vLLM engine does not shard across nodes."
                    )
                if total_gpus % vllm_tp != 0:
                    raise ValueError(
                        f"Total GPUs ({total_gpus}) must be divisible by vllm_tensor_parallel_size ({vllm_tp})."
                    )
            # The rollout batch is num_prompts_per_step * num_generations_per_prompt, and
            # NeMo-RL shards it by the train batch. When num_prompts_per_step is derived,
            # the floor division can leave the two out of step (e.g. 32 // 5 = 6 -> 30 vs
            # 32), which only surfaces as an assert at the first optimizer step.
            gen = training.num_generations_per_prompt
            prompts = training.num_prompts_per_step or max(gb // max(gen, 1), 1)
            rollout = prompts * gen
            if rollout % gb != 0:
                raise ValueError(
                    f"num_prompts_per_step ({prompts}) * num_generations_per_prompt ({gen}) "
                    f"= {rollout} must be a multiple of batch_size ({gb}). Choose a "
                    f"num_generations_per_prompt that divides batch_size, or set "
                    f"num_prompts_per_step explicitly."
                )

    @model_validator(mode="after")
    def _output_type_matches_training(self) -> Self:
        if self.training_type == TrainingType.DPO and self.output.type != OutputNameType.MODEL:
            raise ValueError("DPO produces a full-weight model; output.type must be 'model'.")
        if self.training_type == TrainingType.GRPO:
            assert isinstance(self.training, GRPOTraining)
            if self.training.finetuning_type == "lora":
                if self.output.type != OutputNameType.ADAPTER:
                    raise ValueError("GRPO LoRA produces an adapter; output.type must be 'adapter'.")
            elif self.output.type != OutputNameType.MODEL:
                raise ValueError("GRPO all_weights produces a full-weight model; output.type must be 'model'.")
        return self
