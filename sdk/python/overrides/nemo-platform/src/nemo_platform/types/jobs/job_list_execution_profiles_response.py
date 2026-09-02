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

from typing import List, Union
from typing_extensions import TypeAlias

from .e2e_job_execution_profile import E2EJobExecutionProfile
from .docker_job_execution_profile import DockerJobExecutionProfile
from .volcano_job_execution_profile import VolcanoJobExecutionProfile
from .kubernetes_job_execution_profile import KubernetesJobExecutionProfile
from .subprocess_job_execution_profile import SubprocessJobExecutionProfile

__all__ = ["JobListExecutionProfilesResponse", "JobListExecutionProfilesResponseItem"]

JobListExecutionProfilesResponseItem: TypeAlias = Union[
    DockerJobExecutionProfile,
    KubernetesJobExecutionProfile,
    VolcanoJobExecutionProfile,
    SubprocessJobExecutionProfile,
    E2EJobExecutionProfile,
]

JobListExecutionProfilesResponse: TypeAlias = List[JobListExecutionProfilesResponseItem]
