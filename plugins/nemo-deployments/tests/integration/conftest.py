# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test fixtures for docker- and k8s-backed deployments."""

from __future__ import annotations

from pathlib import Path

import pytest
from docker_availability import DOCKER_AVAILABLE, skip_without_docker
from kubeconfig_availability import KUBECONFIG_AVAILABLE, skip_without_kubeconfig

__all__ = ["DOCKER_AVAILABLE", "KUBECONFIG_AVAILABLE", "skip_without_docker", "skip_without_kubeconfig"]

# Tests under the same substrate share one daemon/cluster and the same managed-by
# label namespace. Run each substrate's tests on a single xdist worker to avoid
# container/volume/pod name races; docker and k8s tests don't collide with each
# other, so they get separate groups rather than one shared one.
_DOCKER_INTEGRATION_XDIST_GROUP = "nemo_deployments_docker_integration"
_K8S_INTEGRATION_XDIST_GROUP = "nemo_deployments_k8s_integration"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    integration_dir = Path(__file__).parent.resolve()
    k8s_dir = (integration_dir / "backends" / "k8s").resolve()
    k8s_reconcile_test = (integration_dir / "test_reconcile_k8s.py").resolve()
    for item in items:
        item_path = Path(str(item.fspath)).resolve()
        if k8s_dir in item_path.parents or item_path == k8s_reconcile_test:
            item.add_marker(pytest.mark.xdist_group(_K8S_INTEGRATION_XDIST_GROUP))
        elif integration_dir in item_path.parents:
            item.add_marker(pytest.mark.xdist_group(_DOCKER_INTEGRATION_XDIST_GROUP))
