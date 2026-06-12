# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Input → canonical spec transformation."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from nemo_platform_plugin.refs import parse_entity_ref
from nmp.automodel.platform_client import check_dataset_access, fetch_model_entity

from nemo_automodel_plugin.schema import (
    AutomodelJobInput,
    AutomodelJobOutput,
    OutputResponse,
)

if TYPE_CHECKING:
    from nemo_platform import AsyncNeMoPlatform

_MAX_PREFIX_LEN = 50
_HEX_LEN = 12


def _random_suffix(prefix: str) -> str:
    truncated = prefix[:_MAX_PREFIX_LEN].rstrip("-")
    return f"{truncated}-{uuid.uuid4().hex[:_HEX_LEN]}"


def _entity_basename(model_ref: str, workspace: str) -> str:
    return parse_entity_ref(model_ref, workspace).name


def _dataset_basename(uri: str) -> str:
    normalized = uri
    if normalized.startswith("fileset://"):
        normalized = normalized[len("fileset://") :]
    return parse_entity_ref(normalized, "default").name


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
    if is_embedding:
        raise ValueError(
            "Embedding-model SFT is not supported in Automodel v1. "
            "Use a causal LM checkpoint or wait for a future release."
        )

    entity_name = _entity_basename(input_spec.model, workspace)
    dataset_name = _dataset_basename(input_spec.dataset.training)
    output_type = _infer_output_type(input_spec, is_embedding)

    if input_spec.output is None:
        out_name = _random_suffix(f"{entity_name}-{dataset_name}")
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
