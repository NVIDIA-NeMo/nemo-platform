# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the pure config-builder helpers in dpo_config.

These cover the optimizer/scheduler/precision/data/logger builders and the inert
Megatron block — i.e. everything except ``compile_dpo_config`` itself, which needs
a real on-disk dataset to prepare and validate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nmp.customization_common.service.context import NMPJobContext
from nmp.rl.app.jobs.training.schemas import (
    DPOConfig,
    ModelConfig,
    OptimizerType,
    TrainingStepConfig,
    TrainingType,
)
from nmp.rl.tasks.training.backends.nemo_rl import dpo_config
from nmp.rl.tasks.training.backends.nemo_rl.dpo_config import (
    _adapt_precision,
    _build_data_config,
    _build_logger_config,
    _build_optimizer_config,
    _build_scheduler_config,
    _megatron_cfg_disabled,
)
from nmp.rl.tasks.training.datasets.preparation import PreparedDataset


def _make_step_config(
    *,
    optimizer: TrainingStepConfig.OptimizerConfig | None = None,
    schedule: TrainingStepConfig.ScheduleConfig | None = None,
    parallelism: TrainingStepConfig.ParallelismConfig | None = None,
    max_seq_length: int = 1024,
) -> TrainingStepConfig:
    return TrainingStepConfig(
        model=ModelConfig(path="/model", max_seq_length=max_seq_length),
        dataset=TrainingStepConfig.DatasetConfig(path="/data"),
        training=TrainingStepConfig.TrainingConfig(training_type=TrainingType.DPO, dpo=DPOConfig()),
        schedule=schedule or TrainingStepConfig.ScheduleConfig(),
        batch=TrainingStepConfig.BatchConfig(),
        optimizer=optimizer or TrainingStepConfig.OptimizerConfig(),
        parallelism=parallelism or TrainingStepConfig.ParallelismConfig(),
        output_model="out",
    )


def _job_ctx(tmp_path: Path) -> NMPJobContext:
    return NMPJobContext(
        workspace="default",
        job_id="rl-test",
        attempt_id="attempt-1",
        step="dpo-training",
        task="task-1",
        jobs_url=None,
        files_url=None,
        storage_path=tmp_path,
        config_path=tmp_path / "config.json",
    )


# --------------------------------------------------------------------------- #
# _adapt_precision
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,expected",
    [
        ("bf16", "bfloat16"),
        ("bf16-mixed", "bfloat16"),
        ("fp16", "float16"),
        ("fp32", "float32"),
        (None, "bfloat16"),
        ("nonsense", "bfloat16"),  # unknown → safe default
    ],
)
def test_adapt_precision(value: str | None, expected: str) -> None:
    assert _adapt_precision(value) == expected


# --------------------------------------------------------------------------- #
# _build_optimizer_config
# --------------------------------------------------------------------------- #


def test_optimizer_config_adamw_default() -> None:
    opt = _build_optimizer_config(_make_step_config())  # optimizer_type None → AdamW
    assert opt["name"] == "torch.optim.AdamW"


@pytest.mark.parametrize(
    "opt_type",
    [OptimizerType.ADAM_WITH_COSINE_ANNEALING, OptimizerType.ADAM_WITH_FLAT_LR],
)
def test_optimizer_config_adam_variants(opt_type: OptimizerType) -> None:
    cfg = _make_step_config(optimizer=TrainingStepConfig.OptimizerConfig(optimizer_type=opt_type))
    assert _build_optimizer_config(cfg)["name"] == "torch.optim.Adam"


def test_optimizer_config_passes_through_kwargs() -> None:
    optimizer = TrainingStepConfig.OptimizerConfig(
        learning_rate=2e-5, weight_decay=0.05, beta1=0.8, beta2=0.95, eps=3e-7
    )
    kwargs = _build_optimizer_config(_make_step_config(optimizer=optimizer))["kwargs"]
    assert kwargs["lr"] == 2e-5
    assert kwargs["weight_decay"] == 0.05
    assert kwargs["betas"] == [0.8, 0.95]
    assert kwargs["eps"] == 3e-7  # the configurable knob actually flows through


