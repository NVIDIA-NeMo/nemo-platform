# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for job compiler."""

import asyncio
import inspect
import re
from datetime import datetime
from types import SimpleNamespace

import pytest
from nemo_platform import AsyncNeMoPlatform, NotFoundError
from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.jobs.api_factory import _validate_and_resolve_job_output
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.auth import AuthClient, auth_client_context
from nmp.common.entities.client import EntityClient
from nmp.common.entities.constants import NAME_PATTERN
from nmp.common.entities.utils import get_random_id
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.customizer.api.v2.jobs.schemas import CustomizationJobInput, CustomizationJobOutput
from nmp.customizer.app.constants import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_MODEL_PATH,
    DEFAULT_TEACHER_MODEL_PATH,
    DEFAULT_TRAINING_OUTPUT_PATH,
)
from nmp.customizer.app.jobs.compiler import (
    CPU_IMAGE_NAMESPACE,
    GPU_IMAGE_NAMESPACE,
    _append_download_if_present,
    _build_file_download_config,
    _build_model_entity_config,
    _build_output_fileset_metadata,
    _resolve_is_embedding_model,
    _validate_deployment_config,
    platform_job_config_compiler,
)
from nmp.customizer.app.jobs.file_io.schemas import DownloadItem, FileSetRef
from nmp.customizer.app.jobs.training.compiler import _collect_integration_secret_envs, _translate_training_config
from nmp.customizer.app.jobs.training.schemas import DistillationConfig
from nmp.customizer.entities.values import FinetuningType
from nmp.customizer.utils import generate_customization_id, transform_input_to_output


