# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Input → canonical spec transformation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nmp.customization_common.contributor.transform import generated_output_name
from nmp.customization_common.service.platform_client import check_dataset_access, fetch_model_entity

from nemo_automodel_plugin.schema import (
    AutomodelJobInput,
    AutomodelJobOutput,
    OutputResponse,
)

if TYPE_CHECKING:
    from nemo_platform import AsyncNeMoPlatform


def _infer_output_type(input_spec: AutomodelJobInput, is_embedding_model: bool) -> str:
    if is_embedding_model:
        return "model"
    lora = input_spec.training.lora
    if input_spec.training.finetuning_type == "lora" and lora is not None and not lora.merge:
        return "adapter"
    return "model"


async def transform_input_to_output(
    input_spec: AutomodelJobInput,
    workspace: str,
    sdk: AsyncNeMoPlatform,
) -> AutomodelJobOutput:
    """Enrich submitter input into canonical AutomodelJobOutput."""
    model_entity = await fetch_model_entity(input_spec.model, workspace, sdk)
    await check_dataset_access(sdk, input_spec.dataset.training, workspace)
    if input_spec.dataset.validation:
        await check_dataset_access(sdk, input_spec.dataset.validation, workspace)

    is_embedding = bool(model_entity.spec and getattr(model_entity.spec, "is_embedding_model", False))

    output_type = _infer_output_type(input_spec, is_embedding)

    if input_spec.output is None:
        out_name = generated_output_name(input_spec.model, input_spec.dataset.training, workspace)
        fileset = out_name
    else:
        out_name = input_spec.output.name
        fileset = out_name

    output = OutputResponse(
        name=out_name,
        type=output_type,
        fileset=fileset,
        description=input_spec.output.description if input_spec.output else None,
    )

    return AutomodelJobOutput(
        name=input_spec.name,
        model=input_spec.model,
        dataset=input_spec.dataset,
        training=input_spec.training,
        schedule=input_spec.schedule,
        batch=input_spec.batch,
        optimizer=input_spec.optimizer,
        parallelism=input_spec.parallelism,
        output=output,
        integrations=input_spec.integrations,
    )
