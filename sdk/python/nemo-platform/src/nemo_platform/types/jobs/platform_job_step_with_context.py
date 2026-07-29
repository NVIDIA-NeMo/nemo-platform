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
from datetime import datetime

from ..._models import BaseModel
from ..shared.auth_context import AuthContext
from .platform_job_step_spec import PlatformJobStepSpec
from ..shared.platform_job_status import PlatformJobStatus

__all__ = ["PlatformJobStepWithContext"]


class PlatformJobStepWithContext(BaseModel):
    """Step with additional context from parent job/attempt."""

    id: str

    attempt_id: str

    fileset: str

    job: str

    name: str

    workspace: str

    artifact_base_path: Optional[str] = None
    """
    Folder inside the fileset that this job's artifacts nest under; None when the
    job owns the whole fileset and its artifacts sit at the root
    """

    auth_context: Optional[AuthContext] = None
    """Auth context captured at resource creation for delegated access.

    Stores a snapshot of the creating principal's identity so that controllers can
    later act on their behalf (e.g., accessing secrets).
    """

    created_at: Optional[datetime] = None

    error_details: Optional[Dict[str, object]] = None

    status: Optional[PlatformJobStatus] = None
    """Enumeration of possible job statuses.

    This enum represents the various states a job can be in during its lifecycle,
    from creation to a terminal state.
    """

    status_details: Optional[Dict[str, object]] = None

    step_spec: Optional[PlatformJobStepSpec] = None
    """Specification for a single step in a platform job."""

    updated_at: Optional[datetime] = None
