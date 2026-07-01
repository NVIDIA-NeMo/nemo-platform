# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_deployments_plugin.backends.k8s.backend import K8sDeploymentBackend


@pytest.mark.asyncio
async def test_create_deployment_not_implemented_yet(k8s_backend: K8sDeploymentBackend) -> None:
    with pytest.raises(NotImplementedError, match="create_deployment"):
        await k8s_backend.create_deployment(
            workspace="default",
            name="srv",
            config_name="cfg1",
            labels={},
            backend_config={},
        )


def test_executor_config_parsed_from_dict(k8s_backend: K8sDeploymentBackend) -> None:
    assert k8s_backend.executor_config.default_namespace == "nemo-deployments"
    assert k8s_backend.executor_config.request_timeout == 30
