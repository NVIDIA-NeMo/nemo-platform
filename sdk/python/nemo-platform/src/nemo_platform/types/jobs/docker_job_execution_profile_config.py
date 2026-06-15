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

from ..._models import BaseModel
from .docker_job_network_config import DockerJobNetworkConfig
from .docker_job_storage_config import DockerJobStorageConfig

__all__ = ["DockerJobExecutionProfileConfig"]


class DockerJobExecutionProfileConfig(BaseModel):
    """Configuration for Docker Job execution profile."""

    cleanup_completed_jobs_immediately: Optional[bool] = None

    default_task_image: Optional[str] = None
    """Default container image for job task pods.

    Used when a job step omits container.image. When unset, falls back to the
    platform CPU tasks image
    (platform.image_registry/nmp-cpu-tasks:platform.image_tag).
    """

    env: Optional[Dict[str, str]] = None
    """Optional env vars applied to all jobs (e.g.

    HOME=/tmp). Keys must not conflict with platform-reserved names. Job steps may
    override these variables.
    """

    launcher_tool_path: Optional[str] = None
    """Path to the jobs launcher tool"""

    networking: Optional[DockerJobNetworkConfig] = None
    """Docker networking configuration"""

    storage: Optional[DockerJobStorageConfig] = None
    """Configuration for persistent storage in Docker jobs."""

    ttl_seconds_active: Optional[int] = None

    ttl_seconds_after_finished: Optional[int] = None

    ttl_seconds_before_active: Optional[int] = None