def _make_mock_model_entity(
    *,
    workspace: str = "default",
    name: str = "test-target",
    fileset: str = "fileset://default/base-model",
    trust_remote_code: bool = False,
) -> ModelEntity:
    """Create a ModelEntity for use in compiler tests."""
    return ModelEntity(
        id=get_random_id("model"),
        workspace=workspace,
        name=name,
        fileset=fileset,
        trust_remote_code=trust_remote_code,
        finetuning_type=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def mock_sdk(mocker):
    """Create a mock SDK with models.retrieve configured for compiler tests."""
    sdk = mocker.Mock(spec=AsyncNeMoPlatform)
    sdk.models = mocker.Mock()
    sdk.models.retrieve = mocker.AsyncMock(
        side_effect=lambda *, name, workspace, verbose=True: _make_mock_model_entity(workspace=workspace, name=name)
    )
    sdk.files = mocker.Mock()
    sdk.files.filesets = mocker.Mock()
    sdk.files.filesets.retrieve = mocker.AsyncMock(return_value=mocker.Mock())
    return sdk


@pytest.fixture
def mock_auth_client(mocker):
    """Create a mock AuthClient that grants all permissions by default."""
    client = mocker.Mock(spec=AuthClient)
    client.has_permissions = mocker.AsyncMock(return_value=True)
    token = auth_client_context.set(client)
    yield client
    auth_client_context.reset(token)


FILE_IO_IMAGE = get_qualified_image(CPU_IMAGE_NAMESPACE)
GPU_TASKS_IMAGE = get_qualified_image(GPU_IMAGE_NAMESPACE)
TRAINING_AUTOMODEL_IMAGE = get_qualified_image("customizer-automodel")
TRAINING_RL_IMAGE = get_qualified_image("customizer-rl")

JobOutputType, transformer_func = _validate_and_resolve_job_output(
    job_output=CustomizationJobOutput,
    job_input=CustomizationJobInput,
    input_to_output=transform_input_to_output,
)

assert isinstance(JobOutputType, type) and issubclass(JobOutputType, CustomizationJobOutput), (
    f"Expected CustomizationJobOutput, got {type(JobOutputType)}"
)
assert callable(transformer_func), f"Expected callable input-to-output transformer, got {type(transformer_func)}"


async def _compiler_args_async(
    original_spec: CustomizationJobInput, workspace: str, entity_client: EntityClient, sdk: AsyncNeMoPlatform
) -> tuple[CustomizationJobOutput, str]:
    """Derive transformed_spec and job_name as job_route_factory's create_job would."""
    job_name = generate_customization_id()

    transformed_spec = original_spec
    if transformer_func:
        result = transformer_func(original_spec, workspace, entity_client, job_name, sdk)
        transformed_spec = await result if inspect.isawaitable(result) else result

    assert isinstance(transformed_spec, CustomizationJobOutput), (
        f"Expected CustomizationJobOutput, got {type(transformed_spec)}"
    )
    return transformed_spec, job_name


def _compiler_args(original_spec: CustomizationJobInput, workspace: str, entity_client: EntityClient, sdk):
    return asyncio.run(_compiler_args_async(original_spec, workspace, entity_client, sdk))


def make_valid_job_input_dict() -> dict:
    """Create a valid CustomizationJobInput as a dictionary."""
    return {
        "model": "default/test-target",
        "training": {
            "type": "sft",
            "peft": {"type": "lora"},
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 0.0001,
        },
        "dataset": "fileset://default/my-dataset",
    }


def make_valid_job_input() -> CustomizationJobInput:
    """Create a validated CustomizationJobInput with inline target object."""
    return CustomizationJobInput.model_validate(make_valid_job_input_dict())


def make_valid_job_output(job_input: CustomizationJobInput | None = None, *, sdk) -> CustomizationJobOutput:
    """Create a validated CustomizationJobOutput from a CustomizationJobInput."""
    if job_input is None:
        job_input = make_valid_job_input()
    transformed_spec, _ = _compiler_args(job_input, "workspace", entity_client=object(), sdk=sdk)
    assert isinstance(transformed_spec, CustomizationJobOutput)
    return transformed_spec


async def make_valid_job_output_async(
    job_input: CustomizationJobInput | None = None,
    *,
    sdk,
) -> CustomizationJobOutput:
    """Async variant of make_valid_job_output for use in async tests."""
    if job_input is None:
        job_input = make_valid_job_input()
    transformed_spec, _ = await _compiler_args_async(job_input, "workspace", entity_client=object(), sdk=sdk)
    assert isinstance(transformed_spec, CustomizationJobOutput)
    return transformed_spec


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "training_input",
        "expected_image",
        "expected_backend",
        "expected_finetuning_type",
        "trust_remote_code",
        "integrations_input",
    ),
    [
        (
            {"type": "sft", "peft": {"type": "lora"}, "epochs": 1, "batch_size": 4, "learning_rate": 0.0001},
            TRAINING_AUTOMODEL_IMAGE,
            "automodel",
            "lora",
            False,
            None,
        ),
        (
            {"type": "dpo", "epochs": 1, "batch_size": 4, "learning_rate": 0.0001},
            TRAINING_RL_IMAGE,
            "nemo_rl",
            "all_weights",
            True,
            None,
        ),
        (
            {"type": "sft", "peft": {"type": "lora"}, "epochs": 1, "batch_size": 4, "learning_rate": 0.0001},
            TRAINING_AUTOMODEL_IMAGE,
            "automodel",
            "lora",
            False,
            {"wandb": {"project": "my-project", "api_key_secret": "my-wandb-secret"}},
        ),
        (
            {
                "type": "sft",
                "peft": {"type": "lora", "merge": True},
                "epochs": 1,
                "batch_size": 4,
                "learning_rate": 0.0001,
            },
            TRAINING_AUTOMODEL_IMAGE,
            "automodel",
            "lora_merged",
            False,
            None,
        ),
    ],
)
async def test_platform_job_config_compiler(
    mocker,
    mock_sdk,
    mock_auth_client,
    training_input: dict,
    expected_image: str,
    expected_backend: str,
    expected_finetuning_type: str,
    trust_remote_code: bool,
    integrations_input: dict | None,
):
    """Test that platform_job_config_compiler produces a valid PlatformJobSpec."""
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=_make_mock_model_entity(trust_remote_code=trust_remote_code),
    )
    job_input_dict = {
        "model": "default/test-target",
        "training": training_input,
        "dataset": "fileset://default/my-dataset",
    }
    if integrations_input is not None:
        job_input_dict["integrations"] = integrations_input
    job_input = CustomizationJobInput.model_validate(job_input_dict)

    # Derive transformed_spec and job_name the same way job_route_factory's create_job would.
    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    assert transformed_spec.output is not None
    generated_fileset_name = transformed_spec.output.fileset
    generated_model_name = transformed_spec.output.name
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    for step in result["steps"]:
        step_name = step["name"]
        assert re.match(NAME_PATTERN, step_name), f"invalid step name {step_name}"

    base_environment = [{"name": "NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH", "value": "/var/run/scratch/job"}]
    cpu_resources = {
        "limits": {"cpu": "4", "memory": "16Gi"},
        "requests": {"cpu": "1", "memory": "8Gi"},
    }

    peft: dict[str, str | int] | None = None
    if expected_finetuning_type in ("lora", "lora_merged"):
        peft = {"type": expected_finetuning_type, "alpha": 32, "rank": 8}

    expected_training_environment: list[dict] = list(base_environment)
    expected_wandb_config = None
    if integrations_input and "wandb" in integrations_input:
        wandb_input = integrations_input["wandb"]
        if wandb_input.get("api_key_secret"):
            expected_training_environment.append(
                {"name": "WANDB_API_KEY", "from_secret": {"name": wandb_input["api_key_secret"]}}
            )
        expected_wandb_config = {
            "project": wandb_input.get("project"),
            "name": wandb_input.get("name"),
            "entity": wandb_input.get("entity"),
            "tags": wandb_input.get("tags"),
            "notes": wandb_input.get("notes"),
            "base_url": wandb_input.get("base_url"),
        }

    training_type = training_input["type"]
    peft_input = training_input.get("peft")
    has_lora = peft_input is not None

    expected_internal_lora = None
    if has_lora:
        expected_internal_lora = {
            "rank": 8,
            "alpha": 32,
            "dropout": 0.0,
            "exclude_modules": None,
            "use_triton": True,
            "target_modules": [
                "*proj",
            ],
        }

    expected_dpo = None
    if training_type == "dpo":
        expected_dpo = {
            "ref_policy_kl_penalty": 0.05,
            "preference_average_log_probs": False,
            "sft_average_log_probs": False,
            "preference_loss_weight": 1.0,
            "sft_loss_weight": 0.0,
            "max_grad_norm": 1.0,
        }

    expected_training_environment += [{"name": "HF_DATASETS_OFFLINE", "value": "1"}]
    expected = {
        "steps": [
            {
                "name": "model-and-dataset-download",
                "executor": {
                    "provider": "cpu",
                    "container": {
                        "image": FILE_IO_IMAGE,
                        "command": ["nemo-platform", "run", "task", "--task", "nmp.customizer.tasks.file_io"],
                    },
                    "resources": cpu_resources,
                },
                "environment": base_environment,
                "config": {
                    "download": [
                        {"src": {"workspace": "default", "name": "base-model"}, "dest": DEFAULT_MODEL_PATH},
                        {
                            "src": {"workspace": "default", "name": "my-dataset"},
                            "dest": DEFAULT_DATASET_PATH,
                        },
                    ],
                    "upload": [],
                },
            },
            {
                "name": "customization-training-job",
                "executor": {
                    "provider": "gpu",
                    "profile": "default",
                    "container": {
                        "image": expected_image,
                        "command": ["python", "-m", "nmp.customizer.tasks.training"],
                    },
                    "resources": {
                        "num_gpus": 1,
                    },
                },
                "environment": expected_training_environment,
                "config": {
                    "output_model": generated_model_name,
                    "backend": expected_backend,
                    "model": {
                        "attn_implementation": "sdpa",
                        "path": DEFAULT_MODEL_PATH,
                        "name": "default/test-target",
                        "precision": None,
                        "max_seq_length": 2048,
                        "trust_remote_code": trust_remote_code,
                        "override_custom_impl": False,
                        "is_embedding_model": False,
                        "chat_template": None,
                        "v4_compatible": False,
                    },
                    "dataset": {
                        "path": DEFAULT_DATASET_PATH,
                        "prompt_template": None,
                        "add_bos": None,
                        "add_eos": None,
                    },
                    "training": {
                        "training_type": training_type,
                        "finetuning_type": expected_finetuning_type,
                        "lora": expected_internal_lora,
                        "kd": None,
                        "dpo": expected_dpo,
                    },
                    "schedule": {
                        "epochs": 1,
                        "max_steps": None,
                        "val_check_interval": None,
                    },
                    "seed": 1111,
                    "batch": {
                        "global_batch_size": 4,
                        "micro_batch_size": 1,
                        "sequence_packing": False,
                        "sequence_packing_max_samples": 1000,
                    },
                    "optimizer": {
                        "optimizer_type": None,
                        "learning_rate": 0.0001,
                        "min_learning_rate": None,
                        "eps": 1e-08,
                        "weight_decay": 0.01,
                        "beta1": 0.9,
                        "beta2": 0.999,
                        "warmup_steps": 0,
                    },
                    "parallelism": {
                        "num_nodes": 1,
                        "num_gpus_per_node": 1,
                        "tensor_parallel_size": 1,
                        "pipeline_parallel_size": 1,
                        "context_parallel_size": 1,
                        "expert_parallel_size": None,
                        "sequence_parallel": False,
                    },
                    "integrations": {
                        "wandb": expected_wandb_config,
                        "mlflow": None,
                    },
                    "workspace_path": DEFAULT_TRAINING_OUTPUT_PATH,
                    "output_path": DEFAULT_OUTPUT_MODEL_PATH,
                    "training_timeout": None,
                },
                "lifecycle": {
                    "staleness_timeout_seconds": 3600,
                },
            },
            {
                "name": "model-upload",
                "executor": {
                    "provider": "cpu",
                    "container": {
                        "image": FILE_IO_IMAGE,
                        "command": ["nemo-platform", "run", "task", "--task", "nmp.customizer.tasks.file_io"],
                    },
                    "resources": cpu_resources,
                },
                "environment": base_environment,
                "config": {
                    "download": [],
                    "upload": [
                        {
                            "src": DEFAULT_OUTPUT_MODEL_PATH,
                            "dest": {
                                "workspace": None,
                                "name": generated_fileset_name,
                            },
                            "metadata": None,
                        }
                    ],
                },
            },
            {
                "name": "model-entity-creation",
                "executor": {
                    "provider": "cpu",
                    "container": {
                        "image": FILE_IO_IMAGE,
                        "command": ["nemo-platform", "run", "task", "--task", "nmp.customizer.tasks.model_entity"],
                    },
                    "resources": cpu_resources,
                },
                "environment": base_environment,
                "config": {
                    "name": generated_model_name,
                    "workspace": "workspace",
                    "model_entity": "default/test-target",
                    "deployment_config": None,
                    "description": "Customized model from job",
                    "fileset": {
                        "workspace": None,
                        "name": generated_fileset_name,
                    },
                    "base_model": "default/test-target",
                    "peft": peft,
                    "trust_remote_code": trust_remote_code,
                },
            },
        ],
    }

    assert result == expected


