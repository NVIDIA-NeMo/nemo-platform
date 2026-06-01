# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Utilities for customization job ID generation and input transformation."""

import uuid

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.entities import EntityClient, parse_qualified_name
from nmp.core.models.schemas import ModelEntity
from nmp.customizer.api.v2.jobs.schemas import (
    CustomizationJobInput,
    CustomizationJobOutput,
    LoRAParams,
    OutputRequest,
    OutputResponse,
)
from nmp.customizer.entities.values import OutputNameType
from nmp.customizer.platform_client import check_dataset_access, fetch_model_entity

_MAX_ENTITY_NAME_LENGTH = 63
_HEX_SUFFIX_LENGTH = 12
_RANDOM_SUFFIX_LENGTH = _HEX_SUFFIX_LENGTH + 1
_MAX_PREFIX_LENGTH = _MAX_ENTITY_NAME_LENGTH - _RANDOM_SUFFIX_LENGTH
_FILESET_PROTOCOL = "fileset://"


def _generate_random_id(prefix: str) -> str:
    """Generate a lowercase ID suitable for FileSet/entity names.

    Uses hex encoding (lowercase) to ensure compatibility.
    Format: {prefix}-{hex_encoded_uuid_first_12_chars}
    """
    truncated_prefix = prefix[:_MAX_PREFIX_LENGTH].rstrip("-")
    if not truncated_prefix:
        raise ValueError(
            f"Cannot generate ID: prefix '{prefix}' contains no valid characters. "
            "The prefix must contain at least one alphanumeric character "
            f"(after truncation to {_MAX_PREFIX_LENGTH} chars and removing trailing hyphens)."
        )
    return f"{truncated_prefix}-{uuid.uuid4().hex[:_HEX_SUFFIX_LENGTH]}"


def generate_customization_id() -> str:
    """Generate a customization job ID."""
    return _generate_random_id("customization")


def get_entity_name(entity: str | ModelEntity) -> str:
    """Extract entity name from a target reference."""
    if isinstance(entity, ModelEntity):
        return entity.name
    return parse_qualified_name(entity)[1]


def _extract_fileset_name(ref: str) -> str:
    """Extract fileset name from fileset://workspace/name, workspace/name, or name."""
    normalized_ref = ref
    if normalized_ref.startswith(_FILESET_PROTOCOL):
        normalized_ref = normalized_ref[len(_FILESET_PROTOCOL) :]
    return parse_qualified_name(normalized_ref)[1]


def _infer_output_type(input_spec: CustomizationJobInput, is_embedding_model: bool) -> OutputNameType:
    """Infer output artifact type from the training configuration.

    LoRA without merge produces an adapter; everything else produces a full model.
    Embedding models always produce a full model.
    """
    if is_embedding_model:
        return OutputNameType.MODEL
    peft = input_spec.training.peft
    if isinstance(peft, LoRAParams) and not peft.merge:
        return OutputNameType.ADAPTER
    return OutputNameType.MODEL


def _resolve_output_name(
    user_output: OutputRequest | None,
    entity_name: str,
    dataset_name: str,
) -> tuple[str, bool]:
    """Resolve the output artifact name.

    Returns:
        (name, was_auto_generated) — the resolved name and whether it was auto-generated.
    """
    if user_output is None:
        return _generate_random_id(f"{entity_name}-{dataset_name}"), True
    return user_output.name, False


async def transform_input_to_output(
    input_spec: CustomizationJobInput,
    workspace: str,
    entity_client: EntityClient,
    job_name: str | None,
    sdk: AsyncNeMoPlatform,
) -> CustomizationJobOutput:
    """Transform customization job input to output with resolved output.

    1. Auto-generate output name with '<model>-<dataset>' prefix when missing.
    2. Reuse output name as fileset when auto-generated; otherwise generate a separate fileset name.
    3. Infer output type from the training peft configuration.
    """
    del entity_client
    del job_name

    model_entity = await fetch_model_entity(input_spec.model, workspace, sdk)
    await check_dataset_access(sdk, input_spec.dataset, workspace)
    entity_name = get_entity_name(input_spec.model)
    dataset_name = _extract_fileset_name(input_spec.dataset)

    is_embedding_model = bool(model_entity.spec and model_entity.spec.is_embedding_model)
    inferred_output_type = _infer_output_type(input_spec, is_embedding_model)

    name, was_auto_generated = _resolve_output_name(input_spec.output, entity_name, dataset_name)
    fileset = name if was_auto_generated else _generate_random_id(name)

    output = OutputResponse(name=name, type=inferred_output_type, fileset=fileset)

    return CustomizationJobOutput.model_validate(
        input_spec.model_dump(exclude={"output"})
        | {
            "output": output.model_dump(),
        }
    )
