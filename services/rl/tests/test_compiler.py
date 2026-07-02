# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compiler tests: public-spec → TrainingStepConfig mapping, executor selection,
and the 4-step PlatformJobSpec shape."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.integrations import IntegrationsSpec, MlflowIntegration, WandbIntegration
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nmp.common.entities.utils import get_random_id
from nmp.rl.app.jobs.compiler import (
    _build_training_step,
    _build_training_step_config,
    platform_job_config_compiler,
)
from nmp.rl.app.jobs.training.schemas import OptimizerType, TrainingType
from nmp.rl.entities.values import FinetuningType
from nmp.rl.schemas import DPOTraining, OutputResponse, ParallelismParams, RlJobOutput


def _make_model_entity(fileset: str | None = "default/base-model") -> ModelEntity:
    return ModelEntity(
        id=get_random_id("model"),
        workspace="default",
        name="base-model",
        fileset=fileset,
        trust_remote_code=False,
        finetuning_type=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _make_job_output(
    training: DPOTraining | None = None,
    integrations: IntegrationsSpec | None = None,
) -> RlJobOutput:
    return RlJobOutput(
        model="default/base-model",
        dataset="default/prefs",
        training=training or DPOTraining(),
        integrations=integrations,
        output=OutputResponse(name="my-dpo", type="model", fileset="my-dpo-fs"),
    )


# Job specs/steps/executors/containers are all TypedDicts (plain dicts).
def _container(step: dict[str, Any]) -> dict[str, Any]:
    return step["executor"]["container"]


def _provider(step: dict[str, Any]) -> str:
    return step["executor"]["provider"]


@pytest.fixture
def mock_sdk() -> Mock:
    return Mock(spec=AsyncNeMoPlatform)


# --------------------------------------------------------------------------- #
# _build_training_step_config: public DPOTraining → internal TrainingStepConfig
# --------------------------------------------------------------------------- #


def test_training_step_config_maps_exposed_knobs() -> None:
    t = DPOTraining(
        optimizer_type=OptimizerType.ADAM_WITH_FLAT_LR,
        adam_eps=3e-7,
        activation_checkpointing=True,
        keep_top_k=5,
        val_at_end=True,
        ref_policy_kl_penalty=0.2,
        max_grad_norm=2.0,
    )
    sc = _build_training_step_config(_make_job_output(t), trust_remote_code=True)

    # Optimizer knobs.
    assert sc.optimizer.optimizer_type is OptimizerType.ADAM_WITH_FLAT_LR
    assert sc.optimizer.eps == 3e-7
    # Memory / checkpoint / validation knobs.
    assert sc.parallelism.activation_checkpointing is True
    assert sc.schedule.keep_top_k == 5
    assert sc.schedule.val_at_end is True
    # DPO hyperparameters + passthrough.
    assert sc.training.training_type is TrainingType.DPO
    assert sc.training.finetuning_type is FinetuningType.ALL_WEIGHTS
    assert sc.training.dpo is not None
    assert sc.training.dpo.ref_policy_kl_penalty == 0.2
    assert sc.training.dpo.max_grad_norm == 2.0
    assert sc.model.trust_remote_code is True


def test_training_step_config_maps_integrations() -> None:
    """job_spec.integrations must reach the step config; otherwise W&B/MLflow are
    silently disabled because the driver's builders read customizer_config.integrations."""
    integrations = IntegrationsSpec(
        wandb=WandbIntegration(
            project="proj", name="run", entity="team", tags=["t1"], notes="n", base_url="https://wandb.example"
        ),
        mlflow=MlflowIntegration(
            experiment_name="exp", name="mlrun", tags={"k": "v"}, description="d", tracking_uri="http://mlflow:5000"
        ),
    )
    sc = _build_training_step_config(_make_job_output(integrations=integrations), trust_remote_code=False)

    assert sc.integrations.wandb is not None
    assert sc.integrations.wandb.project == "proj"
    assert sc.integrations.wandb.name == "run"
    assert sc.integrations.wandb.entity == "team"
    assert sc.integrations.wandb.base_url == "https://wandb.example"

    assert sc.integrations.mlflow is not None
    assert sc.integrations.mlflow.experiment_name == "exp"
    # public MLflow `name` maps to the step config's `run_name`
    assert sc.integrations.mlflow.run_name == "mlrun"
    assert sc.integrations.mlflow.tracking_uri == "http://mlflow:5000"
    assert sc.integrations.mlflow.tags == {"k": "v"}


def test_training_step_config_no_integrations_is_empty() -> None:
    sc = _build_training_step_config(_make_job_output(), trust_remote_code=False)
    assert sc.integrations.wandb is None
    assert sc.integrations.mlflow is None


def test_training_step_config_defaults_match_prior_hardcodes() -> None:
    sc = _build_training_step_config(_make_job_output(), trust_remote_code=False)
    assert sc.optimizer.optimizer_type is None
    assert sc.optimizer.eps == 1e-5
    assert sc.parallelism.activation_checkpointing is False
    assert sc.schedule.keep_top_k == 1
    # val_at_end defaults True → final checkpoint carries val metrics for best-checkpoint selection.
    assert sc.schedule.val_at_end is True


# --------------------------------------------------------------------------- #
# _build_training_step: executor selection by topology
# --------------------------------------------------------------------------- #


def test_single_node_uses_gpu_executor() -> None:
    job = _make_job_output(DPOTraining(parallelism=ParallelismParams(num_nodes=1, num_gpus_per_node=1)))
    step = _build_training_step(job, [], trust_remote_code=False, profile=None)
    assert step["name"] == "dpo-training"
    assert _provider(step) == "gpu"
    assert _container(step)["command"] == ["-m", "nmp.rl.tasks.training"]


def test_multi_node_requires_shared_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nmp.rl.app.jobs.compiler.config.multinode_shared_storage_path", None, raising=False)
    job = _make_job_output(DPOTraining(parallelism=ParallelismParams(num_nodes=2, num_gpus_per_node=2)))
    with pytest.raises(PlatformJobCompilationError, match="shared filesystem"):
        _build_training_step(job, [], trust_remote_code=False, profile=None)


def test_multi_node_uses_distributed_executor_with_shared_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nmp.rl.app.jobs.compiler.config.multinode_shared_storage_path", "/shared", raising=False)
    job = _make_job_output(DPOTraining(parallelism=ParallelismParams(num_nodes=2, num_gpus_per_node=2)))
    step = _build_training_step(job, [], trust_remote_code=False, profile=None)
    assert _provider(step) == "gpu_distributed"

    # BASE_LOG_DIR is injected so Ray can coordinate the cross-node barrier.
    def _env_value(env: Any) -> Any:
        return env["value"] if isinstance(env, dict) else getattr(env, "value", None)

    assert any(_env_value(env) == "/shared" for env in step["environment"])


def test_explicit_profile_overrides_default() -> None:
    job = _make_job_output()
    step = _build_training_step(job, [], trust_remote_code=False, profile="custom-gpu")
    assert step["executor"]["profile"] == "custom-gpu"


# --------------------------------------------------------------------------- #
# platform_job_config_compiler: full 4-step spec
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_compiler_emits_four_steps(monkeypatch: pytest.MonkeyPatch, mock_sdk: Mock) -> None:
    monkeypatch.setattr(
        "nmp.rl.app.jobs.compiler.fetch_model_entity",
        AsyncMock(return_value=_make_model_entity()),
    )
    spec = await platform_job_config_compiler("default", _make_job_output(), mock_sdk)

    steps = spec["steps"]
    names = [s["name"] for s in steps]
    assert names == ["model-and-dataset-download", "dpo-training", "model-upload", "model-entity-creation"]

    # CPU task steps share the lighter tasks image; the GPU step uses the training image.
    assert "nmp-rl-tasks" in _container(steps[0])["image"]
    assert "nmp-rl-training" in _container(steps[1])["image"]
    assert "nmp-rl-tasks" in _container(steps[2])["image"]
    assert _container(steps[0])["command"] == ["-m", "nmp.rl.tasks.file_io"]
    assert _container(steps[3])["command"] == ["-m", "nmp.rl.tasks.model_entity"]


@pytest.mark.asyncio
async def test_compiler_rejects_model_without_fileset(monkeypatch: pytest.MonkeyPatch, mock_sdk: Mock) -> None:
    monkeypatch.setattr(
        "nmp.rl.app.jobs.compiler.fetch_model_entity",
        AsyncMock(return_value=_make_model_entity(fileset=None)),
    )
    with pytest.raises(PlatformJobCompilationError, match="has no fileset"):
        await platform_job_config_compiler("default", _make_job_output(), mock_sdk)
