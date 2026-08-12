# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GRPO training driver (ray run entry point) for NeMo Gym environments."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, cast

from nemo_rl.algorithms.grpo import MasterConfig, _should_use_nemo_gym, grpo_train, setup
from nemo_rl.algorithms.utils import get_tokenizer
from nemo_rl.data.utils import setup_response_data
from nemo_rl.distributed.virtual_cluster import init_ray
from nemo_rl.environments.nemo_gym import setup_nemo_gym_config
from nemo_rl.models.generation import configure_generation_config
from nemo_rl.utils.config import load_config, parse_hydra_overrides
from nemo_rl.utils.logger import get_next_experiment_dir
from nmp.customization_common.service.context import NMPJobContext
from nmp.rl.tasks.training.backends.nemo_rl.nemo_rl_logger import NemoRLLogger
from nmp.rl.tasks.training.backends.nemo_rl.sandbox_config import assemble_master_egress_allow
from omegaconf import OmegaConf

logger = logging.getLogger(__name__)


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Run GRPO training with NeMo Gym configuration")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config file")
    parser.add_argument("--id", type=str, help="Customization ID")
    parser.add_argument("--output-model", type=str, help="Output Model")
    return parser.parse_known_args()


def _maybe_bootstrap_environment(config: MasterConfig) -> None:
    """Install or refresh the environment FileSet before GRPO setup.

    Sandboxed jobs only need live egress endpoints (vLLM + broker). Colocated
    jobs validate the package on the PVC and offline-install wheels when needed.
    """
    nemo_gym = config.env.get("nemo_gym") if isinstance(config.env, dict) else None
    if not isinstance(nemo_gym, dict):
        return

    env_path = nemo_gym.get("environment_path")
    sandboxed = bool(nemo_gym.get("sandboxed"))
    if sandboxed:
        sandbox = nemo_gym.get("sandbox")
        if isinstance(sandbox, dict):
            policy = sandbox.setdefault("network_policy", {})
            policy["egress_allow"] = [{"host": rule.host, "port": rule.port} for rule in assemble_master_egress_allow()]
            logger.info("Applied master egress allowlist: %s", policy["egress_allow"])
        return

    if not env_path:
        return
    root = Path(str(env_path))
    if not (root / "nemo-environment.yaml").is_file():
        logger.warning("No nemo-environment.yaml at %s; skipping platform bootstrap", root)
        return

    from nmp.rl.tasks.environment.bootstrap import bootstrap_environment_package

    # host_work_path is only set in sandboxed mode, which returns above — so in practice
    # this is None and bootstrap picks a temp dir outside the package. Never fall back to
    # a path inside `root`: the package validator rejects any *.jsonl under it, and
    # site-packages ships plenty, which would break resume and rerun on the same PVC.
    host_work = nemo_gym.get("host_work_path")
    work_venv = Path(str(host_work)) / "venv" if host_work else None
    result = bootstrap_environment_package(root, work_venv=work_venv, install_wheels=True)
    logger.info(
        "Bootstrapped environment format=%s image_config_root=%s venv=%s",
        result.manifest.format,
        result.image_config_root,
        result.work_venv,
    )


def main() -> None:
    args, overrides = parse_args()

    cfg = load_config(args.config)
    print(f"Loaded configuration from: {args.config}")

    if overrides:
        print(f"Overrides: {overrides}")
        cfg = parse_hydra_overrides(cfg, overrides)

    config = MasterConfig(**cast(dict[str, Any], OmegaConf.to_container(cfg, resolve=True)))
    print("Applied CLI overrides")
    print(f"Config sections loaded: {sorted(type(config).model_fields)}")

    config.logger["log_dir"] = get_next_experiment_dir(config.logger["log_dir"])
    print(f"Using log directory: {config.logger['log_dir']}")
    if config.checkpointing["enabled"]:
        print(f"Using checkpoint directory: {config.checkpointing['checkpoint_dir']}")

    _maybe_bootstrap_environment(config)

    tokenizer = get_tokenizer(config.policy["tokenizer"])
    assert config.policy["generation"] is not None, "A generation config is required for GRPO"
    config.policy["generation"] = configure_generation_config(
        config.policy["generation"],
        tokenizer,
        has_refit_draft_weights=False,
        trains_mtp=False,
    )
    setup_nemo_gym_config(config, tokenizer)
    assert _should_use_nemo_gym(config)

    train_dataset, val_dataset = setup_response_data(tokenizer, config.data, env_configs=None)

    if val_dataset is not None:
        config.grpo.max_val_samples = len(val_dataset)
        config.grpo.val_batch_size = config.grpo.max_val_samples

    init_ray()

    (
        policy,
        policy_generation,
        nemo_gym,
        cluster,
        dataloader,
        val_dataloader,
        loss_fn,
        logger_inst,
        checkpointer,
        grpo_state,
        master_config,
        _teacher_worker_groups,
        _alias_to_group_alias,
    ) = setup(config, tokenizer, train_dataset, val_dataset)

    task_to_env = {"nemo_gym": nemo_gym}
    val_task_to_env = task_to_env

    job_ctx = NMPJobContext.from_env()
    print(f"Job context loaded (job_id={job_ctx.job_id})")
    if job_ctx.jobs_url:
        customizer_logger = NemoRLLogger.for_schedule(
            job_ctx=job_ctx,
            max_steps=config.grpo.max_num_steps,
            num_epochs=config.grpo.max_num_epochs,
            val_period=config.grpo.val_period,
        )
        if hasattr(logger_inst, "loggers"):
            logger_inst.loggers.append(customizer_logger)

    logger_inst.log_hyperparams(config.model_dump())

    try:
        grpo_train(
            policy,
            policy_generation,
            dataloader,
            val_dataloader,
            tokenizer,
            loss_fn,
            task_to_env,
            val_task_to_env,
            logger_inst,
            checkpointer,
            grpo_state,
            master_config,
        )
    finally:
        for task_name, env in task_to_env.items():
            try:
                import ray

                ray.get(env.shutdown.remote(), timeout=120)
            except Exception as exc:
                logger.warning("Error shutting down environment %s: %s", task_name, exc)


if __name__ == "__main__":
    main()
