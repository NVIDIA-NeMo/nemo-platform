# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test fixtures for docker-backed deployments."""

from __future__ import annotations

from pathlib import Path

import pytest
from docker_availability import DOCKER_AVAILABLE, skip_without_docker

__all__ = ["DOCKER_AVAILABLE", "skip_without_docker"]

# All tests in this package share one Docker daemon and the same managed-by label
# namespace. Run them on a single xdist worker to avoid container/volume races.
_DOCKER_INTEGRATION_XDIST_GROUP = "nemo_deployments_docker_integration"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    integration_dir = Path(__file__).parent.resolve()
    for item in items:
        if integration_dir in Path(str(item.fspath)).resolve().parents:
            item.add_marker(pytest.mark.xdist_group(_DOCKER_INTEGRATION_XDIST_GROUP))
