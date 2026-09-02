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

from typing import Dict, Optional
from typing_extensions import Literal

from ..._models import BaseModel

__all__ = ["DockerVolumeMount"]


class DockerVolumeMount(BaseModel):
    mount_path: str
    """Path inside the container where the volume will be mounted"""

    volume_name: str
    """Name of the Docker volume to mount"""

    allow_create_volume: Optional[bool] = None
    """
    Whether to allow the creation of the volume if it does not exist (default:
    false).
    """

    kind: Optional[Literal["volume", "tmpfs"]] = None
    """Type of the Docker volume to mount.

    Options are 'volume' or 'tmpfs' (default: 'volume'). tmpfs volumes are only
    supported on Linux hosts.
    """

    options: Optional[Dict[str, object]] = None
    """Additional options for the volume"""
