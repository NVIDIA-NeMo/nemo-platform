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

from typing import Dict, List, Union, Optional
from typing_extensions import Annotated, TypeAlias

from ..._utils import PropertyInfo
from ..._models import BaseModel
from .step_lifecycle import StepLifecycle
from .cpu_execution_provider import CPUExecutionProvider
from .gpu_execution_provider import GPUExecutionProvider
from .subprocess_execution_provider import SubprocessExecutionProvider
from .platform_job_environment_variable import PlatformJobEnvironmentVariable
from .distributed_gpu_execution_provider import DistributedGPUExecutionProvider

__all__ = ["PlatformJobStepSpec", "Executor"]

Executor: TypeAlias = Annotated[
    Union[CPUExecutionProvider, GPUExecutionProvider, DistributedGPUExecutionProvider, SubprocessExecutionProvider],
    PropertyInfo(discriminator="provider"),
]


class PlatformJobStepSpec(BaseModel):
    """Specification for a single step in a platform job."""

    executor: Executor
    """The executor for the step"""

    name: str
    """The name of the step.

    Must be unique for all steps in a job. Name must start with a lowercase letter,
    be 2-63 characters, and contain only lowercase letters, digits, hyphens, and @
    . + \\__ (no consecutive hyphens, cannot end with a hyphen).
    """

    config: Optional[Dict[str, object]] = None
    """Configuration for the step"""

    environment: Optional[List[PlatformJobEnvironmentVariable]] = None
    """Environment variables for the step"""

    lifecycle: Optional[StepLifecycle] = None
    """Controller-level lifecycle configuration for a job step.

    These settings control how the jobs controller manages the step, as opposed to
    `config` which is the task payload forwarded to the container.
    """
