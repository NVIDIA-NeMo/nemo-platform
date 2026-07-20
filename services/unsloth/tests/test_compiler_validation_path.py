# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression: validation fileset refs must resolve to on-disk paths in the training step."""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from nmp.unsloth.app.constants import DEFAULT_DATASET_PATH, DEFAULT_VALIDATION_DATASET_PATH
from nmp.unsloth.app.jobs.compiler import platform_job_config_compiler
from nmp.unsloth.schemas import (
    DatasetSpec,
    LoRAParams,
    ModelLoadSpec,
    OutputResponse,
    ScheduleSpec,
    TrainingSpec,
    UnslothJobOutput,
)


def _spec(*, validation_path: str | None) -> UnslothJobOutput:
    return UnslothJobOutput(
        model=ModelLoadSpec(name="default/qwen3-1.7b"),
        dataset=DatasetSpec(
            path="default/commonsense_qa",
            validation_path=validation_path,
            apply_chat_template=True,
        ),
        training=TrainingSpec(lora=LoRAParams()),
        schedule=ScheduleSpec(epochs=1),
        output=OutputResponse(
            name="out",
            type="adapter",
            save_method="lora",
            fileset="out",
        ),
    )


@pytest.mark.asyncio
async def test_training_step_gets_local_validation_path_for_same_fileset() -> None:
    from nmp.unsloth.app.jobs import compiler as compiler_mod

    original_fetch = compiler_mod.fetch_model_entity
    compiler_mod.fetch_model_entity = AsyncMock(
        return_value=types.SimpleNamespace(
            workspace="default",
            name="qwen3-1.7b",
            fileset="default/qwen3-1.7b",
            trust_remote_code=False,
        ),
    )
    try:
        job = await platform_job_config_compiler(
            workspace="default",
            job_spec=_spec(validation_path="default/commonsense_qa"),
            sdk=MagicMock(),
        )
    finally:
        compiler_mod.fetch_model_entity = original_fetch

    training = next(s for s in job["steps"] if s["name"] == "training")
    assert training["config"]["validation_path"] == DEFAULT_DATASET_PATH

    download = next(s for s in job["steps"] if s["name"] == "model-and-dataset-download")
    assert len(download["config"]["download"]) == 2


@pytest.mark.asyncio
async def test_training_step_gets_separate_validation_path_for_different_fileset() -> None:
    from nmp.unsloth.app.jobs import compiler as compiler_mod

    original_fetch = compiler_mod.fetch_model_entity
    compiler_mod.fetch_model_entity = AsyncMock(
        return_value=types.SimpleNamespace(
            workspace="default",
            name="qwen3-1.7b",
            fileset="default/qwen3-1.7b",
            trust_remote_code=False,
        ),
    )
    try:
        job = await platform_job_config_compiler(
            workspace="default",
            job_spec=_spec(validation_path="default/commonsense_qa_val"),
            sdk=MagicMock(),
        )
    finally:
        compiler_mod.fetch_model_entity = original_fetch

    training = next(s for s in job["steps"] if s["name"] == "training")
    assert training["config"]["validation_path"] == DEFAULT_VALIDATION_DATASET_PATH

    download = next(s for s in job["steps"] if s["name"] == "model-and-dataset-download")
    assert len(download["config"]["download"]) == 3


@pytest.mark.asyncio
async def test_upload_step_stamps_output_metadata() -> None:
    from nmp.unsloth.app.jobs import compiler as compiler_mod

    original_fetch = compiler_mod.fetch_model_entity
    compiler_mod.fetch_model_entity = AsyncMock(
        return_value=types.SimpleNamespace(
            workspace="default",
            name="qwen3-1.7b",
            fileset="default/qwen3-1.7b",
            trust_remote_code=False,
        ),
    )
    try:
        job = await platform_job_config_compiler(
            workspace="default",
            job_spec=_spec(validation_path=None),
            sdk=MagicMock(),
        )
    finally:
        compiler_mod.fetch_model_entity = original_fetch

    upload = next(s for s in job["steps"] if s["name"] == "model-upload")
    assert upload["config"]["upload"][0]["metadata"] is None
