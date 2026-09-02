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

__all__ = ["SubmitProfileJobResponse"]


class SubmitProfileJobResponse(BaseModel):
    """Response for a submitted fileset-profiling job."""

    fileset: str
    """Name of the profiled fileset."""

    job_id: str
    """ID of the submitted profiling job."""

    job_name: str
    """Name of the submitted profiling job."""

    workspace: str
    """Workspace of the profiled fileset."""

    reused: Optional[bool] = None
    """
    True if an already-running profiling job was returned instead of submitting a
    new one.
    """

    status: Optional[str] = None
    """Status of the job at submission time."""
