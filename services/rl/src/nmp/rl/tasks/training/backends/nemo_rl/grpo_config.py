# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TrainingStepConfig → NeMo RL YAML for GRPO + NeMo Gym."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nmp.customization_common.service.constants import SANDBOX_DATASET_PATH, SANDBOX_ENVIRONMENT_PATH, SANDBOX_WORK_PATH
from nmp.customization_common.service.context import NMPJobContext
from nmp.rl.app.jobs.training.schemas import GRPOConfig, TrainingStepConfig
from nmp.rl.tasks.training.backends.nemo_rl.dpo_config import (
    _adapt_precision,
    _build_logger_config,
    _build_optimizer_config,
    _build_scheduler_config,
    _megatron_cfg_disabled,
)
from nmp.rl.tasks.training.backends.nemo_rl.sandbox_config import (
    NemoGymSandboxedConfig,
    SandboxConfig,
    SandboxNetworkPolicy,
    assemble_master_egress_allow,
    bootstrap_env_from_job,
    resolve_ephemeral_work_path,
)
from nmp.rl.tasks.training.chat_templates import resolve_chat_template
from nmp.rl.tasks.training.datasets.preparation import compute_val_check_interval, prepare_dataset
from nmp.rl.tasks.training.datasets.validation import DatasetValidator

logger = logging.getLogger(__name__)


def _count_jsonl_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _resolve_gym_paths(
    customizer_config: TrainingStepConfig,
    workspace_dir: Path,
) -> tuple[Path, Path, int, int]:
    """Return train/val paths and sample counts for Gym JSONL."""
    gym = customizer_config.gym
    if gym and gym.sandboxed and gym.sandbox_dataset_path:
        train_path = Path(gym.sandbox_dataset_path) / "training.jsonl"
        val_path = Path(gym.sandbox_dataset_path) / "validation.jsonl"
        pvc_train = Path(customizer_config.dataset.path) / "training.jsonl"
        pvc_val = Path(customizer_config.dataset.path) / "validation.jsonl"
        validator = DatasetValidator(training_type=customizer_config.training.training_type)
        validator.validate_dataset(str(pvc_train))
        if pvc_val.is_file():
            validator.validate_dataset(str(pvc_val))
        return train_path, val_path, _count_jsonl_rows(pvc_train), _count_jsonl_rows(pvc_val)

    prepared = prepare_dataset(
        dataset_path=Path(customizer_config.dataset.path),
        output_dir=workspace_dir / "dataset",
    )
    validator = DatasetValidator(training_type=customizer_config.training.training_type)
    validator.validate_dataset(str(prepared.train_file))
    if prepared.validation_samples:
        validator.validate_dataset(str(prepared.validation_file))
    return (
        prepared.train_file,
        prepared.validation_file,
        prepared.train_samples,
        prepared.validation_samples,
    )


def _build_nemo_gym_env_config(
    customizer_config: TrainingStepConfig,
    job_ctx: NMPJobContext,
) -> dict[str, Any]:
    gym = customizer_config.gym
    if gym is None:
        raise ValueError("GRPO jobs require gym configuration on TrainingStepConfig")

    sandboxed = gym.sandboxed
    env_block: dict[str, Any] = {
        "should_use_nemo_gym": True,
        "should_log_nemo_gym_responses": False,
        "should_mask_flagged_samples": True,
        "nemo_gym": {
            "port_range_low": 5000,
            "port_range_high": 5999,
        },
    }

    nemo_gym = env_block["nemo_gym"]
    if sandboxed:
        runtime_image = gym.gym_runtime_image or "nvcr.io/nvidia/nemo-gym-runtime:latest"

        sandbox_cfg = NemoGymSandboxedConfig(
            sandboxed=True,
            host_provider="opensandbox",
            environment_path=gym.sandbox_environment_path or SANDBOX_ENVIRONMENT_PATH,
            sandbox=SandboxConfig(
                image=runtime_image,
                env_mount_path=SANDBOX_ENVIRONMENT_PATH,
                dataset_mount_path=SANDBOX_DATASET_PATH,
                # Sandbox mount is /job/work; ephemeral host work prefers /scratch or /tmp.
                work_mount_path=SANDBOX_WORK_PATH,
                network_policy=SandboxNetworkPolicy(
                    # Defaults until the training master resolves live vLLM/broker endpoints.
                    egress_allow=assemble_master_egress_allow(),
                ),
            ),
        )
        nemo_gym.update(sandbox_cfg.model_dump(mode="python", exclude_none=True))

        work_path = resolve_ephemeral_work_path(job_ctx.job_id)
        bootstrap = bootstrap_env_from_job(
            job_id=job_ctx.job_id,
            environment_path=gym.sandbox_environment_path or SANDBOX_ENVIRONMENT_PATH,
            dataset_path=gym.sandbox_dataset_path or SANDBOX_DATASET_PATH,
            work_path=work_path,
        )
        nemo_gym["bootstrap_env"] = bootstrap
        nemo_gym["host_work_path"] = work_path
    else:
        nemo_gym["environment_path"] = gym.environment_path
        if gym.environment_path:
            manifest_path = Path(gym.environment_path) / "nemo-environment.yaml"
            if manifest_path.is_file():
                import yaml

                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if isinstance(manifest, dict) and manifest.get("config_paths"):
                    nemo_gym["config_paths"] = list(manifest["config_paths"])

    return env_block


