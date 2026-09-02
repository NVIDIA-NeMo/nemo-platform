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

from typing import Optional

from ..._models import BaseModel
from .compute_resource_spec import ComputeResourceSpec

__all__ = ["ComputeResources"]


class ComputeResources(BaseModel):
    """Resource requirements matching k8s ResourceRequirements format."""

    limits: Optional[ComputeResourceSpec] = None
    """Resource specification."""

    num_gpus: Optional[int] = None
    """Step requesting number of GPUs."""

    num_nodes: Optional[int] = None
    """Number of nodes to use."""

    requests: Optional[ComputeResourceSpec] = None
    """Resource specification."""

    shm_size: Optional[str] = None
    """Shared memory (/dev/shm) size as a Kubernetes quantity (e.g.

    '1Gi', '4Gi'). Used for GPU and distributed-GPU job executors. When unset,
    defaults to 1Gi per allocated GPU.
    """