@pytest.mark.asyncio
async def test_platform_job_config_compiler_distributed(mocker, mock_sdk, mock_auth_client):
    """Test that multi-node jobs use the distributed GPU executor."""
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=_make_mock_model_entity(),
    )
    job_input_dict = make_valid_job_input_dict()
    job_input_dict["training"]["parallelism"] = {
        "num_nodes": 2,
        "num_gpus_per_node": 4,
    }
    job_input_dict["training"]["batch_size"] = 8
    job_input = CustomizationJobInput.model_validate(job_input_dict)

    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    assert len(list(result["steps"])) >= 2
    training_step = list(result["steps"])[1]

    executor = training_step.get("executor", {})
    resources = executor.get("resources", {})
    actual_training_step = {
        "name": training_step.get("name"),
        "executor": {
            "provider": executor.get("provider"),
            "profile": executor.get("profile"),
            "resources": {
                "num_gpus": resources.get("num_gpus"),
                "num_nodes": resources.get("num_nodes"),
            },
        },
    }

    expected_training_step = {
        "name": "customization-training-job",
        "executor": {
            "provider": "gpu_distributed",
            "profile": "default",
            "resources": {
                "num_gpus": 4,
                "num_nodes": 2,
            },
        },
    }
    assert actual_training_step == expected_training_step


@pytest.mark.asyncio
async def test_platform_job_config_compiler_distillation(mocker, mock_sdk, mock_auth_client):
    """Test that distillation jobs include teacher model download and kd config."""
    student_me = _make_mock_model_entity(fileset="fileset://default/base-model")
    teacher_me = _make_mock_model_entity(
        workspace="meta",
        name="llama-3.1-70b-instruct",
        fileset="fileset://meta/llama-3.1-70b-instruct",
        trust_remote_code=False,
    )
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        side_effect=[student_me, teacher_me],
    )

    job_input_dict = {
        "model": "default/test-target",
        "training": {
            "type": "distillation",
            "teacher_model": "meta/llama-3.1-70b-instruct",
            "teacher_precision": "bf16",
            "distillation_ratio": 0.7,
            "distillation_temperature": 2.0,
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 0.0001,
        },
        "dataset": "fileset://default/my-dataset",
    }
    job_input = CustomizationJobInput.model_validate(job_input_dict)
    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    # Step 1: download step should include student model, dataset, AND teacher model
    download_step = result["steps"][0]
    assert download_step["name"] == "model-and-dataset-download"
    downloads = download_step["config"]["download"]
    assert len(downloads) == 3
    assert downloads[0]["dest"] == DEFAULT_MODEL_PATH
    assert downloads[1]["dest"] == DEFAULT_DATASET_PATH
    assert downloads[2] == {
        "src": {"workspace": "meta", "name": "llama-3.1-70b-instruct"},
        "dest": DEFAULT_TEACHER_MODEL_PATH,
    }

    # Step 2: training step should have kd config populated
    training_step = result["steps"][1]
    assert training_step["config"]["backend"] == "automodel"
    training_config = training_step["config"]["training"]
    assert training_config["training_type"] == "distillation"
    assert training_config["finetuning_type"] == "all_weights"
    assert training_config["kd"] is not None
    assert training_config["kd"]["teacher_model"]["path"] == DEFAULT_TEACHER_MODEL_PATH
    assert training_config["kd"]["teacher_model"]["name"] == "meta/llama-3.1-70b-instruct"
    assert training_config["kd"]["teacher_model"]["precision"] == "bf16"
    assert training_config["kd"]["teacher_model"]["trust_remote_code"] is False
    assert training_config["kd"]["ratio"] == 0.7
    assert training_config["kd"]["temperature"] == 2.0
    assert training_config["kd"]["offload_teacher"] is False
    assert training_config["dpo"] is None


