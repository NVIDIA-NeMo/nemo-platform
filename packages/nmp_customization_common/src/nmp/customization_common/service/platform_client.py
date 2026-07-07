# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Async helpers for resolving model/dataset references against the platform.

Used by each plugin's ``transform.py`` (async, runs inside the FastAPI request
handler / ``to_spec`` flow) to validate that the submitter's ``model`` and
``dataset`` references exist before the job moves on to compile / run.
"""

from nemo_platform import AsyncNeMoPlatform
from nemo_platform._exceptions import NotFoundError, PermissionDeniedError
from nemo_platform.types.models import ModelEntity
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import NotFoundError as ClientNotFoundError
from nemo_platform_plugin.client.errors import PermissionDeniedError as ClientPermissionDeniedError
from nemo_platform_plugin.files.client import AsyncFilesClient
from nmp.common.entities.utils import parse_entity_ref
from nmp.customization_common.schemas.file_io import FileSetRef


async def check_dataset_access(sdk: AsyncNeMoPlatform, dataset_uri: str, default_workspace: str) -> None:
    """Verify the caller can access the dataset fileset.

    Raises:
        ValueError: If the fileset is not found.
        PermissionError: If access is denied.
    """
    ref = FileSetRef.model_validate(dataset_uri)
    workspace = ref.workspace or default_workspace
    files = client_from_platform(sdk, AsyncFilesClient)
    try:
        await files.get_fileset(workspace=workspace, name=ref.name)
    except ClientPermissionDeniedError:
        raise PermissionError(f"Access denied to dataset fileset '{workspace}/{ref.name}'") from None
    except ClientNotFoundError:
        raise ValueError(
            f"Dataset fileset '{ref.name}' not found in workspace '{workspace}'. Verify the dataset exists."
        ) from None


async def fetch_model_entity(
    model_ref: str,
    default_workspace: str,
    sdk: AsyncNeMoPlatform,
) -> ModelEntity:
    """Retrieve a model entity by reference string."""
    resolved_ref = parse_entity_ref(model_ref, default_workspace)
    try:
        return await sdk.models.retrieve(name=resolved_ref.name, workspace=resolved_ref.workspace, verbose=True)
    except PermissionDeniedError:
        raise PermissionError(f"Access denied to model '{resolved_ref.workspace}/{resolved_ref.name}'") from None
    except NotFoundError:
        raise ValueError(
            f"Model entity not found: '{resolved_ref.workspace}/{resolved_ref.name}'. Verify the model entity exists."
        ) from None
