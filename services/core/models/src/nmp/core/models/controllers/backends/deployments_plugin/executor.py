# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executor selection for deployments-plugin model entities."""

from nmp.common.config import Runtime
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginConfig


def executor_for_runtime(config: DeploymentsPluginConfig, runtime: Runtime) -> str | None:
    """Resolve a configured executor for the platform runtime."""
    if runtime == Runtime.DOCKER:
        return config.docker_executor or config.default_executor
    if runtime == Runtime.KUBERNETES:
        return config.k8s_executor or config.default_executor
    return config.default_executor
