# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TrainingStepConfig → NeMo RL YAML for GRPO + NeMo Gym."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from nmp.customization_common.service.constants import (
    DEFAULT_ENVIRONMENT_PATH,
    SANDBOX_DATASET_PATH,
    SANDBOX_ENVIRONMENT_PATH,
    SANDBOX_WORK_PATH,
)
from nmp.customization_common.service.context import NMPJobContext
from nmp.rl.app.constants import NMP_JOB_STORAGE_PVC_ENVVAR
from nmp.rl.app.jobs.training.schemas import GRPOConfig, TrainingStepConfig
from nmp.rl.entities.values import FinetuningType
from nmp.rl.tasks.training.backends.nemo_rl.dpo_config import (
    _adapt_precision,
    _build_logger_config,
    _build_optimizer_config,
    _build_scheduler_config,
    _build_tokenizer_config,
    _megatron_cfg_disabled,
)
from nmp.rl.tasks.training.backends.nemo_rl.sandbox_config import (
    NemoGymSandboxedConfig,
    SandboxConfig,
    SandboxNetworkPolicy,
    assemble_master_egress_allow,
    build_sandbox_mounts,
    resolve_job_storage_pvc_claim,
)
from nmp.rl.tasks.training.chat_templates import resolve_chat_template
from nmp.rl.tasks.training.datasets.preparation import compute_val_check_interval, prepare_dataset
from nmp.rl.tasks.training.datasets.validation import DatasetValidator

logger = logging.getLogger(__name__)


def _build_lora_cfg(customizer_config: TrainingStepConfig) -> dict[str, Any]:
    """Map TrainingStepConfig LoRA settings onto NeMo-RL DTensor lora_cfg."""
    enabled = customizer_config.training.finetuning_type == FinetuningType.LORA
    lora = customizer_config.training.lora
    tp = customizer_config.parallelism.tensor_parallel_size
    use_triton = True if lora is None else lora.use_triton
    if tp > 1:
        use_triton = False
    target_modules = list(lora.target_modules) if lora and lora.target_modules else []
    exclude_modules = list(lora.exclude_modules) if lora and lora.exclude_modules else []
    return {
        "enabled": enabled,
        "target_modules": target_modules,
        "exclude_modules": exclude_modules,
        # Automodel's ModuleMatcher rejects match_all_linear alongside either list, and falls
        # through to "every linear layer except the excluded ones" when it is off.
        "match_all_linear": not (target_modules or exclude_modules),
        "dim": lora.rank if lora else 16,
        "alpha": lora.alpha if lora else 32,
        "dropout": lora.dropout if lora else 0.0,
        "dropout_position": "post",
        "lora_A_init": "xavier",
        "use_triton": use_triton,
    }


