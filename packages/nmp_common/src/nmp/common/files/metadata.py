# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Metadata types for filesets.

Re-exported from ``nemo_platform_plugin.files.metadata`` — the canonical
source of truth.  This shim keeps existing ``from nmp.common.files.metadata
import …`` statements working without changes.
"""

from nemo_platform_plugin.files.metadata import DatasetMetadataContent as DatasetMetadataContent
from nemo_platform_plugin.files.metadata import FilesetMetadata as FilesetMetadata
from nemo_platform_plugin.files.metadata import ModelMetadataContent as ModelMetadataContent
from nemo_platform_plugin.files.metadata import ToolCallingMetadataContent as ToolCallingMetadataContent
