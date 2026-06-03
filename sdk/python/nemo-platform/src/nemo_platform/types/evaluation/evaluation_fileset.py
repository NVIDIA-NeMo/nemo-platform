# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing import Dict, Union, Optional
from typing_extensions import TypeAlias

from ..._models import BaseModel
from ..shared.fileset_metadata import FilesetMetadata
from ..files.ngc_storage_config import NGCStorageConfig
from ..files.huggingface_storage_config import HuggingfaceStorageConfig

__all__ = ["EvaluationFileset", "Storage"]

Storage: TypeAlias = Union[NGCStorageConfig, HuggingfaceStorageConfig]


class EvaluationFileset(BaseModel):
    """Fileset definition for use without persisting to the Files API."""

    storage: Storage
    """The storage configuration for the fileset."""

    custom_fields: Optional[Dict[str, object]] = None
    """Custom fields for the fileset."""

    metadata: Optional[FilesetMetadata] = None
    """Tagged metadata container - the key indicates the type.

    Example: metadata = FilesetMetadata( dataset=DatasetMetadataContent(
    schema={"columns": ["id", "name"]}, ) )
    """

    path: Optional[str] = None
    """The relative path to file/directory in the storage."""
