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

from typing import Dict, Union, Iterable
from typing_extensions import Required, TypeAlias, TypedDict

from .step_lifecycle_param import StepLifecycleParam
from .cpu_execution_provider_param import CPUExecutionProviderParam
from .gpu_execution_provider_param import GPUExecutionProviderParam
from .subprocess_execution_provider_param import SubprocessExecutionProviderParam
from .platform_job_environment_variable_param import PlatformJobEnvironmentVariableParam
from .distributed_gpu_execution_provider_param import DistributedGPUExecutionProviderParam

__all__ = ["PlatformJobStepSpecParam", "Executor"]

Executor: TypeAlias = Union[
    CPUExecutionProviderParam,
    GPUExecutionProviderParam,
    DistributedGPUExecutionProviderParam,
    SubprocessExecutionProviderParam,
]


class PlatformJobStepSpecParam(TypedDict, total=False):
    """Specification for a single step in a platform job."""

    executor: Required[Executor]
    """The executor for the step"""

    name: Required[str]
    """The name of the step.

    Must be unique for all steps in a job. Name must start with a lowercase letter,
    be 2-63 characters, and contain only lowercase letters, digits, hyphens, and @
    . + \\__ (no consecutive hyphens, cannot end with a hyphen).
    """

    config: Dict[str, object]
    """Configuration for the step"""

    environment: Iterable[PlatformJobEnvironmentVariableParam]
    """Environment variables for the step"""

    lifecycle: StepLifecycleParam
    """Controller-level lifecycle configuration for a job step.

    These settings control how the jobs controller manages the step, as opposed to
    `config` which is the task payload forwarded to the container.
    """
