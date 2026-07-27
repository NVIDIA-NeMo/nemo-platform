# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from data_designer_nemo.sdk_translation import async_to_sync_sdk
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.filesets import FilesetFileSystem
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient


def make_filesystem(sdk: NeMoPlatform | AsyncNeMoPlatform) -> FilesetFileSystem:
    # We MUST pass a sync FilesClient here: it forces fsspec into synchronous mode
    # (necessary because the upstream DD library calls sync fsspec APIs) AND it
    # avoids fsspec trying to reuse an AsyncNeMoPlatform on a different event loop
    return FilesetFileSystem(client=_get_files_client(sdk))


def _get_files_client(sdk: NeMoPlatform | AsyncNeMoPlatform) -> FilesClient:
    if isinstance(sdk, NeMoPlatform):
        return client_from_platform(sdk, FilesClient)

    return client_from_platform(async_to_sync_sdk(sdk), FilesClient)