def _build_dtensor_cfg(
    customizer_config: TrainingStepConfig,
    grpo_hp: GRPOConfig,
    lora_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Map parallelism and backend settings onto NeMo-RL's policy.dtensor_cfg.

    LoRA, expert parallelism and ``automodel_kwargs`` are implemented only by
    ``DTensorPolicyWorkerV2``, so requesting any of them sets ``_v2``.
    """
    parallelism = customizer_config.parallelism
    expert_parallel_size = parallelism.expert_parallel_size
    automodel_kwargs = grpo_hp.automodel_kwargs
    needs_v2 = lora_cfg["enabled"] or expert_parallel_size > 1 or bool(automodel_kwargs)

    dtensor_cfg: dict[str, Any] = {
        "enabled": True,
        "cpu_offload": False,
        "sequence_parallel": parallelism.sequence_parallel,
        "activation_checkpointing": parallelism.activation_checkpointing,
        "tensor_parallel_size": parallelism.tensor_parallel_size,
        "context_parallel_size": parallelism.context_parallel_size,
        "custom_parallel_plan": None,
        "env_vars": {"PYTORCH_CUDA_ALLOC_CONF": ""},
    }
    # Optional keys stay absent when unset so NeMo-RL's defaults apply.
    if expert_parallel_size > 1:
        dtensor_cfg["expert_parallel_size"] = expert_parallel_size
    if automodel_kwargs:
        dtensor_cfg["automodel_kwargs"] = dict(automodel_kwargs)
    if lora_cfg["enabled"]:
        dtensor_cfg["lora_cfg"] = lora_cfg
    if needs_v2:
        dtensor_cfg["_v2"] = True
    return dtensor_cfg


def _count_jsonl_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _read_manifest_config_paths(environment_path: str | None) -> list[str]:
    """Read ``config_paths`` from the environment package manifest on job storage."""
    if not environment_path:
        return []
    manifest_path = Path(environment_path) / "nemo-environment.yaml"
    if not manifest_path.is_file():
        logger.warning("No nemo-environment.yaml at %s; Gym will start with no config_paths", environment_path)
        return []
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest.get("config_paths"):
        return []
    return list(manifest["config_paths"])


def _resolve_gym_paths(
    customizer_config: TrainingStepConfig,
    workspace_dir: Path,
) -> tuple[Path, Path, int, int]:
    """Return train/val paths and sample counts for Gym JSONL.

    The returned paths feed ``cfg["data"]``, which NeMo-RL opens in the *training
    master* (``setup_response_data`` -> ``NemoGymDataset``). They must therefore stay
    job-storage paths even in sandboxed mode — the ``/job/...`` mounts exist only
    inside the Gym sandbox, and the master would not be able to read them.
    """
    gym = customizer_config.gym
    if gym and gym.sandboxed and gym.sandbox_dataset_path:
        pvc_train = Path(customizer_config.dataset.path) / "training.jsonl"
        pvc_val = Path(customizer_config.dataset.path) / "validation.jsonl"
        validator = DatasetValidator(training_type=customizer_config.training.training_type)
        validator.validate_dataset(str(pvc_train))
        if pvc_val.is_file():
            validator.validate_dataset(str(pvc_val))
        return pvc_train, pvc_val, _count_jsonl_rows(pvc_train), _count_jsonl_rows(pvc_val)

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
    nemo_gym: dict[str, Any] = {
        "port_range_low": 5000,
        "port_range_high": 5999,
    }
    env_block: dict[str, Any] = {
        "should_use_nemo_gym": True,
        "should_log_nemo_gym_responses": False,
        "should_mask_flagged_samples": True,
        "nemo_gym": nemo_gym,
    }

    # config_paths tells Gym which server/agent YAMLs to load out of the environment
    # package. The manifest is always read from the job-storage copy (the training master can
    # reach it in both modes), but it stores the paths RELATIVE to the package root, and Gym
    # resolves relative paths against its own CWD — the runtime image's WORKDIR, which is
    # neither the job-storage copy nor the sandbox mount. Left relative, Gym dies with
    # FileNotFoundError on e.g. /opt/nemo-rl/configs/<agent>.yaml. So anchor them to wherever
    # the package is actually visible to the process that loads them: the sandbox mount in
    # mode B, the job-storage copy in mode A. Absolute entries are passed through untouched.
    package_root = SANDBOX_ENVIRONMENT_PATH if sandboxed else (gym.environment_path or DEFAULT_ENVIRONMENT_PATH)
    config_paths = [
        path if Path(path).is_absolute() else str(Path(package_root) / path)
        for path in _read_manifest_config_paths(gym.environment_path)
    ]
    if config_paths:
        nemo_gym["config_paths"] = config_paths

    if sandboxed:
        # Fail loudly rather than substituting a default here: a wrong sandbox
        # image surfaces as an opaque client-side ReadTimeout once the sandbox pod
        # ErrImagePulls, which is expensive to diagnose from the training log.
        runtime_image = gym.gym_runtime_image
        if not runtime_image:
            raise ValueError(
                "Sandboxed GRPO requires a Gym runtime image; gym.gym_runtime_image is unset. "
                "Set platformConfig.rl.gym_runtime_image, or leave it unset to inherit the "
                "nmp-rl-training image."
            )
        pvc_claim = resolve_job_storage_pvc_claim()
        if not pvc_claim:
            raise ValueError(
                "Sandboxed GRPO requires the job-storage PVC claim name so the Gym sandbox "
                f"can mount the environment and dataset; {NMP_JOB_STORAGE_PVC_ENVVAR} is unset. "
                "Set NMP_RL_JOB_STORAGE_PVC_CLAIM on the rl service."
            )
        mounts = build_sandbox_mounts(
            pvc_claim=pvc_claim,
            workspace=job_ctx.workspace,
            job_id=job_ctx.job_id,
            storage_root=job_ctx.storage_path,
            environment_path=gym.environment_path or DEFAULT_ENVIRONMENT_PATH,
            dataset_path=customizer_config.dataset.path,
        )

        sandbox = SandboxConfig(
            image=runtime_image,
            env_mount_path=SANDBOX_ENVIRONMENT_PATH,
            dataset_mount_path=SANDBOX_DATASET_PATH,
            # Sandbox mount is /job/work; ephemeral host work prefers /scratch or /tmp.
            work_mount_path=SANDBOX_WORK_PATH,
            allow_internet=gym.allow_internet,
            network_policy=SandboxNetworkPolicy(
                # Defaults until the training master resolves live vLLM/broker endpoints.
                egress_allow=assemble_master_egress_allow(),
                public_dns_allow=tuple(gym.public_dns_allow),
            ),
            # Only emitted when the operator declared it, so an unset value leaves
            # NeMo-RL's own default in place rather than this compiler asserting one.
            host_provider_options=(
                {"connection": {"protocol": gym.sandbox_server_protocol}} if gym.sandbox_server_protocol else {}
            ),
            # Same rule: unset leaves the OpenSandbox server's default in place.
            resources=gym.sandbox_resources or None,
            environment_pvc_claim=mounts.environment_pvc_claim,
            environment_sub_path=mounts.environment_sub_path,
            dataset_pvc_claim=mounts.dataset_pvc_claim,
            dataset_sub_path=mounts.dataset_sub_path,
            workspace_pvc_claim=mounts.workspace_pvc_claim,
            workspace_sub_path=mounts.workspace_sub_path,
        )

        # Assigned after construction rather than passed in: these three carry non-null
        # defaults mirroring NeMo-RL's, so handing them None would fail validation and
        # asserting one here would override upstream on every job.
        if gym.sandbox_ttl_s is not None:
            sandbox.ttl_s = gym.sandbox_ttl_s
        if gym.sandbox_rollout_chunk_size is not None:
            sandbox.rollout_chunk_size = gym.sandbox_rollout_chunk_size
        if gym.sandbox_rollout_max_in_flight is not None:
            sandbox.rollout_max_in_flight = gym.sandbox_rollout_max_in_flight

        sandbox_cfg = NemoGymSandboxedConfig(
            sandboxed=True,
            host_provider="opensandbox",
            environment_path=gym.sandbox_environment_path or SANDBOX_ENVIRONMENT_PATH,
            job_id=job_ctx.job_id,
            sandbox=sandbox,
        )
        # mode="json", not "python": this dict is written straight to YAML with yaml.dump
        # and read back by OmegaConf's SafeLoader. "python" mode keeps
        # network_policy.public_dns_allow a tuple, which yaml.dump emits as
        # !!python/tuple and that loader refuses -- the job then dies at driver start,
        # long after compile reported success. "json" mode lowers tuples to lists, and
        # NeMo-RL's own tuple[str, ...] field coerces them back on validation.
        nemo_gym.update(sandbox_cfg.model_dump(mode="json", exclude_none=True))
    else:
        nemo_gym["environment_path"] = gym.environment_path

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
    # NeMo-RL asserts a validation dataset exists whenever any of val_period /
    # val_at_start / val_at_end is set. A Gym dataset fileset only has to carry
    # training.jsonl, so turn validation off entirely rather than assert in setup().
    has_validation = bool(val_samples)
    val_period = val_check_interval if has_validation else 0
    val_at_start = customizer_config.schedule.val_at_start and has_validation
    val_at_end = customizer_config.schedule.val_at_end and has_validation
    if not has_validation and (customizer_config.schedule.val_at_end or customizer_config.schedule.val_at_start):
        logger.warning(
            "No validation.jsonl in the Gym dataset; disabling validation and best-checkpoint selection for this run."
        )

    cfg["grpo"] = {
        "num_prompts_per_step": num_prompts,
        "num_generations_per_prompt": grpo_hp.num_generations_per_prompt,
        "max_rollout_turns": grpo_hp.max_rollout_turns,
        "max_num_epochs": epochs,
        "max_num_steps": max_steps,
        # Not NeMo-RL fields. They ride along as extras -- GRPOConfig allows them -- because
        # this dict is the only channel from the compiled job config to the driver, which is
        # where our own logger is built. Read back with getattr, never attribute access: a
        # config compiled elsewhere simply omits them. Mirrors dpo_config.
        "steps_per_epoch": steps_per_epoch,
        "progress_time_series_metrics": customizer_config.schedule.progress_reporting.time_series_metrics,
        "progress_min_report_interval_seconds": customizer_config.schedule.progress_reporting.min_report_interval_seconds,
        # The advantage estimator reads these two from `grpo.adv_estimator`, not from
        # `grpo` itself. NeMo-RL's own YAML recipes set the top-level pair and point
        # adv_estimator at them with OmegaConf interpolation
        # (`normalize_rewards: ${grpo.normalize_rewards}`), so both spellings appear
        # in a resolved config. This dict is built in Python with no interpolation, so
        # writing only the top-level pair left AdvEstimatorConfig on its own defaults
        # and `normalize_rewards: false` did nothing. Both are written here so the
        # config matches a resolved recipe either way.
        "normalize_rewards": grpo_hp.normalize_rewards,
        "use_leave_one_out_baseline": grpo_hp.use_leave_one_out_baseline,
        "adv_estimator": {
            "name": "grpo",
            "normalize_rewards": grpo_hp.normalize_rewards,
            "use_leave_one_out_baseline": grpo_hp.use_leave_one_out_baseline,
        },
        # Bounds on the normalized advantages. None means unbounded on that side, which
        # is NeMo-RL's default and standard GRPO.
        "advantage_clip_low": grpo_hp.advantage_clip_low,
        "advantage_clip_high": grpo_hp.advantage_clip_high,
        "val_period": val_period,
        "val_start_at": -1,
        "val_at_start": val_at_start,
        "val_at_end": val_at_end,
        "overlong_filtering": grpo_hp.overlong_filtering,
        "max_val_samples": val_samples if val_samples else None,
        "val_batch_size": val_samples if val_samples else num_prompts,
        "seed": customizer_config.seed,
        # These are the transforms NeMo-RL applies between the rollout's reward and the one
        # the loss sees. All default off, so an unstated job still has grpo.py's `reward`
        # equal to the NeMo-Gym aggregator's `total_reward/mean`; enabling any of them
        # separates the two, which is why nemo_rl_logger's GRPO series carries both.
        "use_dynamic_sampling": grpo_hp.use_dynamic_sampling,
        "dynamic_sampling_max_gen_batches": grpo_hp.dynamic_sampling_max_gen_batches,
        "batch_multiplier": grpo_hp.batch_multiplier,
        # `enabled` is what NeMo-RL branches on; the penalty fields are only read when it is
        # true, so an absent reward_shaping compiles to the same disabled block as before.
        "reward_shaping": (
            {"enabled": True, **grpo_hp.reward_shaping} if grpo_hp.reward_shaping else {"enabled": False}
        ),
        "reward_scaling": {"enabled": False},
        "async_grpo": {"enabled": False, "max_trajectory_age_steps": 1},
    }

    cfg["loss_fn"] = {
        "reference_policy_kl_penalty": grpo_hp.ref_policy_kl_penalty,
        "reference_policy_kl_type": "k3",
        "ratio_clip_min": grpo_hp.ratio_clip_min,
        "ratio_clip_max": grpo_hp.ratio_clip_max,
        # None leaves dual clipping off, which is NeMo-RL's default. The loss asserts
        # the value exceeds 1 when it is set; the job schema rejects it earlier.
        "ratio_clip_c": grpo_hp.ratio_clip_c,
        "use_on_policy_kl_approximation": grpo_hp.use_on_policy_kl_approximation,
        "use_importance_sampling_correction": grpo_hp.use_importance_sampling_correction,
        "sequence_level_importance_ratios": False,
        "token_level_loss": True,
        # Truncated importance sampling. ClippedPGLossFn gates the whole block on the type
        # being non-null, so leaving these three absent is how TIS stays off -- and
        # sequence_level_importance_ratios is already False above, which seq-mask-tis requires.
        "truncated_importance_sampling_type": grpo_hp.truncated_importance_sampling_type,
        "truncated_importance_sampling_ratio": grpo_hp.truncated_importance_sampling_ratio,
        "truncated_importance_sampling_ratio_min": grpo_hp.truncated_importance_sampling_ratio_min,
    }

    cfg["checkpointing"] = {
        "enabled": True,
        "checkpoint_dir": str(workspace_dir / "checkpoints"),
        # Ranking by a val metric only works when validation runs; without it,
        # metric_name=None makes NeMo-RL fall back to latest-checkpoint selection.
        "metric_name": "val:total_reward/mean" if has_validation else None,
        "higher_is_better": True,
        "keep_top_k": customizer_config.schedule.keep_top_k,
        "save_period": val_period or val_check_interval,
        "checkpoint_must_save_by": None,
        "save_optimizer": True,
    }

    model_path = customizer_config.model.path
    precision = _adapt_precision(customizer_config.model.precision)
    parallelism = customizer_config.parallelism
    lora_cfg = _build_lora_cfg(customizer_config)
    chat_template = resolve_chat_template(
        model_path=model_path,
        model_name=customizer_config.model.name,
        user_template=customizer_config.model.chat_template,
        trust_remote_code=customizer_config.model.trust_remote_code,
    )

    cfg["policy"] = {
        "model_name": model_path,
        "tokenizer": _build_tokenizer_config(model_path, chat_template),
        "train_global_batch_size": batch_size,
        "train_micro_batch_size": micro_batch_size,
        "generation_batch_size": micro_batch_size * 4,
        "logprob_batch_size": micro_batch_size,
        "max_total_sequence_length": customizer_config.model.max_seq_length,
        "precision": precision,
        "logprob_chunk_size": 2048,
        "offload_optimizer_for_logprob": False,
        "max_grad_norm": grpo_hp.max_grad_norm,
        "dtensor_cfg": _build_dtensor_cfg(customizer_config, grpo_hp, lora_cfg),
        "megatron_cfg": _megatron_cfg_disabled(precision, grpo_hp.max_grad_norm),
        "optimizer": _build_optimizer_config(customizer_config),
        "scheduler": _build_scheduler_config(customizer_config, max_steps),
        "generation": {
            "port_range_low": 3000,
            "port_range_high": 4999,
            "backend": "vllm",
            # Defaulting to the full context matches NeMo-RL's own recipes: it means "run
            # until the context is exhausted", and the vLLM worker clamps it to what the
            # prompt leaves. An explicit value bounds response length instead.
            "max_new_tokens": grpo_hp.max_new_tokens or customizer_config.model.max_seq_length,
            "temperature": grpo_hp.temperature,
            # top_p stays neutral -- 1.0 is its disabled value, and the job schema has no
            # knob for it. top_k defaults to None, which is also disabled: sample from the
            # whole distribution.
            "top_p": 1.0,
            "top_k": grpo_hp.top_k,
            "stop_token_ids": None,
            "stop_strings": None,
            "vllm_cfg": {
                "async_engine": True,
                "precision": precision,
                "kv_cache_dtype": "auto",
                # Generation shards independently of training: the rollout engine may need
                # several GPUs to hold inference weights the policy shards differently.
                "tensor_parallel_size": (
                    grpo_hp.vllm_tensor_parallel_size
                    or min(parallelism.tensor_parallel_size, parallelism.num_gpus_per_node)
                ),
                "pipeline_parallel_size": 1,
                "expert_parallel_size": 1,
                "gpu_memory_utilization": grpo_hp.vllm_gpu_memory_utilization,
                "max_model_len": customizer_config.model.max_seq_length,
                "enforce_eager": True,
                "expose_http_server": True,
            },
            "colocated": {"enabled": True, "resources": {"gpus_per_node": None, "num_nodes": None}},
        },
        "sequence_packing": {"enabled": False},
        "dynamic_batching": {"enabled": False},
        "make_sequence_length_divisible_by": parallelism.tensor_parallel_size,
    }

    # NeMo-RL forwards this to the training model as HF config kwargs and to vLLM as
    # `hf_overrides`, so one setting covers both.
    if grpo_hp.router_aux_loss_coef is not None:
        cfg["policy"]["hf_config_overrides"] = {"router_aux_loss_coef": float(grpo_hp.router_aux_loss_coef)}

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
