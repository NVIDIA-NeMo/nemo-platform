# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nemo_deployments_plugin.backends.k8s.backend import K8sDeploymentBackend
from nemo_deployments_plugin.backends.k8s.config import K8sExecutorConfig


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


def test_shutdown_closes_kubernetes_clients(k8s_backend: K8sDeploymentBackend) -> None:
    mock_clients = MagicMock()
    k8s_backend._clients = mock_clients
    k8s_backend.shutdown()
    mock_clients.close.assert_called_once()


def test_default_namespace_rejects_invalid_dns_label() -> None:
    with pytest.raises(ValueError, match="default_namespace must be a lowercase DNS-1123 label"):
        K8sExecutorConfig(default_namespace="X")
