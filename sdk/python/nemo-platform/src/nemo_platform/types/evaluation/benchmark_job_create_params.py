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

from typing import Dict, Union
from typing_extensions import Required, TypeAlias, TypedDict

from .benchmark_online_job_param import BenchmarkOnlineJobParam
from .benchmark_offline_job_param import BenchmarkOfflineJobParam
from .benchmark_online_agent_job_param import BenchmarkOnlineAgentJobParam

__all__ = ["BenchmarkJobCreateParams", "Spec"]


class BenchmarkJobCreateParams(TypedDict, total=False):
    workspace: str

    spec: Required[Spec]
    """Input for an offline benchmark evaluation job.

    Evaluates the benchmark's dataset against all metrics in the benchmark.
    """

    custom_fields: Dict[str, object]

    description: str

    name: str

    ownership: Dict[str, object]

    project: str


Spec: TypeAlias = Union[BenchmarkOfflineJobParam, BenchmarkOnlineJobParam, BenchmarkOnlineAgentJobParam]
