# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_automodel_plugin.schema import AutomodelJobOutput
from nmp.automodel.adapter import automodel_spec_to_compiler_output
from nmp.automodel.api.v2.jobs.schemas import DistillationTraining, SFTTraining
from nmp.customization_common.integrations import collect_integration_secret_envs


def test_adapter_sft() -> None:
    spec = automodel_spec_to_compiler_output(
        {
            "model": "meta/llama",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "finetuning_type": "lora"},
            "output": {"name": "out", "type": "adapter", "fileset": "out-fs"},
        },
    )
    assert isinstance(spec.training, SFTTraining)
    assert spec.dataset == "default/train"


def test_adapter_distillation() -> None:
    spec = automodel_spec_to_compiler_output(
        {
            "model": "meta/llama",
            "dataset": {"training": "default/train"},
            "training": {
                "training_type": "distillation",
                "finetuning_type": "all_weights",
                "teacher_model": "meta/teacher",
            },
            "output": {"name": "out", "type": "model", "fileset": "out-fs"},
        },
    )
    assert isinstance(spec.training, DistillationTraining)
    assert spec.training.teacher_model == "meta/teacher"


def test_adapter_no_integrations() -> None:
    spec = automodel_spec_to_compiler_output(
        {
            "model": "meta/llama",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "finetuning_type": "lora"},
            "output": {"name": "out", "type": "adapter", "fileset": "out-fs"},
        },
    )
    assert spec.integrations is None
    assert collect_integration_secret_envs(spec.integrations) == []


def test_adapter_integrations_full_round_trip() -> None:
    spec = automodel_spec_to_compiler_output(
        {
            "model": "meta/llama",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "finetuning_type": "lora"},
            "output": {"name": "my-output", "type": "adapter", "fileset": "out-fs"},
            "integrations": {
                "wandb": {
                    "project": "my-project",
                    "name": "run-001",
                    "entity": "my-team",
                    "tags": ["sft", "llama"],
                    "notes": "experiment notes",
                    "base_url": "https://wandb.internal",
                    "api_key_secret": "default/wandb-key",
                },
                "mlflow": {
                    "experiment_name": "exp-1",
                    "name": "run-001",
                    "tracking_uri": "http://mlflow:5000",
                    "tags": {"team": "nlp"},
                    "description": "SFT run",
                },
            },
        },
    )

    assert spec.integrations is not None
    wandb = spec.integrations.wandb
    assert wandb is not None
    assert wandb.project == "my-project"
    assert wandb.name == "run-001"
    assert wandb.entity == "my-team"
    assert wandb.tags == ["sft", "llama"]
    assert wandb.notes == "experiment notes"
    assert wandb.base_url == "https://wandb.internal"
    assert wandb.api_key_secret is not None
    assert wandb.api_key_secret.root == "default/wandb-key"

    mlflow = spec.integrations.mlflow
    assert mlflow is not None
    assert mlflow.experiment_name == "exp-1"
    assert mlflow.name == "run-001"
    assert mlflow.tracking_uri == "http://mlflow:5000"
    assert mlflow.tags == {"team": "nlp"}
    assert mlflow.description == "SFT run"

    secret_envs = collect_integration_secret_envs(spec.integrations)
    assert secret_envs == [
        {"name": "WANDB_API_KEY", "from_secret": {"name": "default/wandb-key"}},
    ]


def test_adapter_integrations_from_automodel_job_output() -> None:
    job_output = AutomodelJobOutput.model_validate(
        {
            "model": "meta/llama",
            "dataset": {"training": "default/train"},
            "training": {"training_type": "sft", "finetuning_type": "lora"},
            "schedule": {"epochs": 1},
            "batch": {"global_batch_size": 8, "micro_batch_size": 1},
            "optimizer": {"learning_rate": 1e-4},
            "parallelism": {"num_nodes": 1, "num_gpus_per_node": 1},
            "output": {"name": "out", "type": "adapter", "fileset": "out-fs"},
            "integrations": {"wandb": {"project": "plugin-project"}},
        },
    )

    spec = automodel_spec_to_compiler_output(job_output)

    assert spec.integrations is not None
    assert spec.integrations.wandb is not None
    assert spec.integrations.wandb.project == "plugin-project"
