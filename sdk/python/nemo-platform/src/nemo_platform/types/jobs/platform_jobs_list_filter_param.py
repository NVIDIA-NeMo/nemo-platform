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

from typing import List, Union
from typing_extensions import TypeAlias, TypedDict

from ..shared.platform_job_status import PlatformJobStatus
from ..shared_params.string_filter import StringFilter
from ..shared_params.datetime_filter import DatetimeFilter

__all__ = ["PlatformJobsListFilterParam", "Name", "Source"]

Name: TypeAlias = Union[StringFilter, str]

Source: TypeAlias = Union[StringFilter, str]


class PlatformJobsListFilterParam(TypedDict, total=False):
    """Filter options for listing platform jobs."""

    created_at: DatetimeFilter
    """Jobs created at 'gte' datetime or 'lte' datetime."""

    name: Name
    """Name of the job."""

    project: str
    """Project of the job."""

    source: Source
    """The source of the job."""

    status: Union[PlatformJobStatus, List[PlatformJobStatus]]
    """The current status."""

    updated_at: DatetimeFilter
    """Jobs updated at 'gte' datetime or 'lte' datetime."""

    workspace: str
    """Workspace of the job."""
