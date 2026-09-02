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

from __future__ import annotations

from typing_extensions import TypedDict

from .compute_resource_spec_param import ComputeResourceSpecParam

__all__ = ["ComputeResourcesParam"]


class ComputeResourcesParam(TypedDict, total=False):
    """Resource requirements matching k8s ResourceRequirements format."""

    limits: ComputeResourceSpecParam
    """Resource specification."""

    num_gpus: int
    """Step requesting number of GPUs."""

    num_nodes: int
    """Number of nodes to use."""

    requests: ComputeResourceSpecParam
    """Resource specification."""

    shm_size: str
    """Shared memory (/dev/shm) size as a Kubernetes quantity (e.g.

    '1Gi', '4Gi'). Used for GPU and distributed-GPU job executors. When unset,
    defaults to 1Gi per allocated GPU.
    """
