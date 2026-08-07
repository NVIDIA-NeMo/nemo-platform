# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GRPO config compilation (sandbox paths + egress)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock  # noqa: F401 — reserved for future SDK mocks

import pytest
from nmp.customization_common.service.context import NMPJobContext
from nmp.rl.app.jobs.training.schemas import (
    GRPOConfig,
    ModelConfig,
    TrainingBackend,
    TrainingStepConfig,
)
from nmp.rl.entities.values import FinetuningType, TrainingType
from nmp.rl.tasks.training.backends.nemo_rl.grpo_config import compile_grpo_config


@pytest.fixture
def job_ctx(tmp_path: Path) -> NMPJobContext:
    return NMPJobContext(
        workspace="default",
        job_id="job-123",
        attempt_id="attempt-1",
        step="grpo-training",
        task="training",
        jobs_url=None,
        files_url=None,
        storage_path=tmp_path,
        config_path=tmp_path / "config.yaml",
    )


def _write_gym_dataset(root: Path) -> None:
    row = {
        "task_idx": 0,
        "vf_env_id": "ascii-tree",
        "responses_create_params": {"input": [{"role": "user", "content": "hello"}]},
        "agent_ref": {"name": "verifiers_agent"},
        "answer": "42",
        "example_id": "ex-0",
        "info": {},
    }
    (root / "training.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_compile_grpo_config_sandboxed_paths(tmp_path: Path, job_ctx: NMPJobContext) -> None:
    dataset_pvc = tmp_path / "dataset"
    dataset_pvc.mkdir()
    _write_gym_dataset(dataset_pvc)

    env_root = tmp_path / "environment"
    env_root.mkdir()
    (env_root / "nemo-environment.yaml").write_text(
        "format: adapter-wheels-v1\nadapter:\n  agent: verifiers_agent\nconfig_paths: []\n",
        encoding="utf-8",
    )

    step = TrainingStepConfig(
        backend=TrainingBackend.NEMO_RL,
        model=ModelConfig(path=str(tmp_path / "model"), max_seq_length=512),
        dataset=TrainingStepConfig.DatasetConfig(path=str(dataset_pvc)),
        gym=TrainingStepConfig.GymConfig(
            environment_path=str(env_root),
            sandbox_environment_path="/job/environment",
            sandbox_dataset_path="/job/dataset",
            sandboxed=True,
            gym_runtime_image="nvcr.io/nvidia/nemo-gym-runtime:test",
        ),
        training=TrainingStepConfig.TrainingConfig(
            training_type=TrainingType.GRPO,
            finetuning_type=FinetuningType.ALL_WEIGHTS,
            grpo=GRPOConfig(num_generations_per_prompt=4),
        ),
        schedule=TrainingStepConfig.ScheduleConfig(epochs=1),
        batch=TrainingStepConfig.BatchConfig(global_batch_size=8, micro_batch_size=1),
        optimizer=TrainingStepConfig.OptimizerConfig(),
        parallelism=TrainingStepConfig.ParallelismConfig(num_gpus_per_node=1),
        output_model="out",
        workspace_path=str(tmp_path / "workspace"),
    )
    (tmp_path / "workspace").mkdir()

    cfg = compile_grpo_config(step, job_ctx)

    assert cfg["env"]["should_use_nemo_gym"] is True
    assert cfg["env"]["nemo_gym"]["sandboxed"] is True
    assert cfg["env"]["nemo_gym"]["environment_path"] == "/job/environment"
    assert cfg["data"]["train"]["data_path"] == "/job/dataset/training.jsonl"
    assert cfg["env"]["nemo_gym"]["sandbox"]["network_policy"]["egress_allow"]
    assert "host_work_path" in cfg["env"]["nemo_gym"]
    assert cfg["env"]["nemo_gym"]["bootstrap_env"]["NMP_JOB_ID"] == "job-123"
    assert "/nmp-rl/job-123/work" in cfg["env"]["nemo_gym"]["bootstrap_env"]["NMP_WORK_PATH"]
