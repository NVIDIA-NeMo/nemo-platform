# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.automodel.adapter import automodel_spec_to_compiler_output
from nmp.automodel.api.v2.jobs.schemas import CustomizationJobOutput, LoRAParams, OutputResponse, SFTTraining
from nmp.automodel.app.jobs.compiler import _build_file_download_config
from nmp.automodel.compile import platform_job_config_compiler
from nmp.automodel.images import get_tasks_image, get_training_image
from nmp.common.entities.utils import get_random_id
from nmp.common.jobs.exceptions import PlatformJobCompilationError


def _make_mock_model_entity(
    workspace: str = "default",
    name: str = "test-target",
    fileset: str | None = "default/base-model",
) -> ModelEntity:
    return ModelEntity(
        id=get_random_id("model"),
        workspace=workspace,
        name=name,
        fileset=fileset,
        trust_remote_code=False,
        finetuning_type=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def mock_sdk():
    sdk = Mock(spec=AsyncNeMoPlatform)
    sdk.models = Mock()
    sdk.models.retrieve = AsyncMock(
        side_effect=lambda name, workspace, verbose=True: _make_mock_model_entity(workspace=workspace, name=name),
    )
    sdk.files = Mock()
    sdk.files.filesets = Mock()
    sdk.files.filesets.retrieve = AsyncMock(return_value=Mock())
    return sdk


def _make_job_output() -> CustomizationJobOutput:
    return CustomizationJobOutput(
        model="default/test-target",
        dataset="default/my-dataset",
        training=SFTTraining(
            peft=LoRAParams(rank=8, alpha=32, merge=False),
            learning_rate=1e-4,
            batch_size=4,
            micro_batch_size=1,
            max_seq_length=2048,
        ),
        output=OutputResponse(name="out", type="adapter", fileset="out-fs"),
    )


def test_build_file_download_config_rejects_missing_model_fileset() -> None:
    with pytest.raises(PlatformJobCompilationError, match="has no fileset"):
        _build_file_download_config(_make_job_output(), _make_mock_model_entity(fileset=None))


def test_compile_training_step_carries_pass2_fields() -> None:
    """Pass-2 hyperparameters on the v2 SFTTraining reach the internal TrainingStepConfig."""
    from nmp.automodel.app.jobs.training.compiler import compile_training_step

    job_output = CustomizationJobOutput(
        model="default/test-target",
        dataset="default/my-dataset",
        training=SFTTraining(
            peft=LoRAParams(rank=8, alpha=32, merge=False, exclude_modules=["*.out_proj"], use_triton=False),
            learning_rate=1e-4,
            adam_eps=1e-6,
            optimizer="AdamW",
            lr_decay_style="linear",
            attn_implementation="flash_attention_2",
            batch_size=4,
            micro_batch_size=1,
            sequence_packing=True,
            sequence_packing_max_samples=256,
            max_seq_length=2048,
        ),
        output=OutputResponse(name="out", type="adapter", fileset="out-fs"),
    )
    step = compile_training_step(job_output, base_env=[], me=_make_mock_model_entity())
    cfg = step.config if hasattr(step, "config") else step["config"]

    assert cfg["optimizer"]["optimizer_name"] == "AdamW"
    assert cfg["optimizer"]["lr_decay_style"] == "linear"
    assert cfg["optimizer"]["eps"] == 1e-6
    assert cfg["model"]["attn_implementation"] == "flash_attention_2"
    assert cfg["batch"]["sequence_packing_max_samples"] == 256
    assert cfg["training"]["lora"]["exclude_modules"] == ["*.out_proj"]
    assert cfg["training"]["lora"]["use_triton"] is False


@pytest.mark.asyncio
async def test_platform_job_config_compiler_sft_lora(mock_sdk, monkeypatch):
    monkeypatch.setattr(
        "nmp.automodel.app.jobs.compiler.fetch_model_entity",
        AsyncMock(return_value=_make_mock_model_entity()),
    )
    contract_dir = Path(__file__).resolve().parent / "contract" / "input_configs"
    input_path = contract_dir / "llama-3.2-1b" / "llama_3_2_1b_lora.json"
    if not input_path.exists():
        pytest.skip("contract configs not present")

    raw = json.loads(input_path.read_text())
    plugin_shape = {
        "model": raw["model"]["path"],
        "dataset": {"training": "default/train-data"},
        "training": {
            "training_type": "sft",
            "finetuning_type": "lora",
            "lora": {
                "rank": raw["training"]["lora"]["rank"],
                "alpha": raw["training"]["lora"]["alpha"],
                "merge": False,
            },
            "max_seq_length": raw["model"]["max_seq_length"],
        },
        "schedule": {
            "epochs": raw["schedule"]["epochs"],
            "max_steps": raw["schedule"]["max_steps"],
        },
        "batch": {
            "global_batch_size": raw["batch"]["global_batch_size"],
            "micro_batch_size": raw["batch"]["micro_batch_size"],
        },
        "optimizer": {"learning_rate": raw["optimizer"]["learning_rate"]},
        "parallelism": {
            "num_nodes": raw["parallelism"]["num_nodes"],
            "num_gpus_per_node": raw["parallelism"]["num_gpus_per_node"],
            "tensor_parallel_size": raw["parallelism"]["tensor_parallel_size"],
        },
        "output": {"name": "test-out", "type": "adapter", "fileset": "test-out-fs"},
    }
    compiler_spec = automodel_spec_to_compiler_output(plugin_shape)
    spec = await platform_job_config_compiler(compiler_spec, "default", mock_sdk)

    steps = spec.steps if hasattr(spec, "steps") else spec["steps"]
    assert len(steps) == 4
    training_step = steps[1]
    training_name = training_step.name if hasattr(training_step, "name") else training_step["name"]
    assert training_name == "training"
    training_cmd = (
        training_step.executor.container.command
        if hasattr(training_step, "executor")
        else training_step["executor"]["container"]["command"]
    )
    assert "nmp.automodel.tasks.training" in " ".join(training_cmd)
    download_cmd = (
        steps[0].executor.container.command
        if hasattr(steps[0], "executor")
        else steps[0]["executor"]["container"]["command"]
    )
    assert download_cmd[-1] == "nmp.automodel.tasks.file_io"
    download_entrypoint = (
        steps[0].executor.container.entrypoint
        if hasattr(steps[0], "executor")
        else steps[0]["executor"]["container"]["entrypoint"]
    )
    assert download_entrypoint == ["/opt/venv/bin/python"]

    def _step_image(step) -> str:
        if hasattr(step, "executor"):
            return step.executor.container.image
        return step["executor"]["container"]["image"]

    assert _step_image(steps[0]) == get_tasks_image()
    assert _step_image(steps[1]) == get_training_image()
    assert _step_image(steps[2]) == get_tasks_image()
    assert _step_image(steps[3]) == get_tasks_image()
