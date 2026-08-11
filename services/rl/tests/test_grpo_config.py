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
    LoRAConfig,
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


def _make_grpo_step(
    tmp_path: Path,
    dataset_pvc: Path,
    *,
    finetuning_type: FinetuningType = FinetuningType.ALL_WEIGHTS,
    lora: LoRAConfig | None = None,
    tensor_parallel_size: int = 1,
) -> TrainingStepConfig:
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
            finetuning_type=finetuning_type,
            grpo=GRPOConfig(num_generations_per_prompt=4),
            lora=lora,
        ),
        schedule=TrainingStepConfig.ScheduleConfig(epochs=1),
        batch=TrainingStepConfig.BatchConfig(global_batch_size=8, micro_batch_size=1),
        optimizer=TrainingStepConfig.OptimizerConfig(),
        parallelism=TrainingStepConfig.ParallelismConfig(
            num_gpus_per_node=1,
            tensor_parallel_size=tensor_parallel_size,
        ),
        output_model="out",
        workspace_path=str(tmp_path / "workspace"),
    )


def _prepared_step(
    tmp_path: Path,
    *,
    finetuning_type: FinetuningType = FinetuningType.ALL_WEIGHTS,
    lora: LoRAConfig | None = None,
    tensor_parallel_size: int = 1,
) -> tuple[TrainingStepConfig, Path]:
    dataset_pvc = tmp_path / "dataset"
    dataset_pvc.mkdir(exist_ok=True)
    _write_gym_dataset(dataset_pvc)
    (tmp_path / "workspace").mkdir(exist_ok=True)
    return (
        _make_grpo_step(
            tmp_path,
            dataset_pvc,
            finetuning_type=finetuning_type,
            lora=lora,
            tensor_parallel_size=tensor_parallel_size,
        ),
        dataset_pvc,
    )


