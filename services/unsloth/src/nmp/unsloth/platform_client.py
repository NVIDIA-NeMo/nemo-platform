# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Async helpers for resolving model/dataset references against the platform.

Mirrors :mod:`nmp.automodel.platform_client`. Used by the plugin's
``transform.py`` (async, runs inside the FastAPI request handler /
``to_spec`` flow) to validate that the submitter's ``model`` and
``dataset.path`` exist before the job moves on to compile / run.

Sync download/upload helpers live in :mod:`nmp.unsloth.file_io` —
those are consumed by the plugin's ``run()`` and by future container
tasks, both of which are sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nemo_platform import AsyncNeMoPlatform
from nemo_platform._exceptions import NotFoundError, PermissionDeniedError
from nmp.common.entities.utils import parse_entity_ref
from nmp.unsloth.app.jobs.file_io.schemas import FileSetRef

if TYPE_CHECKING:
    from nemo_platform.types.models import ModelEntity


async def check_dataset_access(
    sdk: AsyncNeMoPlatform,
    dataset_uri: str,
    default_workspace: str,
) -> None:
    """Verify the caller can access the dataset fileset.

    Raises:
        ValueError: If the fileset is not found.
        PermissionError: If access is denied.
    """
    ref = FileSetRef.model_validate(dataset_uri)
    workspace = ref.workspace or default_workspace
    try:
        await sdk.files.filesets.retrieve(workspace=workspace, name=ref.name)
    except PermissionDeniedError:
        raise PermissionError(f"Access denied to dataset fileset '{workspace}/{ref.name}'") from None
    except NotFoundError:
        raise ValueError(
            f"Dataset fileset '{ref.name}' not found in workspace '{workspace}'. Verify the dataset exists."
        ) from None


async def fetch_model_entity(
    model_ref: str,
    default_workspace: str,
    sdk: AsyncNeMoPlatform,
) -> "ModelEntity":
    """Retrieve a model entity by reference string.

    Args:
        model_ref: ``"name"`` (uses ``default_workspace``) or ``"workspace/name"``.
        default_workspace: Workspace to use when the ref is bare.
        sdk: Async platform SDK handle.

    Raises:
        ValueError: If the model entity is not found.
        PermissionError: If access is denied.
    """
    resolved_ref = parse_entity_ref(model_ref, default_workspace)
    try:
        return await sdk.models.retrieve(
            name=resolved_ref.name,
            workspace=resolved_ref.workspace,
            verbose=True,
        )
    except PermissionDeniedError:
        raise PermissionError(f"Access denied to model '{resolved_ref.workspace}/{resolved_ref.name}'") from None
    except NotFoundError:
        raise ValueError(
            f"Model entity not found: '{resolved_ref.workspace}/{resolved_ref.name}'. Verify the model entity exists."
        ) from None
