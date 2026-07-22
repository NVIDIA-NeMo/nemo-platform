# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nemo_deployments_plugin.backends.k8s.backend import K8sDeploymentBackend
from nemo_deployments_plugin.backends.k8s.config import K8sExecutorConfig


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


def test_effective_namespace_prefers_explicit_config(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit config value wins even when POD_NAMESPACE is set.
    monkeypatch.setenv("POD_NAMESPACE", "pod-ns")
    config = K8sExecutorConfig(default_namespace="explicit-ns")
    assert config.effective_namespace == "explicit-ns"


def test_effective_namespace_falls_back_to_pod_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    # No explicit config -> the controller's own pod namespace (downward API).
    monkeypatch.setenv("POD_NAMESPACE", "pod-ns")
    config = K8sExecutorConfig()
    assert config.default_namespace is None
    assert config.effective_namespace == "pod-ns"


def test_effective_namespace_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Neither an explicit config value nor POD_NAMESPACE -> "default".
    monkeypatch.delenv("POD_NAMESPACE", raising=False)
    config = K8sExecutorConfig()
    assert config.effective_namespace == "default"


def test_effective_namespace_ignores_blank_pod_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    # A blank/whitespace POD_NAMESPACE is treated as unset.
    monkeypatch.setenv("POD_NAMESPACE", "  ")
    config = K8sExecutorConfig()
    assert config.effective_namespace == "default"
