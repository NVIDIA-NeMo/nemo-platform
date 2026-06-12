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

from typing import Dict, List, Optional

from ..._models import BaseModel
from .compute_resources import ComputeResources
from .image_pull_secret import ImagePullSecret
from .kubernetes_object_metadata import KubernetesObjectMetadata
from .kubernetes_job_storage_config import KubernetesJobStorageConfig

__all__ = ["KubernetesJobExecutionProfileConfig"]


class KubernetesJobExecutionProfileConfig(BaseModel):
    """Configuration for Kubernetes execution environment."""

    affinity: Optional[Dict[str, object]] = None
    """Affinity for the Kubernetes job pods."""

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

    image_pull_secrets: Optional[List[ImagePullSecret]] = None
    """Image pull secrets for the Kubernetes job pods."""

    job_metadata: Optional[KubernetesObjectMetadata] = None
    """Metadata to add to each job object in the Kubernetes job."""

    launcher_image: Optional[str] = None
    """Container image that contains the jobs-launcher binary."""

    launcher_tool_path: Optional[str] = None
    """Path to the jobs launcher tool"""

    namespace: Optional[str] = None
    """Kubernetes namespace to submit the job to.

    If not set, it will be determined from the environment.
    """

    node_selector: Optional[Dict[str, str]] = None
    """Node selector for the Kubernetes job pods."""

    num_gpus: Optional[int] = None
    """Number of GPUs to request for the job"""

    pod_metadata: Optional[KubernetesObjectMetadata] = None
    """Metadata to add to each pod in the Kubernetes job."""

    pod_security_context: Optional[Dict[str, object]] = None
    """Pod security context for the Kubernetes job pods."""

    resources: Optional[ComputeResources] = None
    """Resource requirements matching k8s ResourceRequirements format."""

    scheduler_name: Optional[str] = None
    """The scheduler name to use for the pod spec.

    When non-empty, this value is applied to the pod's schedulerName field, enabling
    custom schedulers such as KAI Scheduler. Empty string omits schedulerName so the
    cluster default scheduler is used.
    """

    service_account_name: Optional[str] = None
    """Kubernetes service account name for job pods.

    Uses the Kubernetes default service account when set to 'default'.
    """

    storage: Optional[KubernetesJobStorageConfig] = None
    """Configuration for persistent storage in Kubernetes jobs."""

    tolerations: Optional[List[Dict[str, object]]] = None
    """Tolerations for the Kubernetes job pods."""

    ttl_seconds_active: Optional[int] = None

    ttl_seconds_after_finished: Optional[int] = None

    ttl_seconds_before_active: Optional[int] = None
