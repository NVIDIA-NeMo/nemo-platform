# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared Kubernetes cluster availability check for integration tests."""

from __future__ import annotations

import pytest

try:
    from kubernetes import client, config

    try:
        config.load_kube_config()
    except config.ConfigException:
        config.load_incluster_config()
    client.VersionApi().get_code(_request_timeout=5)
    KUBECONFIG_AVAILABLE: bool = True
except Exception:
    KUBECONFIG_AVAILABLE = False

skip_without_kubeconfig: pytest.MarkDecorator = pytest.mark.skipif(
    not KUBECONFIG_AVAILABLE,
    reason="No reachable Kubernetes cluster (set KUBECONFIG or run against kind)",
)