@pytest.mark.asyncio
async def test_platform_job_config_compiler_distillation_with_lora(mocker, mock_sdk, mock_auth_client):
    """Test that distillation + LoRA produces correct kd + lora config."""
    student_me = _make_mock_model_entity(fileset="fileset://default/base-model")
    teacher_me = _make_mock_model_entity(
        workspace="meta",
        name="llama-3.1-70b-instruct",
        fileset="fileset://meta/llama-3.1-70b-instruct",
    )
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        side_effect=[student_me, teacher_me],
    )

    job_input_dict = {
        "model": "default/test-target",
        "training": {
            "type": "distillation",
            "teacher_model": "meta/llama-3.1-70b-instruct",
            "peft": {"type": "lora", "rank": 16},
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 0.0001,
        },
        "dataset": "fileset://default/my-dataset",
    }
    job_input = CustomizationJobInput.model_validate(job_input_dict)
    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    training_step = result["steps"][1]
    training_config = training_step["config"]["training"]
    assert training_config["kd"] is not None
    assert training_config["lora"] is not None
    assert training_config["lora"]["rank"] == 16
    assert training_config["finetuning_type"] == "lora"


@pytest.mark.asyncio
async def test_platform_job_config_compiler_distillation_teacher_not_found(mocker, mock_sdk, mock_auth_client):
    """Test that a missing teacher model raises PlatformJobCompilationError."""
    student_me = _make_mock_model_entity()
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        side_effect=[
            student_me,
            ValueError("Model entity not found: meta/nonexistent-model. Verify the model entity exists."),
        ],
    )

    job_input_dict = {
        "model": "default/test-target",
        "training": {
            "type": "distillation",
            "teacher_model": "meta/nonexistent-model",
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 0.0001,
        },
        "dataset": "fileset://default/my-dataset",
    }
    job_input = CustomizationJobInput.model_validate(job_input_dict)
    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )

    with pytest.raises(PlatformJobCompilationError, match="not found"):
        await platform_job_config_compiler(
            "workspace",
            job_input,
            transformed_spec,
            entity_client=object(),
            job_name=job_name,
            sdk=mock_sdk,
        )


@pytest.mark.asyncio
async def test_platform_job_config_compiler_explicit_execution_profile(mocker, mock_sdk, mock_auth_client):
    """Test that an explicit execution_profile is threaded to the GPU executor."""
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=_make_mock_model_entity(),
    )
    job_input_dict = make_valid_job_input_dict()
    job_input_dict["training"]["execution_profile"] = "a100"
    job_input = CustomizationJobInput.model_validate(job_input_dict)

    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    training_step = result["steps"][1]
    assert training_step["executor"]["profile"] == "a100"


@pytest.mark.asyncio
async def test_platform_job_config_compiler_distributed_explicit_execution_profile(mocker, mock_sdk, mock_auth_client):
    """Test that an explicit execution_profile is threaded to the distributed GPU executor."""
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=_make_mock_model_entity(),
    )
    job_input_dict = make_valid_job_input_dict()
    job_input_dict["training"]["parallelism"] = {"num_nodes": 2, "num_gpus_per_node": 4}
    job_input_dict["training"]["batch_size"] = 8
    job_input_dict["training"]["execution_profile"] = "high_priority"
    job_input = CustomizationJobInput.model_validate(job_input_dict)

    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    training_step = result["steps"][1]
    assert training_step["executor"]["provider"] == "gpu_distributed"
    assert training_step["executor"]["profile"] == "high_priority"


@pytest.mark.asyncio
async def test_platform_job_config_compiler_config_default_execution_profile(mocker, mock_sdk, mock_auth_client):
    """Test that the service-level default_execution_profile is used when user omits execution_profile."""
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=_make_mock_model_entity(),
    )
    mocker.patch("nmp.customizer.app.jobs.training.compiler.config.default_training_execution_profile", "a100")
    job_input = make_valid_job_input()

    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    training_step = result["steps"][1]
    assert training_step["executor"]["profile"] == "a100"


@pytest.mark.asyncio
async def test_platform_job_config_compiler_user_profile_overrides_config_default(mocker, mock_sdk, mock_auth_client):
    """Test that a user-specified execution_profile takes precedence over the config default."""
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=_make_mock_model_entity(),
    )
    mocker.patch("nmp.customizer.app.jobs.training.compiler.config.default_training_execution_profile", "a100")
    job_input_dict = make_valid_job_input_dict()
    job_input_dict["training"]["execution_profile"] = "spot"
    job_input = CustomizationJobInput.model_validate(job_input_dict)

    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )

    training_step = result["steps"][1]
    assert training_step["executor"]["profile"] == "spot"


def test_execution_profile_rejects_empty_string():
    """Empty string execution_profile is rejected at schema validation."""
    job_input_dict = make_valid_job_input_dict()
    job_input_dict["training"]["execution_profile"] = ""
    with pytest.raises(Exception, match="String should have at least 1 character"):
        CustomizationJobInput.model_validate(job_input_dict)


@pytest.mark.parametrize(
    ("model_name", "spec", "expected"),
    [
        ("nvidia/llama-nemotron-embed-1b-v2", None, True),
        (
            "nvidia/llama-nemotron-embed-1b-v2",
            SimpleNamespace(is_embedding_model=False, model_fields_set=set()),
            True,
        ),
        (
            "nvidia/llama-nemotron-embed-1b-v2",
            SimpleNamespace(is_embedding_model=False, model_fields_set={"is_embedding_model"}),
            False,
        ),
        (
            "meta/llama-3.1-8b-instruct",
            SimpleNamespace(is_embedding_model=True, model_fields_set={"is_embedding_model"}),
            True,
        ),
    ],
)
def test_resolve_is_embedding_model_with_legacy_and_explicit_specs(
    model_name: str, spec: object, expected: bool
) -> None:
    me = SimpleNamespace(name=model_name, spec=spec)
    assert _resolve_is_embedding_model(me) is expected


@pytest.mark.asyncio
async def test_platform_job_config_compiler_uses_name_fallback_when_spec_flag_is_missing(
    mocker, mock_sdk, mock_auth_client
) -> None:
    model_entity = SimpleNamespace(
        name="team/awesome-embed-model",
        fileset="fileset://default/base-model",
        trust_remote_code=False,
        spec=SimpleNamespace(
            is_embedding_model=False,
            model_fields_set=set(),
            chat_template=None,
            tool_call_config=None,
            checkpoint_model_name="base-embed-model",
        ),
    )
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=model_entity,
    )

    job_input_dict = make_valid_job_input_dict()
    del job_input_dict["training"]["peft"]
    job_input = CustomizationJobInput.model_validate(job_input_dict)
    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )
    training_step = result["steps"][1]
    assert training_step["config"]["model"]["is_embedding_model"] is True


