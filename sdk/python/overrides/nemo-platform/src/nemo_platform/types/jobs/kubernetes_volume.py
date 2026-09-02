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

from typing import Union, Optional
from typing_extensions import TypeAlias

from ..._models import BaseModel
from .kubernetes_secret_volume import KubernetesSecretVolume
from .kubernetes_empty_dir_volume import KubernetesEmptyDirVolume
from .kubernetes_config_map_volume import KubernetesConfigMapVolume
from .kubernetes_persistent_volume_claim import KubernetesPersistentVolumeClaim

__all__ = ["KubernetesVolume", "UnionMember0", "UnionMember1", "UnionMember2", "UnionMember3"]


class UnionMember0(BaseModel):
    persistent_volume_claim: object

    config_map: Optional[KubernetesConfigMapVolume] = None
    """Kubernetes ConfigMap volume definition."""

    empty_dir: Optional[KubernetesEmptyDirVolume] = None
    """Kubernetes EmptyDir Volume definition."""

    name: Optional[str] = None
    """Volume Name"""

    secret: Optional[KubernetesSecretVolume] = None
    """Kubernetes Secret volume definition."""


class UnionMember1(BaseModel):
    empty_dir: object

    config_map: Optional[KubernetesConfigMapVolume] = None
    """Kubernetes ConfigMap volume definition."""

    name: Optional[str] = None
    """Volume Name"""

    persistent_volume_claim: Optional[KubernetesPersistentVolumeClaim] = None
    """Kubernetes Persistent Volume Claim definition."""

    secret: Optional[KubernetesSecretVolume] = None
    """Kubernetes Secret volume definition."""


class UnionMember2(BaseModel):
    secret: object

    config_map: Optional[KubernetesConfigMapVolume] = None
    """Kubernetes ConfigMap volume definition."""

    empty_dir: Optional[KubernetesEmptyDirVolume] = None
    """Kubernetes EmptyDir Volume definition."""

    name: Optional[str] = None
    """Volume Name"""

    persistent_volume_claim: Optional[KubernetesPersistentVolumeClaim] = None
    """Kubernetes Persistent Volume Claim definition."""


class UnionMember3(BaseModel):
    config_map: object

    empty_dir: Optional[KubernetesEmptyDirVolume] = None
    """Kubernetes EmptyDir Volume definition."""

    name: Optional[str] = None
    """Volume Name"""

    persistent_volume_claim: Optional[KubernetesPersistentVolumeClaim] = None
    """Kubernetes Persistent Volume Claim definition."""

    secret: Optional[KubernetesSecretVolume] = None
    """Kubernetes Secret volume definition."""


KubernetesVolume: TypeAlias = Union[UnionMember0, UnionMember1, UnionMember2, UnionMember3]
