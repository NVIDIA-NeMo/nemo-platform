# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Execution provider types for the Jobs service.

The definitions now live in :mod:`nemo_platform_plugin.jobs.providers` so that
both the server and the typed HTTP client (``JobsClient``) share one source of
truth.  This module re-exports them for backward compatibility.
"""

from nemo_platform_plugin.jobs.providers import (
    ComputeResources as ComputeResources,
)
from nemo_platform_plugin.jobs.providers import (
    ComputeResourceSpec as ComputeResourceSpec,
)
from nemo_platform_plugin.jobs.providers import (
    ContainerSpec as ContainerSpec,
)
from nemo_platform_plugin.jobs.providers import (
    CPUExecutionProvider as CPUExecutionProvider,
)
from nemo_platform_plugin.jobs.providers import (
    DistributedGPUExecutionProvider as DistributedGPUExecutionProvider,
)
from nemo_platform_plugin.jobs.providers import (
    ExecutionProviderT as ExecutionProviderT,
)
from nemo_platform_plugin.jobs.providers import (
    GPUExecutionProvider as GPUExecutionProvider,
)
from nemo_platform_plugin.jobs.providers import (
    Provider as Provider,
)
from nemo_platform_plugin.jobs.providers import (
    SubprocessExecutionProvider as SubprocessExecutionProvider,
)
from nemo_platform_plugin.jobs.providers import (
    TaskSpec as TaskSpec,
)