def compile_grpo_config(
    customizer_config: TrainingStepConfig,
    job_ctx: NMPJobContext,
) -> dict[str, Any]:
    """Compile TrainingStepConfig to NeMo RL GRPO + NeMo Gym configuration."""
    cfg: dict[str, Any] = {}
    workspace_dir = Path(customizer_config.workspace_path)
    grpo_hp = customizer_config.training.grpo or GRPOConfig()

    train_path, val_path, train_samples, val_samples = _resolve_gym_paths(customizer_config, workspace_dir)

    batch_size = customizer_config.batch.global_batch_size
    micro_batch_size = customizer_config.batch.micro_batch_size
    epochs = customizer_config.schedule.epochs
    num_prompts = grpo_hp.num_prompts_per_step or max(batch_size // max(grpo_hp.num_generations_per_prompt, 1), 1)

    steps_per_epoch = max((train_samples + num_prompts - 1) // max(num_prompts, 1), 1)
    total_steps = steps_per_epoch * epochs
    user_max_steps = customizer_config.schedule.max_steps
    max_steps = min(user_max_steps, total_steps) if user_max_steps and user_max_steps > 0 else total_steps

    val_check_interval = compute_val_check_interval(
        steps_per_epoch=steps_per_epoch,
        max_steps=max_steps,
        val_check_interval=customizer_config.schedule.val_check_interval,
    )
    val_period = val_check_interval

    cfg["grpo"] = {
        "num_prompts_per_step": num_prompts,
        "num_generations_per_prompt": grpo_hp.num_generations_per_prompt,
        "num_val_generations_per_prompt": grpo_hp.num_val_generations_per_prompt,
        "max_rollout_turns": grpo_hp.max_rollout_turns,
        "max_num_epochs": epochs,
        "max_num_steps": max_steps,
        "normalize_rewards": grpo_hp.normalize_rewards,
        "use_leave_one_out_baseline": True,
        "val_period": val_period,
        "val_start_at": -1,
        "val_at_start": False,
        "val_at_end": customizer_config.schedule.val_at_end,
        "overlong_filtering": False,
        "max_val_samples": val_samples if val_samples else None,
        "val_batch_size": val_samples if val_samples else num_prompts,
        "seed": customizer_config.seed,
        "use_dynamic_sampling": False,
        "batch_multiplier": 1,
        "reward_shaping": {"enabled": False},
        "reward_scaling": {"enabled": False},
        "async_grpo": {"enabled": False, "max_trajectory_age_steps": 1},
    }

    cfg["loss_fn"] = {
        "reference_policy_kl_penalty": grpo_hp.ref_policy_kl_penalty,
        "reference_policy_kl_type": "k3",
        "ratio_clip_min": grpo_hp.ratio_clip_min,
        "ratio_clip_max": grpo_hp.ratio_clip_max,
        "use_on_policy_kl_approximation": True,
        "use_importance_sampling_correction": True,
        "sequence_level_importance_ratios": False,
        "token_level_loss": True,
    }

    cfg["checkpointing"] = {
        "enabled": True,
        "checkpoint_dir": str(workspace_dir / "checkpoints"),
        "metric_name": "val:total_reward/mean",
        "higher_is_better": True,
        "keep_top_k": customizer_config.schedule.keep_top_k,
        "save_period": val_period,
        "checkpoint_must_save_by": None,
        "save_optimizer": True,
    }

    model_path = customizer_config.model.path
    precision = _adapt_precision(customizer_config.model.precision)
    parallelism = customizer_config.parallelism
    chat_template = resolve_chat_template(
        model_path=model_path,
        model_name=customizer_config.model.name,
        user_template=customizer_config.model.chat_template,
        trust_remote_code=customizer_config.model.trust_remote_code,
    )

    cfg["policy"] = {
        "model_name": model_path,
        "tokenizer": {
            "name": model_path,
            "chat_template": chat_template,
            "chat_template_kwargs": None,
        },
        "train_global_batch_size": batch_size,
        "train_micro_batch_size": micro_batch_size,
        "generation_batch_size": micro_batch_size * 4,
        "logprob_batch_size": micro_batch_size,
        "max_total_sequence_length": customizer_config.model.max_seq_length,
        "precision": precision,
        "logprob_chunk_size": 2048,
        "offload_optimizer_for_logprob": False,
        "max_grad_norm": grpo_hp.max_grad_norm,
        "dtensor_cfg": {
            "_v2": True,
            "enabled": True,
            "cpu_offload": False,
            "sequence_parallel": parallelism.sequence_parallel,
            "activation_checkpointing": parallelism.activation_checkpointing,
            "tensor_parallel_size": parallelism.tensor_parallel_size,
            "context_parallel_size": parallelism.context_parallel_size,
            "custom_parallel_plan": None,
            "env_vars": {"PYTORCH_CUDA_ALLOC_CONF": ""},
        },
        "megatron_cfg": _megatron_cfg_disabled(precision, grpo_hp.max_grad_norm),
        "optimizer": _build_optimizer_config(customizer_config),
        "scheduler": _build_scheduler_config(customizer_config, max_steps),
        "generation": {
            "port_range_low": 3000,
            "port_range_high": 4999,
            "backend": "vllm",
            "max_new_tokens": customizer_config.model.max_seq_length,
            "temperature": 1.0,
            "top_p": 1.0,
            "vllm_cfg": {
                "async_engine": True,
                "precision": precision,
                "tensor_parallel_size": min(parallelism.tensor_parallel_size, parallelism.num_gpus_per_node),
                "pipeline_parallel_size": 1,
                "gpu_memory_utilization": 0.5,
                "max_model_len": customizer_config.model.max_seq_length,
                "enforce_eager": True,
                "expose_http_server": True,
            },
            "colocated": {"enabled": True, "resources": {"gpus_per_node": None, "num_nodes": None}},
        },
        "sequence_packing": {"enabled": False},
        "dynamic_batching": {"enabled": False},
    }

    cfg["data"] = {
        "max_input_seq_length": customizer_config.model.max_seq_length,
        "shuffle": False,
        "num_workers": 1,
        "use_multiple_dataloader": False,
        "train": {"data_path": str(train_path)},
        "validation": {"data_path": str(val_path)} if val_samples else None,
        "default": {
            "dataset_name": "NemoGymDataset",
            "env_name": "nemo_gym",
            "processor": "nemo_gym_data_processor",
        },
    }

    cfg["env"] = _build_nemo_gym_env_config(customizer_config, job_ctx)
    cfg["logger"] = _build_logger_config(customizer_config, job_ctx, workspace_dir)
    cfg["cluster"] = {
        "gpus_per_node": parallelism.num_gpus_per_node,
        "num_nodes": parallelism.num_nodes,
    }

    logger.info(
        "Compiled GRPO config: train_samples=%d, val_samples=%d, sandboxed=%s",
        train_samples,
        val_samples,
        customizer_config.gym.sandboxed if customizer_config.gym else False,
    )
    return cfg
