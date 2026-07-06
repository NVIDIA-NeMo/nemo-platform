# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared schemas for the Jobs service.

The job specification types now live in :mod:`nemo_platform_plugin.jobs.spec`
and the ``BaseExecutionProfile`` base in the same package, so that both the
server and the typed HTTP client (``JobsClient``) share one source of truth.
This module re-exports them for backward compatibility.
"""

from nemo_platform_plugin.jobs.spec import (
    BackendRef as BackendRef,
)
from nemo_platform_plugin.jobs.spec import (
    BaseExecutionProfile as BaseExecutionProfile,
)
from nemo_platform_plugin.jobs.spec import (
    PlatformJobEnvironmentVariable as PlatformJobEnvironmentVariable,
)
from nemo_platform_plugin.jobs.spec import (
    PlatformJobSecretEnvironmentVariableRef as PlatformJobSecretEnvironmentVariableRef,
)
from nemo_platform_plugin.jobs.spec import (
    PlatformJobSpec as PlatformJobSpec,
)
from nemo_platform_plugin.jobs.spec import (
    PlatformJobStepSpec as PlatformJobStepSpec,
)
from nemo_platform_plugin.jobs.spec import (
    ProfileRef as ProfileRef,
)
from nemo_platform_plugin.jobs.spec import (
    ProviderRef as ProviderRef,
)
from nemo_platform_plugin.jobs.spec import (
    StepLifecycle as StepLifecycle,
)
