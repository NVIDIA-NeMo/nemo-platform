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
from .kubernetes_volume import KubernetesVolume
from .kubernetes_volume_mount import KubernetesVolumeMount

__all__ = ["KubernetesJobStorageConfig"]


class KubernetesJobStorageConfig(BaseModel):
    """Configuration for persistent storage in Kubernetes jobs."""

    additional_volume_mounts: Optional[List[KubernetesVolumeMount]] = None
    """Additional volume mounts"""

    additional_volumes: Optional[List[KubernetesVolume]] = None
    """Additional volumes to mount"""

    pvc_name: Optional[str] = None
    """Persistent Volume Claim Name to use for job storage."""

    volume_permissions_image: Optional[str] = None
    """Image used to set volume permissions"""
