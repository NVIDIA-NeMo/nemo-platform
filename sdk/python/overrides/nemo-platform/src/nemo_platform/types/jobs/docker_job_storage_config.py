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

from typing import List, Optional

from ..._models import BaseModel
from .docker_volume_mount import DockerVolumeMount

__all__ = ["DockerJobStorageConfig"]


class DockerJobStorageConfig(BaseModel):
    """Configuration for persistent storage in Docker jobs."""

    additional_volume_mounts: Optional[List[DockerVolumeMount]] = None
    """List of additional Docker volume mounts for the job"""

    volume_name: Optional[str] = None
    """Name of the Docker volume for persistent storage"""

    volume_permissions_image: Optional[str] = None
    """Docker image used to set permissions on the volume"""
