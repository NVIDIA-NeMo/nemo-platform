# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the extension FilesResource sub-resource surface.

The vendored extension ``FilesResource`` replaces the Stainless-generated one on
``NemoClient.files``. It must remain API-compatible with the generated resource
by exposing the ``filesets`` and ``otlp`` sub-resources; otherwise auto-generated
CLI commands such as ``nemo files filesets create`` fail at runtime with
``'FilesResource' object has no attribute 'filesets'``.
"""

from __future__ import annotations

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.files.client import AsyncFilesClient, FilesClient
from nemo_platform_plugin.files.client import AsyncFilesClient, FilesClient


def test_sync_files_resource_exposes_filesets_and_otlp() -> None:
    client = NemoClient(base_url="http://testserver", workspace="test")

    assert isinstance(client.files.filesets, FilesClient)
    assert isinstance(client.files.otlp, FilesClient)


def test_async_files_resource_exposes_filesets_and_otlp() -> None:
    client = AsyncNemoClient(base_url="http://testserver", workspace="test")

    assert isinstance(client.files.filesets, AsyncFilesClient)
    assert isinstance(client.files.otlp, AsyncFilesClient)