@pytest.mark.asyncio
async def test_platform_job_config_compiler_passes_chat_template_from_model_spec(
    mocker, mock_sdk, mock_auth_client
) -> None:
    """Chat template from model entity spec flows to training config AND output fileset metadata."""
    custom_template = "{% for message in messages %}{{ message.content }}{% endfor %}"
    model_entity = SimpleNamespace(
        name="default/test-target",
        fileset="fileset://default/base-model",
        trust_remote_code=False,
        spec=SimpleNamespace(
            checkpoint_model_name="test-model",
            chat_template=custom_template,
            tool_call_config=SimpleNamespace(
                tool_call_parser="llama3_json",
                tool_call_plugin=None,
                auto_tool_choice=True,
            ),
            is_embedding_model=False,
            model_fields_set={"is_embedding_model", "chat_template"},
        ),
    )
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=model_entity,
    )

    job_input = make_valid_job_input()
    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )
    training_step = result["steps"][1]
    assert training_step["config"]["model"]["chat_template"] == custom_template

    # Verify tool_calling metadata is propagated to the upload step
    upload_step = next(s for s in result["steps"] if s["name"] == "model-upload")
    upload_metadata = upload_step["config"]["upload"][0]["metadata"]
    assert upload_metadata == {
        "tool_calling": {
            "chat_template": custom_template,
            "tool_call_parser": "llama3_json",
            "auto_tool_choice": True,
        },
    }


@pytest.mark.asyncio
async def test_platform_job_config_compiler_chat_template_none_when_spec_missing(
    mocker, mock_sdk, mock_auth_client
) -> None:
    """Chat template is None when model entity has no spec; upload metadata is also None."""
    model_entity = SimpleNamespace(
        name="default/test-target",
        fileset="fileset://default/base-model",
        trust_remote_code=False,
        spec=None,
    )
    mocker.patch(
        "nmp.customizer.app.jobs.compiler.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=model_entity,
    )

    job_input = make_valid_job_input()
    transformed_spec, job_name = await _compiler_args_async(
        job_input, "workspace", entity_client=object(), sdk=mock_sdk
    )
    result = await platform_job_config_compiler(
        "workspace",
        job_input,
        transformed_spec,
        entity_client=object(),
        job_name=job_name,
        sdk=mock_sdk,
    )
    training_step = result["steps"][1]
    assert training_step["config"]["model"]["chat_template"] is None

    upload_step = next(s for s in result["steps"] if s["name"] == "model-upload")
    assert upload_step["config"]["upload"][0]["metadata"] is None


class TestBuildOutputFilesetMetadata:
    """Tests for _build_output_fileset_metadata function."""

    def test_returns_none_when_spec_is_none(self):
        me = SimpleNamespace(spec=None)
        assert _build_output_fileset_metadata(me) is None

    def test_returns_none_when_spec_has_no_relevant_fields(self):
        me = SimpleNamespace(spec=SimpleNamespace(chat_template=None, tool_call_config=None))
        assert _build_output_fileset_metadata(me) is None

    def test_propagates_chat_template_only(self):
        me = SimpleNamespace(
            spec=SimpleNamespace(
                chat_template="{% for m in messages %}{{ m.content }}{% endfor %}",
                tool_call_config=None,
            ),
        )
        result = _build_output_fileset_metadata(me)
        assert result == {
            "tool_calling": {
                "chat_template": "{% for m in messages %}{{ m.content }}{% endfor %}",
            },
        }

    def test_propagates_tool_call_config_only(self):
        me = SimpleNamespace(
            spec=SimpleNamespace(
                chat_template=None,
                tool_call_config=SimpleNamespace(
                    tool_call_parser="hermes",
                    tool_call_plugin="ws/my-plugin",
                    auto_tool_choice=False,
                ),
            ),
        )
        result = _build_output_fileset_metadata(me)
        assert result == {
            "tool_calling": {
                "tool_call_parser": "hermes",
                "tool_call_plugin": "ws/my-plugin",
                "auto_tool_choice": False,
            },
        }

    def test_propagates_all_fields(self):
        me = SimpleNamespace(
            spec=SimpleNamespace(
                chat_template="my-template",
                tool_call_config=SimpleNamespace(
                    tool_call_parser="llama3_json",
                    tool_call_plugin=None,
                    auto_tool_choice=True,
                ),
            ),
        )
        result = _build_output_fileset_metadata(me)
        assert result == {
            "tool_calling": {
                "chat_template": "my-template",
                "tool_call_parser": "llama3_json",
                "auto_tool_choice": True,
            },
        }


class TestAppendDownloadIfPresent:
    """Tests for _append_download_if_present function."""

    @pytest.mark.parametrize(
        "ref",
        [
            None,
            "",
        ],
        ids=["none", "empty_string"],
    )
    def test_does_not_append_when_ref_is_empty(self, ref: str | None):
        downloads: list[DownloadItem] = []

        _append_download_if_present(downloads, fileset_name=ref, dest="model", field_name="test")

        assert downloads == []

    @pytest.mark.parametrize(
        ("ref", "expected_workspace", "expected_name"),
        [
            ("fileset://default/my-model", "default", "my-model"),
            ("fileset://workspace-a/nested/path/name", "workspace-a", "nested/path/name"),
            ("default/my-dataset", "default", "my-dataset"),
        ],
        ids=["fileset_protocol", "fileset_with_nested_path", "plain_format"],
    )
    def test_appends_download_item_for_valid_ref(self, ref: str, expected_workspace: str, expected_name: str):
        downloads: list[DownloadItem] = []

        _append_download_if_present(downloads, fileset_name=ref, dest="output_dir", field_name="model")

        assert len(downloads) == 1
        assert downloads[0] == DownloadItem(
            src=FileSetRef(workspace=expected_workspace, name=expected_name),
            dest="output_dir",
        )

    def test_appends_to_existing_list(self):
        existing_item = DownloadItem(src=FileSetRef(workspace="ws1", name="existing"), dest="existing_dir")
        downloads: list[DownloadItem] = [existing_item]

        _append_download_if_present(downloads, fileset_name="fileset://ws2/new-item", dest="new_dir", field_name="new")

        assert len(downloads) == 2
        assert downloads[0] == existing_item
        assert downloads[1] == DownloadItem(src=FileSetRef(workspace="ws2", name="new-item"), dest="new_dir")


