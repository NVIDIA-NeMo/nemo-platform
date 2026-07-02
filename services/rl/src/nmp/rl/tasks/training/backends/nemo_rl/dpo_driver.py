# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DPO training driver (ray run entry point).

Entry point for DPO (Direct Preference Optimization) training, invoked via
ray run in a distributed environment.

Preference data handling lives in NeMo-RL itself (``setup_preference_data`` plus
the config-driven ``BinaryPreferenceDataset`` / ``PreferenceDataset`` loaders):
the ``data`` config emitted by ``dpo_config.compile_dpo_config`` drives the
built-in loaders, so no custom preprocessor is needed. On top of NeMo-RL's DPO
loop we add the ``NemoRLLogger`` that streams progress back to the NeMo Platform
Jobs service.
"""

import argparse
import logging
from typing import cast

from nemo_rl.algorithms.dpo import MasterConfig, dpo_train, setup
from nemo_rl.algorithms.utils import get_tokenizer
from nemo_rl.data.utils import setup_preference_data
from nemo_rl.distributed.virtual_cluster import init_ray
from nemo_rl.utils.config import load_config, parse_hydra_overrides
from nemo_rl.utils.logger import get_next_experiment_dir
from nmp.customization_common.service.context import NMPJobContext
from nmp.rl.tasks.training.backends.nemo_rl.nemo_rl_logger import NemoRLLogger
from nmp.rl.tasks.training.backends.nemo_rl.preference_datasets import register_preference_datasets
from omegaconf import OmegaConf

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run DPO training with configuration")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config file")
    parser.add_argument("--id", type=str, help="Customization ID")
    parser.add_argument("--output-model", type=str, help="Output Model")

    # Parse known args for the script
    args, overrides = parser.parse_known_args()

    return args, overrides


def main():
    """Main entry point."""
    args, overrides = parse_args()

    cfg = load_config(args.config)
    print(f"Loaded configuration from: {args.config}")

    if overrides:
        print(f"Overrides: {overrides}")
        cfg = parse_hydra_overrides(cfg, overrides)

    config = cast(MasterConfig, OmegaConf.to_container(cfg, resolve=True))
    print("Applied CLI overrides")

    # Log only the top-level config section names. The resolved config carries
    # integration secrets (W&B / MLflow tokens, tracking URIs), so never dump the
    # full structure to stdout.
    print(f"Config sections loaded: {sorted(config.keys())}")

    config["logger"]["log_dir"] = get_next_experiment_dir(config["logger"]["log_dir"])
    print(f"📊 Using log directory: {config['logger']['log_dir']}")
    if config["checkpointing"]["enabled"]:
        print(f"📊 Using checkpoint directory: {config['checkpointing']['checkpoint_dir']}")

    init_ray()

    # setup tokenizer
    tokenizer = get_tokenizer(config["policy"]["tokenizer"])

    # Register our local-file-capable HelpSteer3 / Tulu3 datasets into NeMo-RL's
    # DATASET_REGISTRY before building data. Without this, setup_preference_data
    # resolves those two formats to NeMo-RL's built-in classes, which always
    # download from HuggingFace and ignore the uploaded local files.
    register_preference_datasets()

    # setup data — NeMo-RL builds the datasets from the `data` config (per-split
    # dataset specs). The compiler emits one of BinaryPreferenceDataset /
    # PreferenceDataset / HelpSteer3 / Tulu3Preference per detected schema, each
    # pointing at the prepared local training.jsonl / validation.jsonl.
    dataset, val_dataset = setup_preference_data(tokenizer, config["data"])
    (
        policy,
        cluster,
        train_dataloader,
        val_dataloader,
        loss_fn,
        logger,
        checkpointer,
        dpo_save_state,
        master_config,
    ) = setup(config, tokenizer, dataset, val_dataset)

    # Add NemoRLLogger for progress reporting if Jobs service is configured
    job_ctx = NMPJobContext.from_env()
    # Log only the non-sensitive job id; the full context carries service URLs
    # and identifiers that should not be dumped to stdout.
    print(f"Job context loaded (job_id={job_ctx.job_id})")
    if job_ctx.jobs_url:
        # Extract training parameters for progress reporting
        max_steps = config["dpo"].get("max_num_steps", 0)
        num_epochs = config["dpo"].get("max_num_epochs", 1)
        steps_per_epoch = config["dpo"]["steps_per_epoch"]  # type: ignore - we need to pass this additional parameter to the logger
        log_interval = (config["dpo"]["val_period"] // 10) + 1

        customizer_logger = NemoRLLogger(
            steps_per_epoch=steps_per_epoch,
            job_ctx=job_ctx,
            log_interval=log_interval,
            max_steps=max_steps,
            num_epochs=num_epochs,
        )
        # The setup() logger is a composite with a `.loggers` list; guard in case
        # that internal shape changes.
        if hasattr(logger, "loggers"):
            logger.loggers.append(customizer_logger)
        else:
            print("WARNING: logger has no `.loggers`; NeMo Platform progress reporting disabled.")

    logger.log_hyperparams(config)

    dpo_train(
        policy,
        train_dataloader,
        val_dataloader,
        tokenizer,
        loss_fn,
        master_config,
        logger,
        checkpointer,
        dpo_save_state,
    )


if __name__ == "__main__":
    main()
