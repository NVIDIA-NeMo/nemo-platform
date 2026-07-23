# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from data_designer_nemo.sdk_translation import async_to_sync_sdk
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.filesets import FilesetFileSystem
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient

# TODO: Update the FilesetFileSystem constructor to accept an explicit `asynchronous: bool | None`
# argument so that the fsspec asynchronous mode is not coupled to the `client`. Once that exists,
# we can drop `_get_files_client` and `_async_to_sync_sdk`, leaving us with something like:
#
# FilesetFileSystem(async_client=_get_async_files_client(sdk), asynchronous=False)


def make_filesystem(sdk: NeMoPlatform | AsyncNeMoPlatform) -> FilesetFileSystem:
    return FilesetFileSystem(client=_get_files_client(sdk))


def _get_files_client(sdk: NeMoPlatform | AsyncNeMoPlatform) -> FilesClient:
    if isinstance(sdk, NeMoPlatform):
        return client_from_platform(sdk, FilesClient)

    return client_from_platform(async_to_sync_sdk(sdk), FilesClient)