class TestBuildFileDownloadConfig:
    """Tests for _build_file_download_config function."""

    def test_with_model_entity_and_dataset(self, mock_sdk):
        """Test with model_entity and dataset; model fileset comes from fetched ModelEntity."""
        job_input = CustomizationJobInput.model_validate(make_valid_job_input_dict())
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)
        me = _make_mock_model_entity(fileset="fileset://default/base-model")

        result = _build_file_download_config(transformed_spec, me)

        expected = {
            "download": [
                {"src": {"workspace": "default", "name": "base-model"}, "dest": DEFAULT_MODEL_PATH},
                {"src": {"workspace": "default", "name": "my-dataset"}, "dest": DEFAULT_DATASET_PATH},
            ],
            "upload": [],
        }
        assert result.model_dump(mode="json") == expected

    def test_with_model_urn_and_no_fileset(self, mock_sdk):
        """Test with model as URN string; only dataset is downloaded when ModelEntity has no fileset."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["model"] = "default/some-target"
        transformed_spec = make_valid_job_output(CustomizationJobInput.model_validate(job_input_dict), sdk=mock_sdk)
        me = _make_mock_model_entity(workspace="default", name="some-target", fileset="")

        result = _build_file_download_config(transformed_spec, me)

        expected = {
            "download": [
                {"src": {"workspace": "default", "name": "my-dataset"}, "dest": DEFAULT_DATASET_PATH},
            ],
            "upload": [],
        }
        assert result.model_dump(mode="json") == expected

    def test_with_different_workspaces(self, mock_sdk):
        """Test with model and dataset from different workspaces."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["model"] = "workspace-a/model-v1"
        job_input_dict["dataset"] = "fileset://workspace-b/training-data"
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        me = _make_mock_model_entity(
            workspace="workspace-a",
            name="model-v1",
            fileset="fileset://workspace-a/model-v1",
        )
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)
        result = _build_file_download_config(transformed_spec, me)

        expected = {
            "download": [
                {"src": {"workspace": "workspace-a", "name": "model-v1"}, "dest": DEFAULT_MODEL_PATH},
                {"src": {"workspace": "workspace-b", "name": "training-data"}, "dest": DEFAULT_DATASET_PATH},
            ],
            "upload": [],
        }
        assert result.model_dump(mode="json") == expected

    def test_with_teacher_model_entity(self, mock_sdk):
        """Test that teacher model is included in downloads for distillation jobs."""
        job_input = CustomizationJobInput.model_validate(make_valid_job_input_dict())
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)
        me = _make_mock_model_entity(fileset="fileset://default/base-model")
        teacher_me = _make_mock_model_entity(
            workspace="meta",
            name="llama-3.1-70b-instruct",
            fileset="fileset://meta/llama-3.1-70b-instruct",
        )

        result = _build_file_download_config(transformed_spec, me, teacher_me)

        expected = {
            "download": [
                {"src": {"workspace": "default", "name": "base-model"}, "dest": DEFAULT_MODEL_PATH},
                {"src": {"workspace": "default", "name": "my-dataset"}, "dest": DEFAULT_DATASET_PATH},
                {"src": {"workspace": "meta", "name": "llama-3.1-70b-instruct"}, "dest": DEFAULT_TEACHER_MODEL_PATH},
            ],
            "upload": [],
        }
        assert result.model_dump(mode="json") == expected

    def test_without_teacher_model_entity(self, mock_sdk):
        """Test that no teacher download is added when teacher_me is None."""
        job_input = CustomizationJobInput.model_validate(make_valid_job_input_dict())
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)
        me = _make_mock_model_entity(fileset="fileset://default/base-model")

        result = _build_file_download_config(transformed_spec, me)

        assert len(result.download) == 2


class TestBuildModelEntityConfig:
    """Tests for _build_model_entity_config function."""

    def test_basic_model_entity_config(self, mock_sdk):
        """Test creating model entity config with basic parameters."""
        transformed_spec = make_valid_job_output(sdk=mock_sdk)

        result = _build_model_entity_config("default", transformed_spec)

        assert result.name == transformed_spec.output.name
        assert result.description == "Customized model from job"
        assert result.fileset.workspace is None
        assert result.fileset.name == transformed_spec.output.fileset
        assert result.base_model == "default/test-target"
        assert result.peft is not None
        assert result.peft.type == FinetuningType.LORA

    def test_model_entity_config_with_lora_params(self, mock_sdk):
        """Test model entity config with LoRA parameters."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["training"]["peft"] = {"type": "lora", "alpha": 16}
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _build_model_entity_config("default", transformed_spec)

        assert result.peft is not None
        assert result.peft.type == FinetuningType.LORA
        assert result.peft.alpha == 16
        assert result.peft.rank == 8

    def test_model_entity_config_with_full_finetuning(self, mock_sdk):
        """Test model entity config with full finetuning (all_weights)."""
        job_input_dict = make_valid_job_input_dict()
        del job_input_dict["training"]["peft"]
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _build_model_entity_config("default", transformed_spec)

        assert result.peft is None

    def test_model_entity_config_with_lora_merged(self, mock_sdk):
        """Test model entity config with LoRA merge=True produces lora_merged finetuning type."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["training"]["peft"] = {"type": "lora", "merge": True}
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _build_model_entity_config("default", transformed_spec)

        assert result.peft is not None
        assert result.peft.type == FinetuningType.LORA_MERGED
        assert result.peft.alpha == 32
        assert result.peft.rank == 8

    def test_model_entity_config_extracts_correct_base_model(self, mock_sdk):
        """Test that base_model is correctly extracted from model_entity."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["model"] = "my-workspace/my-model-v2"
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _build_model_entity_config("default", transformed_spec)

        assert result.base_model == "my-workspace/my-model-v2"

    def test_model_entity_config_with_custom_output(self, mock_sdk):
        """Test model entity config with user-provided output name."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["output"] = {"name": "my-custom-model"}
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        transformed_spec = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _build_model_entity_config("default", transformed_spec)

        assert result.name == "my-custom-model"
        assert result.fileset.name == transformed_spec.output.fileset