# --------------------------------------------------------------------------- #
# _build_scheduler_config
# --------------------------------------------------------------------------- #


def test_scheduler_cosine_is_warmup_then_decay_chain() -> None:
    cfg = _make_step_config(
        optimizer=TrainingStepConfig.OptimizerConfig(
            optimizer_type=OptimizerType.ADAMW_WITH_COSINE_ANNEALING, warmup_steps=10
        )
    )
    sched = _build_scheduler_config(cfg, num_steps=100)
    assert isinstance(sched, list)
    assert sched[0]["name"] == "torch.optim.lr_scheduler.LinearLR"
    assert sched[1]["name"] == "torch.optim.lr_scheduler.CosineAnnealingLR"
    assert sched[2]["milestones"] == [10]


def test_scheduler_flat_is_constant_lr() -> None:
    cfg = _make_step_config(
        optimizer=TrainingStepConfig.OptimizerConfig(optimizer_type=OptimizerType.ADAMW_WITH_FLAT_LR)
    )
    sched = _build_scheduler_config(cfg, num_steps=100)
    assert isinstance(sched, dict)
    assert sched["name"] == "torch.optim.lr_scheduler.ConstantLR"


# --------------------------------------------------------------------------- #
# _megatron_cfg_disabled (inert block, must still be fully populated)
# --------------------------------------------------------------------------- #


def test_megatron_cfg_is_inert_but_complete() -> None:
    mc = _megatron_cfg_disabled(precision="bfloat16", max_grad_norm=2.5)
    assert mc["enabled"] is False
    assert mc["pipeline_dtype"] == "bfloat16"  # tracks policy.precision
    assert mc["optimizer"]["clip_grad"] == 2.5  # tracks policy.max_grad_norm
    # All required sub-blocks present so NeMo-RL's schema validates.
    for key in ("peft", "optimizer", "scheduler", "distributed_data_parallel_config", "fp8_cfg"):
        assert key in mc
    assert mc["fp8_cfg"]["enabled"] is False
    assert mc["peft"]["enabled"] is False


# --------------------------------------------------------------------------- #
# _build_data_config
# --------------------------------------------------------------------------- #


def test_data_config_binary_preference(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dpo_config, "detect_dpo_schema_name", lambda _path: "BinaryPreferenceDataset")
    prepared = PreparedDataset(
        merged_dir=tmp_path,
        train_file=tmp_path / "training.jsonl",
        validation_file=tmp_path / "validation.jsonl",
        train_samples=10,
        validation_samples=2,
    )
    data = _build_data_config(_make_step_config(max_seq_length=512), prepared)

    assert data["max_input_seq_length"] == 512
    assert data["shuffle"] is False  # deterministic ordering is an intentional override
    for split in ("train", "validation"):
        assert data[split]["dataset_name"] == "BinaryPreferenceDataset"
        assert data[split]["prompt_key"] == "prompt"
        assert data[split]["chosen_key"] == "chosen"
        assert data[split]["rejected_key"] == "rejected"
    assert data["train"]["data_path"] == str(prepared.train_file)


# --------------------------------------------------------------------------- #
# _build_logger_config
# --------------------------------------------------------------------------- #


def test_logger_config_has_all_subsections_when_integrations_disabled(tmp_path: Path) -> None:
    cfg = _build_logger_config(_make_step_config(), _job_ctx(tmp_path), tmp_path)

    assert cfg["wandb_enabled"] is False
    assert cfg["mlflow_enabled"] is False
    assert cfg["monitor_gpus"] is False
    assert cfg["log_dir"].endswith("logs")
    # Every backend subsection is present even when disabled (NeMo-RL expects them).
    for key in ("wandb", "swanlab", "tensorboard", "mlflow", "gpu_monitoring"):
        assert key in cfg