def test_compile_grpo_config_sandboxed_paths(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    step, dataset_pvc = _prepared_step(tmp_path)
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
    # Full-weight omits lora_cfg entirely rather than emitting enabled=False.
    assert "lora_cfg" not in cfg["policy"]["dtensor_cfg"]

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
    step, _ = _prepared_step(tmp_path)
    with pytest.raises(ValueError, match="NMP_JOB_STORAGE_PVC_CLAIM"):
        compile_grpo_config(step, job_ctx)


def test_compile_grpo_config_disables_validation_without_val_split(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Gym dataset only has to ship training.jsonl; NeMo-RL asserts on a missing
    val dataset whenever val_period / val_at_start / val_at_end is set."""
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    step, _ = _prepared_step(tmp_path)
    cfg = compile_grpo_config(step, job_ctx)

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
    step, _ = _prepared_step(tmp_path)
    cfg = compile_grpo_config(step, job_ctx)

    # _v2 selects DTensorPolicyWorkerV2 -> PY_EXECUTABLES.AUTOMODEL, which is neither
    # built nor prefetched. Unset (or False) keeps DTensorPolicyWorker -> `fsdp`.
    assert not cfg["policy"]["dtensor_cfg"].get("_v2", False)
    # megatron_cfg would select MegatronPolicyWorker -> `mcore`, also excluded.
    assert cfg["policy"]["megatron_cfg"]["enabled"] is False
    # vLLM is the only prefetched generation backend (`vllm`); sglang/trtllm are not.
    assert cfg["policy"]["generation"]["backend"] == "vllm"


def test_compile_grpo_config_enables_lora(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    step, _ = _prepared_step(
        tmp_path,
        finetuning_type=FinetuningType.LORA,
        lora=LoRAConfig(rank=32, alpha=64, use_triton=True),
    )
    cfg = compile_grpo_config(step, job_ctx)
    lora_cfg = cfg["policy"]["dtensor_cfg"]["lora_cfg"]
    assert lora_cfg["enabled"] is True
    assert lora_cfg["dim"] == 32
    assert lora_cfg["alpha"] == 64
    assert lora_cfg["use_triton"] is True
    assert cfg["policy"]["dtensor_cfg"]["_v2"] is True


def test_compiled_config_has_master_config_required_fields(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fields NeMo-RL's ``MasterConfig`` requires but gives no default for.

    ``MasterConfig`` is a pydantic model, so a missing key is a hard
    ValidationError -- and it is raised by the *driver*, after the Ray cluster is
    already up. On a real job that is minutes of GPU time and four pods in before
    anything complains, and none of it is visible to the compiler's own tests.

    ``make_sequence_length_divisible_by`` was set by dpo_config but not here, and
    the three generation fields are GRPO-only (DPO runs no vLLM), so nothing
    exercised them. Values mirror upstream's reference config
    ``examples/configs/grpo_math_1B.yaml``.
    """
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    step, _ = _prepared_step(tmp_path)
    policy = compile_grpo_config(step, job_ctx)["policy"]

    # None is meaningful, not absent: generation/__init__.py fills stop_token_ids
    # with [tokenizer.eos_token_id] when it is None.
    for field in ("top_k", "stop_token_ids", "stop_strings"):
        assert field in policy["generation"], f"policy.generation.{field} missing"
        assert policy["generation"][field] is None

    assert policy["make_sequence_length_divisible_by"] == step.parallelism.tensor_parallel_size


@pytest.mark.parametrize(
    ("finetuning_type", "lora", "expected"),
    [
        (FinetuningType.ALL_WEIGHTS, None, False),
        (FinetuningType.LORA, LoRAConfig(rank=8), True),
        # finetuning_type is what enables LoRA; an omitted lora block just takes defaults.
        (FinetuningType.LORA, None, True),
    ],
)
def test_lora_and_v2_stay_coupled(
    tmp_path: Path,
    job_ctx: NMPJobContext,
    monkeypatch: pytest.MonkeyPatch,
    finetuning_type: FinetuningType,
    lora: LoRAConfig | None,
    expected: bool,
) -> None:
    """``lora_cfg.enabled`` and ``_v2`` must never disagree.

    LoRA is implemented only in DTensorPolicyWorkerV2; the V1 DTensorPolicyWorker
    ignores ``lora_cfg`` entirely. So enabling LoRA without ``_v2`` does not fail --
    it silently trains full weights and reports success. The reverse (``_v2`` without
    LoRA) is also wrong: it moves a full-weight run onto PY_EXECUTABLES.AUTOMODEL,
    which the image does not prefetch.

    The two assertions above cover each case on its own; this pins the relationship,
    so decoupling them fails here rather than in a training run.
    """
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    step, _ = _prepared_step(tmp_path, finetuning_type=finetuning_type, lora=lora)
    dtensor_cfg = compile_grpo_config(step, job_ctx)["policy"]["dtensor_cfg"]

    # Read exactly the way NeMo-RL does, so "key omitted" and "enabled: False" are
    # equivalent here and the test does not depend on which one we emit.
    assert dtensor_cfg.get("lora_cfg", {}).get("enabled", False) is expected
    assert dtensor_cfg.get("_v2", False) is expected


def test_compile_grpo_config_disables_triton_for_tp(
    tmp_path: Path, job_ctx: NMPJobContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMP_JOB_STORAGE_PVC_CLAIM", "nmp-job-storage")
    step, _ = _prepared_step(
        tmp_path,
        finetuning_type=FinetuningType.LORA,
        lora=LoRAConfig(rank=16, use_triton=True),
        tensor_parallel_size=2,
    )
    # Fix batch divisibility for tp=2 on 1 gpu would fail validate — compiler path
    # only; here we only compile YAML so TP is just a knob on lora_cfg.
    cfg = compile_grpo_config(step, job_ctx)
    assert cfg["policy"]["dtensor_cfg"]["lora_cfg"]["use_triton"] is False