class TestValidateDeploymentConfig:
    """Tests for _validate_deployment_config."""

    async def _make_spec_with_deployment_config(
        self,
        mock_sdk,
        *,
        deployment_config,
        peft=None,
        training_type="sft",
    ):
        """Build a CustomizationJobOutput with a specific deployment_config."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["training"]["type"] = training_type
        if peft is not None:
            job_input_dict["training"]["peft"] = peft
        elif "peft" in job_input_dict["training"]:
            del job_input_dict["training"]["peft"]
        job_input_dict["deployment_config"] = deployment_config
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        return await make_valid_job_output_async(job_input, sdk=mock_sdk)

    @pytest.mark.asyncio
    async def test_none_deployment_config_passes(self, mock_sdk, mock_auth_client):
        """No deployment_config is always valid."""
        spec = await self._make_spec_with_deployment_config(mock_sdk, deployment_config=None)
        await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

    @pytest.mark.asyncio
    async def test_inline_deployment_config_passes(self, mock_sdk, mock_auth_client):
        """Inline DeploymentParams are not validated here (schema handles Case 1)."""
        spec = await self._make_spec_with_deployment_config(
            mock_sdk,
            deployment_config={"lora_enabled": True},
            peft={"type": "lora"},
        )
        await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

    @pytest.mark.asyncio
    async def test_inline_tool_call_plugin_permission_denied(self, mock_sdk, mock_auth_client):
        """Inline deployment_config with tool_call_plugin requires models.tool-call-plugin.set."""
        spec = await self._make_spec_with_deployment_config(
            mock_sdk,
            deployment_config={
                "lora_enabled": True,
                "tool_call_config": {"tool_call_plugin": "default/my-plugin"},
            },
            peft={"type": "lora"},
        )
        mock_auth_client.has_permissions.return_value = False

        with pytest.raises(PlatformJobCompilationError, match="Insufficient permissions to set tool_call_plugin"):
            await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

        mock_auth_client.has_permissions.assert_awaited_once_with("default", ["models.tool-call-plugin.set"])

    @pytest.mark.asyncio
    async def test_case4_lora_string_ref_lora_disabled_rejected(self, mocker, mock_sdk, mock_auth_client):
        """LoRA job + string config ref with lora_enabled=False should be rejected."""
        spec = await self._make_spec_with_deployment_config(
            mock_sdk,
            deployment_config="my-config",
            peft={"type": "lora"},
        )

        mock_config = mocker.Mock()
        mock_config.model_spec = mocker.Mock(lora_enabled=False)
        mock_config.model_entity_id = None
        mock_sdk.inference = mocker.Mock()
        mock_sdk.inference.deployment_configs = mocker.Mock()
        mock_sdk.inference.deployment_configs.retrieve = mocker.AsyncMock(return_value=mock_config)

        with pytest.raises(PlatformJobCompilationError, match="lora_enabled=false"):
            await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

    @pytest.mark.asyncio
    async def test_case4_lora_string_ref_lora_enabled_passes(self, mocker, mock_sdk, mock_auth_client):
        """LoRA job + string config ref with lora_enabled=True should pass."""
        spec = await self._make_spec_with_deployment_config(
            mock_sdk,
            deployment_config="my-config",
            peft={"type": "lora"},
        )

        mock_config = mocker.Mock()
        mock_config.model_spec = mocker.Mock(lora_enabled=True)
        mock_config.model_entity_id = None
        mock_sdk.inference = mocker.Mock()
        mock_sdk.inference.deployment_configs = mocker.Mock()
        mock_sdk.inference.deployment_configs.retrieve = mocker.AsyncMock(return_value=mock_config)

        await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

    @pytest.mark.asyncio
    async def test_case2_sft_string_ref_new_model_rejected(self, mocker, mock_sdk, mock_auth_client):
        """SFT job + string config ref when output model doesn't exist should be rejected."""
        spec = await self._make_spec_with_deployment_config(
            mock_sdk,
            deployment_config="my-config",
            peft=None,
        )

        mock_config = mocker.Mock()
        mock_config.model_spec = mocker.Mock(lora_enabled=True)
        mock_config.model_entity_id = "default/other-model"
        mock_sdk.inference = mocker.Mock()
        mock_sdk.inference.deployment_configs = mocker.Mock()
        mock_sdk.inference.deployment_configs.retrieve = mocker.AsyncMock(return_value=mock_config)

        mock_sdk.models.retrieve = mocker.AsyncMock(
            side_effect=NotFoundError(
                message="Not found",
                response=mocker.Mock(status_code=404),
                body=None,
            )
        )

        with pytest.raises(PlatformJobCompilationError, match="cannot be a string reference"):
            await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

    @pytest.mark.asyncio
    async def test_case2a_sft_string_ref_retarget_matching_passes(self, mocker, mock_sdk, mock_auth_client):
        """SFT retarget + string ref pointing to correct model should pass."""
        output_name = "my-output-model"
        job_input_dict = make_valid_job_input_dict()
        del job_input_dict["training"]["peft"]
        job_input_dict["output"] = {"name": output_name}
        job_input_dict["deployment_config"] = "my-config"
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        spec = await make_valid_job_output_async(job_input, sdk=mock_sdk)

        mock_config = mocker.Mock()
        mock_config.model_spec = mocker.Mock(
            lora_enabled=True,
            model_name=output_name,
            model_namespace="default",
        )
        mock_config.model_entity_id = f"default/{output_name}"
        mock_sdk.inference = mocker.Mock()
        mock_sdk.inference.deployment_configs = mocker.Mock()
        mock_sdk.inference.deployment_configs.retrieve = mocker.AsyncMock(return_value=mock_config)

        mock_existing_me = mocker.Mock()
        mock_existing_me.name = output_name
        mock_existing_me.workspace = "default"
        mock_sdk.models.retrieve = mocker.AsyncMock(return_value=mock_existing_me)

        await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

    @pytest.mark.asyncio
    async def test_case2a_sft_string_ref_retarget_mismatch_rejected(self, mocker, mock_sdk, mock_auth_client):
        """SFT retarget + string ref pointing to wrong model should be rejected."""
        output_name = "my-output-model"
        job_input_dict = make_valid_job_input_dict()
        del job_input_dict["training"]["peft"]
        job_input_dict["output"] = {"name": output_name}
        job_input_dict["deployment_config"] = "my-config"
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        spec = await make_valid_job_output_async(job_input, sdk=mock_sdk)

        mock_config = mocker.Mock()
        mock_config.model_spec = mocker.Mock(
            lora_enabled=True,
            model_name="wrong-model",
            model_namespace="default",
        )
        mock_config.model_entity_id = "default/wrong-model"
        mock_sdk.inference = mocker.Mock()
        mock_sdk.inference.deployment_configs = mocker.Mock()
        mock_sdk.inference.deployment_configs.retrieve = mocker.AsyncMock(return_value=mock_config)

        mock_existing_me = mocker.Mock()
        mock_existing_me.name = output_name
        mock_existing_me.workspace = "default"
        mock_sdk.models.retrieve = mocker.AsyncMock(return_value=mock_existing_me)

        with pytest.raises(PlatformJobCompilationError, match="targets a different model entity"):
            await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)

    @pytest.mark.asyncio
    async def test_nonexistent_config_ref_rejected(self, mocker, mock_sdk, mock_auth_client):
        """String ref to a deployment config that doesn't exist should be rejected."""
        spec = await self._make_spec_with_deployment_config(
            mock_sdk,
            deployment_config="nonexistent-config",
            peft={"type": "lora"},
        )

        mock_sdk.inference = mocker.Mock()
        mock_sdk.inference.deployment_configs = mocker.Mock()
        mock_sdk.inference.deployment_configs.retrieve = mocker.AsyncMock(
            side_effect=NotFoundError(
                message="Not found",
                response=mocker.Mock(status_code=404),
                body=None,
            )
        )

        with pytest.raises(PlatformJobCompilationError, match="does not exist"):
            await _validate_deployment_config("default", spec, mock_sdk, mock_auth_client)


