# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for deployment reconciliation.

Requires AIRCORE-756 DockerDeploymentBackend to be registered in BACKEND_CLASSES.
Until then, these tests are skipped — unit tests with MockDeploymentBackend provide coverage.
"""

from __future__ import annotations

import pytest
from nemo_deployments_plugin.backends.registry import BACKEND_CLASSES

pytestmark = pytest.mark.skipif(
    "docker" not in BACKEND_CLASSES,
    reason="Requires DockerDeploymentBackend (AIRCORE-756)",
)


@pytest.mark.asyncio
async def test_puller_server_prerequisite_chain() -> None:
    """Volume → puller (OnFailure) → server (Always + prerequisite) end-to-end."""
    raise NotImplementedError("Enable when AIRCORE-756 lands")
