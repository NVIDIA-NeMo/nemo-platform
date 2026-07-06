# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging

import data_designer.config as dd
from data_designer.config.seed_source import SeedSource
from data_designer_nemo.errors import NDDInternalError, NDDInvalidConfigError
from data_designer_nemo.fileset_file_seed_source import FilesetFileSeedSource
from data_designer_nemo.secret_resolver import validate_secret
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import NotFoundError, PermissionDeniedError
from nemo_platform_plugin.files.client import AsyncFilesClient

logger = logging.getLogger(__name__)


def get_seed_source(dd_config: dd.DataDesignerConfig) -> SeedSource | None:
    return dd_config.seed_config.source if dd_config.seed_config else None


async def validate_seed(dd_config: dd.DataDesignerConfig, workspace: str, sdk: AsyncNeMoPlatform) -> None:
    if (seed_source := get_seed_source(dd_config)) is None:
        return None

    if isinstance(seed_source, dd.HuggingFaceSeedSource) and (token := seed_source.token) is not None:
        await validate_secret(sdk, token, workspace)
        return None

    if isinstance(seed_source, FilesetFileSeedSource):
        workspace, fileset_name = _parse_seed_source_path(seed_source.path, workspace)
        files = client_from_platform(sdk, AsyncFilesClient)
        try:
            await files.get_fileset(name=fileset_name, workspace=workspace)
        except NotFoundError as e:
            raise NDDInvalidConfigError(f"Could not find fileset {fileset_name!r} in workspace {workspace!r}") from e
        except PermissionDeniedError as e:
            raise NDDInvalidConfigError(f"Access denied to workspace {workspace!r}") from e
        except Exception as e:
            logger.exception("Error retrieving fileset", extra={"fileset_name": fileset_name, "workspace": workspace})
            raise NDDInternalError(
                f"An unexpected error occurred while retrieving fileset {fileset_name!r} in workspace {workspace!r}: {e}"
            ) from e


def _parse_seed_source_path(path: str, request_workspace: str) -> tuple[str, str]:
    provided_fileset = path.split("#")[0]
    match provided_fileset.split("/"):
        case [name]:
            return request_workspace, name
        case [workspace, name]:
            return workspace, name
        case _:
            raise NDDInvalidConfigError(
                f"The fileset reference {provided_fileset!r} in seed source path is formatted incorrectly"
            )