class TestCollectIntegrationSecretEnvs:
    """Tests for _collect_integration_secret_envs function."""

    def test_no_integrations(self, mock_sdk):
        """Returns empty list when no integrations are configured."""
        job_output = make_valid_job_output(make_valid_job_input(), sdk=mock_sdk)
        assert job_output.integrations is None

        result = _collect_integration_secret_envs(job_output)

        assert result == []

    def test_wandb_without_secret(self, mock_sdk):
        """Returns empty list when W&B is configured but no secret is provided."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["integrations"] = {
            "wandb": {"project": "my-project"},
        }
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        job_output = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _collect_integration_secret_envs(job_output)

        assert result == []

    def test_wandb_with_secret(self, mock_sdk):
        """Returns WANDB_API_KEY env var with from_secret when secret is provided."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["integrations"] = {
            "wandb": {
                "project": "my-project",
                "api_key_secret": "my-wandb-secret",
            },
        }
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        job_output = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _collect_integration_secret_envs(job_output)

        assert len(result) == 1
        assert result[0] == {
            "name": "WANDB_API_KEY",
            "from_secret": {"name": "my-wandb-secret"},
        }

    def test_wandb_with_workspace_qualified_secret(self, mock_sdk):
        """Handles workspace/secret_name format correctly."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["integrations"] = {
            "wandb": {
                "api_key_secret": "my-workspace/my-wandb-secret",
            },
        }
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        job_output = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _collect_integration_secret_envs(job_output)

        assert len(result) == 1
        assert result[0] == {
            "name": "WANDB_API_KEY",
            "from_secret": {"name": "my-workspace/my-wandb-secret"},
        }

    def test_mlflow_only_no_secrets(self, mock_sdk):
        """Returns empty list when only MLflow is configured (no secret support yet)."""
        job_input_dict = make_valid_job_input_dict()
        job_input_dict["integrations"] = {
            "mlflow": {"experiment_name": "my-experiment"},
        }
        job_input = CustomizationJobInput.model_validate(job_input_dict)
        job_output = make_valid_job_output(job_input, sdk=mock_sdk)

        result = _collect_integration_secret_envs(job_output)

        assert result == []


class TestTranslateTrainingConfig:
    """Tests for _translate_training_config function."""

    def test_sft_produces_no_kd(self):
        """SFT training should produce kd=None."""
        from nmp.customizer.api.v2.jobs.schemas import SFTTraining

        training = SFTTraining(epochs=1, batch_size=4, learning_rate=0.0001)
        me = SimpleNamespace(trust_remote_code=False, spec=None)
        result = _translate_training_config(training, me)
        assert result.kd is None
        assert result.training_type.value == "sft"

    def test_distillation_produces_kd_config(self):
        """Distillation training should produce a populated DistillationConfig."""
        from nmp.customizer.api.v2.jobs.schemas import DistillationTraining

        training = DistillationTraining(
            teacher_model="meta/llama-3.1-70b-instruct",
            teacher_precision="fp16",
            distillation_ratio=0.8,
            distillation_temperature=3.0,
            epochs=1,
            batch_size=4,
            learning_rate=0.0001,
        )
        me = SimpleNamespace(trust_remote_code=False, spec=None)
        teacher_me = SimpleNamespace(trust_remote_code=True)

        result = _translate_training_config(training, me, teacher_me=teacher_me)

        assert result.training_type.value == "distillation"
        assert result.kd is not None
        assert isinstance(result.kd, DistillationConfig)
        assert result.kd.teacher_model.path == DEFAULT_TEACHER_MODEL_PATH
        assert result.kd.teacher_model.name == "meta/llama-3.1-70b-instruct"
        assert result.kd.teacher_model.precision.value == "fp16"
        assert result.kd.teacher_model.trust_remote_code is True
        assert result.kd.ratio == 0.8
        assert result.kd.temperature == 3.0
        assert result.kd.offload_teacher is False

    def test_distillation_without_teacher_me_defaults_trust_remote_code(self):
        """When teacher_me is None, trust_remote_code should default to False."""
        from nmp.customizer.api.v2.jobs.schemas import DistillationTraining

        training = DistillationTraining(
            teacher_model="meta/llama-3.1-70b-instruct",
            epochs=1,
            batch_size=4,
            learning_rate=0.0001,
        )
        me = SimpleNamespace(trust_remote_code=False, spec=None)

        result = _translate_training_config(training, me, teacher_me=None)

        assert result.kd is not None
        assert result.kd.teacher_model.trust_remote_code is False

    def test_distillation_with_lora_produces_both_kd_and_lora(self):
        """Distillation + LoRA should produce both kd and lora configs."""
        from nmp.customizer.api.v2.jobs.schemas import DistillationTraining, LoRAParams

        training = DistillationTraining(
            teacher_model="meta/llama-3.1-70b-instruct",
            peft=LoRAParams(rank=16, alpha=32),
            epochs=1,
            batch_size=4,
            learning_rate=0.0001,
        )
        me = SimpleNamespace(trust_remote_code=False, spec=None)
        teacher_me = SimpleNamespace(trust_remote_code=False)

        result = _translate_training_config(training, me, teacher_me=teacher_me)

        assert result.kd is not None
        assert result.lora is not None
        assert result.lora.rank == 16
        assert result.finetuning_type == FinetuningType.LORA
