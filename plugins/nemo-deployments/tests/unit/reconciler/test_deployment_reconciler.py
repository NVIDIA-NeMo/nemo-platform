# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock

import pytest
from helpers import make_deployment, make_deployment_config
from nemo_deployments_plugin.backends.base import BackendStatusUpdate
from nemo_deployments_plugin.backends.registry import ExecutorRegistry
from nemo_deployments_plugin.config import ControllerConfig
from nemo_deployments_plugin.entities import Prerequisite, Volume
from nemo_deployments_plugin.reconciler.deployment_reconciler import DeploymentReconciler
from nemo_deployments_plugin.reconciler.orphan_cleanup import reconcile_orphans
from nemo_platform_plugin.entity_client import NemoEntityConflictError, NemoEntityNotFoundError
from reconciler.conftest import MockDeploymentBackend

NO_VOLUMES: dict[tuple[str, str], Volume] = {}


@pytest.mark.asyncio
async def test_pending_creates_deployment(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
    mock_entities: AsyncMock,
) -> None:
    dep = make_deployment()
    cfg = make_deployment_config()
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert len(mock_backend.create_calls) == 1
    assert dep.status == "STARTING"
    mock_entities.update.assert_awaited()


@pytest.mark.asyncio
async def test_prerequisite_gating_stays_pending(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment("server")
    dep.deployment_config = "server"
    cfg = make_deployment_config("server")
    dep.prerequisites = [Prerequisite(deployment_name="puller", condition="succeeded")]
    deployment_reconciler.set_config_cache({("default", "server"): cfg})

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert dep.status == "PENDING"
    assert "Waiting" in dep.status_message
    assert mock_backend.create_calls == []


@pytest.mark.asyncio
async def test_prerequisite_failure_marks_parent_failed(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    puller = make_deployment("puller")
    puller.deployment_config = "puller"
    puller.status = "FAILED"
    server = make_deployment("server")
    server.deployment_config = "server"
    cfg = make_deployment_config("server")
    server.prerequisites = [Prerequisite(deployment_name="puller")]
    deployment_reconciler.set_config_cache({("default", "server"): cfg})
    by_name = {("default", "puller"): puller}

    await deployment_reconciler.reconcile_one(
        server,
        deployments_by_name=by_name,
        volumes_by_name=NO_VOLUMES,
    )

    assert server.status == "FAILED"
    assert mock_backend.create_calls == []


@pytest.mark.asyncio
async def test_ready_monitoring(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "READY"
    cfg = make_deployment_config()
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(status="READY", status_message="healthy")

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert mock_backend.read_calls == [("default", "dep1")]
    assert dep.status == "READY"


@pytest.mark.asyncio
async def test_unknown_status_retries_then_fails(
    mock_entities: AsyncMock,
    mock_backend: MockDeploymentBackend,
) -> None:
    reconciler = DeploymentReconciler(
        mock_entities,
        ExecutorRegistry({"default": mock_backend}, default_executor="default"),
        ControllerConfig(
            drift_recovery_max_attempts=3,
            drift_recovery_initial_delay_seconds=0,
            drift_recovery_max_delay_seconds=0,
        ),
    )
    dep = make_deployment()
    dep.status = "STARTING"
    cfg = make_deployment_config()
    reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(
        status="UNKNOWN",
        status_message="Docker API error while checking container status: connection reset",
    )

    for _ in range(4):
        await reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert dep.status == "FAILED"
    assert "Unable to communicate with backend after 3 attempts" in dep.status_message


@pytest.mark.asyncio
async def test_unknown_status_records_attempt_before_exhaustion(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "STARTING"
    cfg = make_deployment_config()
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(
        status="UNKNOWN",
        status_message="Docker daemon unavailable",
    )

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert dep.status == "UNKNOWN"
    assert "attempt 1/3" in dep.status_message


@pytest.mark.asyncio
async def test_on_failure_succeeded_terminal(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "STARTING"
    cfg = make_deployment_config()
    cfg.restart_policy = "OnFailure"
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(
        status="SUCCEEDED",
        status_message="completed",
        exit_code=0,
    )

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert dep.status == "SUCCEEDED"
    assert dep.exit_code == 0


@pytest.mark.asyncio
async def test_desired_stopped_deletes(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
    mock_entities: AsyncMock,
) -> None:
    dep = make_deployment()
    dep.desired_state = "STOPPED"
    cfg = make_deployment_config()
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert mock_backend.deployment_delete_calls == [("default", "dep1")]
    mock_entities.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_proceeds_when_config_missing(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
    mock_entities: AsyncMock,
) -> None:
    dep = make_deployment()
    dep.desired_state = "STOPPED"
    mock_entities.get.side_effect = NemoEntityNotFoundError("missing")

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert mock_backend.deployment_delete_calls == [("default", "dep1")]
    mock_entities.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_retains_deleting_when_backend_delete_fails(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
    mock_entities: AsyncMock,
) -> None:
    dep = make_deployment()
    dep.desired_state = "STOPPED"

    async def failing_delete(workspace: str, name: str) -> BackendStatusUpdate:
        raise RuntimeError("delete failed")

    mock_backend.delete_deployment = failing_delete  # type: ignore[method-assign]

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert dep.status == "DELETING"
    mock_entities.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_clears_drift_recovery_cache(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
    mock_entities: AsyncMock,
) -> None:
    dep = make_deployment()
    dep.desired_state = "STOPPED"
    deployment_reconciler._drift_cache.add_attempt("default/dep1")

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert deployment_reconciler._drift_cache.get_attempts("default/dep1") == 0


@pytest.mark.asyncio
async def test_drift_recovery_recreate(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "LOST"
    cfg = make_deployment_config()
    cfg.restart_policy = "Always"
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(status="LOST", status_message="missing")
    mock_backend.create_status = BackendStatusUpdate(status="STARTING", status_message="recreated")

    dep.status = "LOST"
    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert len(mock_backend.create_calls) == 1
    assert dep.status == "STARTING"
    assert "Recovering" in dep.status_message


@pytest.mark.asyncio
async def test_drift_recovery_exhausted(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "LOST"
    cfg = make_deployment_config()
    cfg.restart_policy = "Always"
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    deployment_reconciler._drift_cache.add_attempt("default/dep1")
    deployment_reconciler._drift_cache.add_attempt("default/dep1")
    deployment_reconciler._drift_cache.add_attempt("default/dep1")

    mock_backend.read_status_result = BackendStatusUpdate(status="LOST")
    dep.status = "LOST"
    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert dep.status == "FAILED"
    assert "Drift recovery failed" in dep.status_message


@pytest.mark.asyncio
async def test_conflict_propagates_from_save(
    deployment_reconciler: DeploymentReconciler,
    mock_entities: AsyncMock,
) -> None:
    dep = make_deployment()
    cfg = make_deployment_config()
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_entities.update.side_effect = NemoEntityConflictError("conflict")

    with pytest.raises(NemoEntityConflictError):
        await deployment_reconciler.reconcile_one(
            dep,
            deployments_by_name={},
            volumes_by_name=NO_VOLUMES,
        )


@pytest.mark.asyncio
async def test_missing_config_marks_failed(
    deployment_reconciler: DeploymentReconciler,
    mock_entities: AsyncMock,
) -> None:
    dep = make_deployment()
    mock_entities.get.side_effect = NemoEntityNotFoundError("missing")

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)

    assert dep.status == "FAILED"
    assert "DeploymentConfig" in dep.status_message


@pytest.mark.asyncio
async def test_executor_not_found_marks_failed(
    deployment_reconciler: DeploymentReconciler,
    mock_entities: AsyncMock,
) -> None:
    from nemo_deployments_plugin.backends.registry import ExecutorRegistry

    empty_registry = ExecutorRegistry({}, default_executor=None)
    reconciler = DeploymentReconciler(mock_entities, empty_registry, deployment_reconciler._controller_config)
    dep = make_deployment()
    cfg = make_deployment_config()
    reconciler.set_config_cache({("default", "cfg1"): cfg})

    await reconciler.reconcile_one(
        dep,
        deployments_by_name={},
        volumes_by_name=NO_VOLUMES,
    )

    assert dep.status == "FAILED"
    assert "executor" in dep.status_message.lower()


@pytest.mark.asyncio
async def test_orphan_cleanup_deletes_unknown(
    mock_backend: MockDeploymentBackend,
) -> None:
    mock_backend.managed_names = ["default/orphan", "default/known"]
    await reconcile_orphans([mock_backend], {"default/known"})
    assert mock_backend.deployment_delete_calls == [("default", "orphan")]


@pytest.mark.asyncio
async def test_orphan_cleanup_skips_invalid_ids(
    mock_backend: MockDeploymentBackend,
) -> None:
    mock_backend.managed_names = ["default/valid", "/invalid", "ws/", "default/orphan"]
    await reconcile_orphans([mock_backend], {"default/valid"})
    assert mock_backend.deployment_delete_calls == [("default", "orphan")]


@pytest.mark.asyncio
async def test_on_failure_failed_exit(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "STARTING"
    cfg = make_deployment_config()
    cfg.restart_policy = "OnFailure"
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(
        status="FAILED",
        status_message="exit 1",
        exit_code=1,
    )

    await deployment_reconciler.reconcile_one(
        dep,
        deployments_by_name={},
        volumes_by_name=NO_VOLUMES,
    )

    assert dep.status == "FAILED"
    assert dep.exit_code == 1


@pytest.mark.asyncio
async def test_drift_recovery_ignore(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "LOST"
    cfg = make_deployment_config()
    cfg.restart_policy = "Always"
    cfg.drift_recovery.action = "ignore"
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(status="LOST", status_message="gone")

    await deployment_reconciler.reconcile_one(
        dep,
        deployments_by_name={},
        volumes_by_name=NO_VOLUMES,
    )

    assert dep.status == "LOST"
    assert "ignored" in dep.status_message.lower()
    assert mock_backend.create_calls == []


@pytest.mark.asyncio
async def test_drift_recovery_backoff_skips_recreate(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "LOST"
    cfg = make_deployment_config()
    cfg.restart_policy = "Always"
    cfg.drift_recovery.initial_delay_seconds = 3600
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    deployment_reconciler._drift_cache.add_attempt("default/dep1")
    mock_backend.read_status_result = BackendStatusUpdate(status="LOST")

    await deployment_reconciler.reconcile_one(
        dep,
        deployments_by_name={},
        volumes_by_name=NO_VOLUMES,
    )

    assert mock_backend.create_calls == []
    assert dep.status == "LOST"


@pytest.mark.asyncio
async def test_volume_mount_gating(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    from helpers import make_volume
    from nemo_deployments_plugin.entities import VolumeMount

    dep = make_deployment()
    cfg = make_deployment_config()
    cfg.volume_mounts = [VolumeMount(name="data", mountPath="/data")]
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    vol = make_volume("data")

    await deployment_reconciler.reconcile_one(
        dep,
        deployments_by_name={},
        volumes_by_name={("default", "data"): vol},
    )

    assert dep.status == "PENDING"
    assert "volume" in dep.status_message.lower()
    assert mock_backend.create_calls == []


@pytest.mark.asyncio
async def test_prerequisite_ready_through_reconciler(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    worker = make_deployment("worker")
    worker.deployment_config = "worker"
    worker.status = "READY"
    server = make_deployment("server")
    server.deployment_config = "server"
    cfg = make_deployment_config("server")
    server.prerequisites = [Prerequisite(deployment_name="worker", condition="ready")]
    deployment_reconciler.set_config_cache({("default", "server"): cfg})
    by_name = {("default", "worker"): worker}

    await deployment_reconciler.reconcile_one(
        server,
        deployments_by_name=by_name,
        volumes_by_name=NO_VOLUMES,
    )

    assert server.status == "STARTING"
    assert len(mock_backend.create_calls) == 1


@pytest.mark.asyncio
async def test_drift_recovery_create_failure_stays_lost_and_backoffs(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    dep = make_deployment()
    dep.status = "LOST"
    cfg = make_deployment_config()
    cfg.restart_policy = "Always"
    deployment_reconciler.set_config_cache({("default", "cfg1"): cfg})
    mock_backend.read_status_result = BackendStatusUpdate(status="LOST", status_message="missing")

    async def failing_create(**kwargs: object) -> BackendStatusUpdate:
        mock_backend.create_calls.append(kwargs)
        raise RuntimeError("create failed")

    mock_backend.create_deployment = failing_create  # type: ignore[method-assign]

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)
    assert dep.status == "LOST"
    assert "Will retry" in dep.status_message
    assert len(mock_backend.create_calls) == 1

    await deployment_reconciler.reconcile_one(dep, deployments_by_name={}, volumes_by_name=NO_VOLUMES)
    assert dep.status == "LOST"
    assert dep.status != "FAILED"
    assert len(mock_backend.create_calls) == 1


@pytest.mark.asyncio
async def test_succeeded_prerequisite_in_index_allows_create(
    deployment_reconciler: DeploymentReconciler,
    mock_backend: MockDeploymentBackend,
) -> None:
    puller = make_deployment("puller")
    puller.deployment_config = "puller"
    puller.status = "SUCCEEDED"
    puller.exit_code = 0
    server = make_deployment("server")
    server.deployment_config = "server"
    cfg = make_deployment_config("server")
    server.prerequisites = [Prerequisite(deployment_name="puller", condition="succeeded")]
    deployment_reconciler.set_config_cache({("default", "server"): cfg})
    by_name = {("default", "puller"): puller}

    await deployment_reconciler.reconcile_one(
        server,
        deployments_by_name=by_name,
        volumes_by_name=NO_VOLUMES,
    )

    assert server.status == "STARTING"
    assert len(mock_backend.create_calls) == 1
