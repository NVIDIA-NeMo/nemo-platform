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

from typing import Dict, Union, Optional
from datetime import datetime
from typing_extensions import TypeAlias

from ..._models import BaseModel
from .benchmark_online_job import BenchmarkOnlineJob
from .benchmark_offline_job import BenchmarkOfflineJob
from .benchmark_online_agent_job import BenchmarkOnlineAgentJob
from ..shared.platform_job_status import PlatformJobStatus

__all__ = ["BenchmarkEvaluationJob", "Spec"]

Spec: TypeAlias = Union[BenchmarkOfflineJob, BenchmarkOnlineJob, BenchmarkOnlineAgentJob]


class BenchmarkEvaluationJob(BaseModel):
    name: str

    spec: Spec
    """Input for an offline benchmark evaluation job.

    Evaluates the benchmark's dataset against all metrics in the benchmark.
    """

    id: Optional[str] = None

    created_at: Optional[datetime] = None

    custom_fields: Optional[Dict[str, object]] = None

    description: Optional[str] = None

    error_details: Optional[Dict[str, object]] = None

    ownership: Optional[Dict[str, object]] = None

    project: Optional[str] = None

    status: Optional[PlatformJobStatus] = None
    """Enumeration of possible job statuses.

    This enum represents the various states a job can be in during its lifecycle,
    from creation to a terminal state.
    """

    status_details: Optional[Dict[str, object]] = None

    updated_at: Optional[datetime] = None

    workspace: Optional[str] = None
