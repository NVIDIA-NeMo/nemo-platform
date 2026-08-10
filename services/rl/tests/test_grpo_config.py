# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GRPO config compilation (sandbox paths + egress)."""

from __future__ import annotations

import json
from pathlib import Path

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


def _sandboxed_step(tmp_path: Path, dataset_pvc: Path) -> TrainingStepConfig:
    env_root = tmp_path / "environment"
    env_root.mkdir(exist_ok=True)
    (env_root / "nemo-environment.yaml").write_text(
        "format: adapter-wheels-v1\nadapter:\n  agent: verifiers_agent\n"
        "config_paths:\n  - configs/verifiers_agent.yaml\n",
        encoding="utf-8",
    )
    return TrainingStepConfig(
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


def test_compile_grpo_config_sandboxed_paths(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    dataset_pvc = tmp_path / "dataset"
    dataset_pvc.mkdir()
    _write_gym_dataset(dataset_pvc)

    (tmp_path / "workspace").mkdir()

    step = _sandboxed_step(tmp_path, dataset_pvc)

    cfg = compile_grpo_config(step, job_ctx)

    nemo_gym = cfg["env"]["nemo_gym"]
    assert cfg["env"]["should_use_nemo_gym"] is True
    assert nemo_gym["sandboxed"] is True
    assert nemo_gym["environment_path"] == "/job/environment"
    # The master reads the dataset itself, so the dataloader path stays on job storage
    # even though the sandbox sees the same file at /job/dataset.
    assert cfg["data"]["train"]["data_path"] == str(dataset_pvc / "training.jsonl")
    assert nemo_gym["sandbox"]["network_policy"]["egress_allow"]
    assert "host_work_path" in nemo_gym
    assert nemo_gym["bootstrap_env"]["NMP_JOB_ID"] == "job-123"
    assert "/nmp-rl/job-123/work" in nemo_gym["bootstrap_env"]["NMP_WORK_PATH"]
    # config_paths must reach Gym in sandboxed mode too, or no servers start.
    assert nemo_gym["config_paths"] == ["configs/verifiers_agent.yaml"]
    # job_id is a sandbox pod label; without it every job shares one default.
    assert nemo_gym["job_id"] == "job-123"

    sandbox = nemo_gym["sandbox"]
    assert sandbox["environment_pvc_claim"] == "nmp-job-storage"
    assert sandbox["workspace_pvc_claim"] == "nmp-job-storage"
    assert sandbox["dataset_pvc_claim"] == "nmp-job-storage"
    assert sandbox["environment_sub_path"] == "jobs/default/job-123/environment"
    assert sandbox["dataset_sub_path"] == "jobs/default/job-123/dataset"


def test_compile_grpo_config_sandboxed_requires_pvc_claim(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NMP_JOB_STORAGE_PVC_CLAIM", raising=False)
    dataset_pvc = tmp_path / "dataset"
    dataset_pvc.mkdir()
    _write_gym_dataset(dataset_pvc)
    (tmp_path / "workspace").mkdir()

    step = _sandboxed_step(tmp_path, dataset_pvc)
    with pytest.raises(ValueError, match="NMP_JOB_STORAGE_PVC_CLAIM"):
        compile_grpo_config(step, job_ctx)


def test_compile_grpo_config_disables_validation_without_val_split(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Gym dataset only has to ship training.jsonl; NeMo-RL asserts on a missing
    val dataset whenever val_period / val_at_start / val_at_end is set."""
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    dataset_pvc = tmp_path / "dataset"
    dataset_pvc.mkdir()
    _write_gym_dataset(dataset_pvc)
    (tmp_path / "workspace").mkdir()

    cfg = compile_grpo_config(_sandboxed_step(tmp_path, dataset_pvc), job_ctx)

    assert cfg["data"]["validation"] is None
    assert cfg["grpo"]["val_period"] == 0
    assert cfg["grpo"]["val_at_end"] is False
    assert cfg["grpo"]["val_at_start"] is False
    assert cfg["checkpointing"]["metric_name"] is None
    assert cfg["checkpointing"]["save_period"] > 0


def test_compiled_config_selects_only_prefetched_actors(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard the config -> Ray actor -> venv coupling.

    NeMo-RL picks the policy actor from the compiled config, and
    ray_actor_environment_registry maps each actor to a py_executable (a `uv run
    --extra <X>` venv). Only the extras prefetched in
    docker/rl/Dockerfile.nmp-rl-base exist in the image; anything else is built on
    the node at job startup, which on a deny-egress training cluster fails outright.

    Each assertion below corresponds to a prefetch filter in that Dockerfile. If you
    flip one, add the matching actor to the prefetch filter list *and* its
    verification loop first.
    """
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    dataset_pvc = tmp_path / "dataset"
    dataset_pvc.mkdir()
    _write_gym_dataset(dataset_pvc)
    (tmp_path / "workspace").mkdir()

    cfg = compile_grpo_config(_sandboxed_step(tmp_path, dataset_pvc), job_ctx)

    # _v2 selects DTensorPolicyWorkerV2 -> PY_EXECUTABLES.AUTOMODEL, which is neither
    # built nor prefetched. Unset (or False) keeps DTensorPolicyWorker -> `fsdp`.
    assert not cfg["policy"]["dtensor_cfg"].get("_v2", False)
    # megatron_cfg would select MegatronPolicyWorker -> `mcore`, also excluded.
    assert cfg["policy"]["megatron_cfg"]["enabled"] is False
    # vLLM is the only prefetched generation backend (`vllm`); sglang/trtllm are not.
    assert cfg["policy"]["generation"]["backend"] == "vllm"
