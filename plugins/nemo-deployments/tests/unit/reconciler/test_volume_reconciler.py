# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock

import pytest
from helpers import make_volume
from nemo_deployments_plugin.backends.base import VolumeStatusUpdate
from nemo_deployments_plugin.reconciler.volume_reconciler import VolumeReconciler
from reconciler.conftest import MockDeploymentBackend


@pytest.mark.asyncio
async def test_pending_volume_becomes_bound(
    volume_reconciler: VolumeReconciler,
    mock_backend: MockDeploymentBackend,
    mock_entities: AsyncMock,
) -> None:
    vol = make_volume()
    mock_backend.volume_create_status = VolumeStatusUpdate(status="BOUND", status_message="ready")

    await volume_reconciler.reconcile_one(vol)

    assert vol.status == "BOUND"
    mock_entities.update.assert_awaited()


@pytest.mark.asyncio
async def test_volume_create_failure(
    volume_reconciler: VolumeReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    vol = make_volume()

    async def fail(**kwargs: object) -> VolumeStatusUpdate:
        raise RuntimeError("docker unavailable")

    mock_backend.create_volume = fail  # type: ignore[method-assign]

    await volume_reconciler.reconcile_one(vol)

    assert vol.status == "FAILED"
    assert "docker unavailable" in vol.status_message
