# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for jobs controller backends base module."""

import datetime
from unittest.mock import MagicMock, patch

from nmp.common.config import PlatformConfig
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.core.jobs.api.v2.jobs.schemas import PlatformJobStepWithContext
from nmp.core.jobs.app.providers import ContainerSpec, CPUExecutionProvider
from nmp.core.jobs.app.schemas import PlatformJobStepSpec, StepLifecycle
from nmp.core.jobs.controllers.backends.base import get_logs_endpoint_from_fileset, resolve_task_image
from nmp.core.jobs.controllers.backends.test import MockKubernetesCPUJobBackend


class TestGetLogsEndpointFromFileset:
    """Tests for get_logs_endpoint_from_fileset."""

    def test_returns_expected_path_with_workspace_and_fileset(self):
        """Endpoint URL includes /apis/files prefix and workspace/fileset in path."""
        config = PlatformConfig(  # type: ignore[abstract]
            service_discovery={"files": "http://files.example.com"},
            loopback_address=None,
        )

        with patch(
            "nmp.core.jobs.controllers.backends.base.determine_loopback_override",
            return_value=None,
        ):
            result = get_logs_endpoint_from_fileset(config, workspace="my-workspace", fileset_id="my-fileset-id")

        assert result == (
            "http://files.example.com/apis/files/v2/workspaces/my-workspace/filesets/my-fileset-id/otlp/v1/logs"
        )

    def test_with_loopback_address_replaces_localhost_in_files_url(self):
        """When loopback_address is set, localhost in files URL (base_url) is replaced."""
        config = PlatformConfig(  # type: ignore[abstract]
            base_url="http://localhost:8080",
            loopback_address="host.docker.internal",
        )

        result = get_logs_endpoint_from_fileset(config, workspace="default", fileset_id="job-logs-abc")

        assert result == (
            "http://host.docker.internal:8080/apis/files/v2/workspaces/default/filesets/job-logs-abc/otlp/v1/logs"
        )

    def test_with_loopback_address_replaces_127_0_0_1(self):
        """When loopback_address is set, 127.0.0.1 in files URL is replaced."""
        config = PlatformConfig(  # type: ignore[abstract]
            base_url="http://127.0.0.1:3000",
            loopback_address="host.docker.internal",
        )

        result = get_logs_endpoint_from_fileset(config, workspace="default", fileset_id="fs-123")

        assert result == (
            "http://host.docker.internal:3000/apis/files/v2/workspaces/default/filesets/fs-123/otlp/v1/logs"
        )

    def test_no_loopback_override_when_files_url_has_no_loopback(self):
        """When files URL has no loopback host, URL is unchanged by loopback_address."""
        config = PlatformConfig(  # type: ignore[abstract]
            service_discovery={"files": "https://files.service.svc.cluster.local"},
            loopback_address="host.docker.internal",
        )

        result = get_logs_endpoint_from_fileset(config, workspace="default", fileset_id="fs-456")

        assert result == (
            "https://files.service.svc.cluster.local/apis/files/v2/workspaces/default/filesets/fs-456/otlp/v1/logs"
        )

    def test_uses_determine_loopback_override_when_loopback_address_not_set(self):
        """When loopback_address is None, determine_loopback_override() is used."""
        config = PlatformConfig(  # type: ignore[abstract]
            base_url="http://localhost:8080",
            loopback_address=None,
        )

        with patch(
            "nmp.core.jobs.controllers.backends.base.determine_loopback_override",
            return_value="host.docker.internal",
        ):
            result = get_logs_endpoint_from_fileset(config, workspace="default", fileset_id="job-logs-xyz")

        assert result == (
            "http://host.docker.internal:8080/apis/files/v2/workspaces/default/filesets/job-logs-xyz/otlp/v1/logs"
        )

    def test_no_replacement_when_determine_loopback_override_returns_none(self):
        """When determine_loopback_override returns None, files URL (base_url) is used as-is."""
        config = PlatformConfig(  # type: ignore[abstract]
            base_url="http://localhost:8080",
            loopback_address=None,
        )

        with patch(
            "nmp.core.jobs.controllers.backends.base.determine_loopback_override",
            return_value=None,
        ):
            result = get_logs_endpoint_from_fileset(config, workspace="ns1", fileset_id="fileset-789")

        assert result == ("http://localhost:8080/apis/files/v2/workspaces/ns1/filesets/fileset-789/otlp/v1/logs")

    def test_uses_service_discovery_files_url_when_set(self):
        """When service_discovery has 'files', get_logs_endpoint_from_fileset uses that URL."""
        config = PlatformConfig(  # type: ignore[abstract]
            base_url="http://platform:8080",
            service_discovery={"files": "http://files-service.svc.cluster.local:8080"},
            loopback_address=None,
        )

        with patch(
            "nmp.core.jobs.controllers.backends.base.determine_loopback_override",
            return_value=None,
        ):
            result = get_logs_endpoint_from_fileset(config, workspace="my-workspace", fileset_id="my-fileset-id")

        assert result == (
            "http://files-service.svc.cluster.local:8080/apis/files/v2/workspaces/my-workspace/filesets/my-fileset-id/otlp/v1/logs"
        )

    def test_service_discovery_takes_precedence_over_base_url(self):
        """When service_discovery['files'] is set, it is used instead of base_url for files."""
        config = PlatformConfig(  # type: ignore[abstract]
            base_url="http://platform:8080",
            service_discovery={"files": "http://discovered-files:9000"},
            loopback_address=None,
        )

        with patch(
            "nmp.core.jobs.controllers.backends.base.determine_loopback_override",
            return_value=None,
        ):
            result = get_logs_endpoint_from_fileset(config, workspace="ws1", fileset_id="fs-1")

        # get_service_url("files") returns service_discovery["files"] when present
        assert result == ("http://discovered-files:9000/apis/files/v2/workspaces/ws1/filesets/fs-1/otlp/v1/logs")

    def test_service_discovery_files_with_loopback_replacement(self):
        """Loopback replacement works when files URL comes from service_discovery."""
        config = PlatformConfig(  # type: ignore[abstract]
            base_url="http://platform:8080",
            service_discovery={"files": "http://localhost:3000"},
            loopback_address="host.docker.internal",
        )

        result = get_logs_endpoint_from_fileset(config, workspace="default", fileset_id="job-logs-123")

        assert result == (
            "http://host.docker.internal:3000/apis/files/v2/workspaces/default/filesets/job-logs-123/otlp/v1/logs"
        )


def _make_step(
    staleness_timeout: int = 0,
    created_at: datetime.datetime | None = None,
    step_spec: PlatformJobStepSpec | None = ...,  # type: ignore[assignment]
) -> PlatformJobStepWithContext:
    if step_spec is ...:
        step_spec = PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(provider="cpu", profile="default", container=ContainerSpec(image="img")),
            config={},
            lifecycle=StepLifecycle(staleness_timeout_seconds=staleness_timeout),
        )
    return PlatformJobStepWithContext(
        id="step-1",
        job="job-1",
        attempt_id="attempt-1",
        fileset="fileset-1",
        workspace="default",
        name="test-step",
        step_spec=step_spec,
        status=PlatformJobStatus.ACTIVE,
        created_at=created_at or datetime.datetime.now(datetime.timezone.utc),
    )


def _make_task(status: str = "active", updated_at: datetime.datetime | None = None) -> MagicMock:
    task = MagicMock()
    task.status = status
    task.updated_at = updated_at
    return task


def _make_backend(mock_sdk: MagicMock | None = None) -> MockKubernetesCPUJobBackend:
    sdk = mock_sdk or MagicMock()
    return MockKubernetesCPUJobBackend(nmp_sdk=sdk, execution_profile_config=MagicMock(), profile_name="default")


class TestCheckTaskStaleness:
    """Tests for JobBackend.check_step_is_stale."""

    def test_disabled_when_timeout_is_zero(self):
        backend = _make_backend()
        step = _make_step(staleness_timeout=0)

        assert backend.check_step_is_stale(step) is False

    def test_disabled_when_lifecycle_is_none(self):
        backend = _make_backend()
        step = _make_step()
        step.step_spec.lifecycle = None

        assert backend.check_step_is_stale(step) is False

    def test_not_stale_when_step_too_young(self):
        backend = _make_backend()
        step = _make_step(
            staleness_timeout=1800,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )

        assert backend.check_step_is_stale(step) is False
        backend._nmp_sdk.jobs.tasks.list.assert_not_called()

    def test_not_stale_when_no_active_tasks(self):
        mock_sdk = MagicMock()
        mock_sdk.jobs.tasks.list.return_value.data = [
            _make_task(status="completed"),
            _make_task(status="error"),
        ]
        backend = _make_backend(mock_sdk)
        step = _make_step(
            staleness_timeout=60,
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120),
        )

        assert backend.check_step_is_stale(step) is False

    def test_not_stale_when_task_recently_updated(self):
        mock_sdk = MagicMock()
        mock_sdk.jobs.tasks.list.return_value.data = [
            _make_task(status="active", updated_at=datetime.datetime.now(datetime.timezone.utc)),
        ]
        backend = _make_backend(mock_sdk)
        step = _make_step(
            staleness_timeout=60,
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120),
        )

        assert backend.check_step_is_stale(step) is False

    def test_stale_when_all_active_tasks_exceed_threshold(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        mock_sdk = MagicMock()
        mock_sdk.jobs.tasks.list.return_value.data = [
            _make_task(status="active", updated_at=now - datetime.timedelta(seconds=200)),
            _make_task(status="active", updated_at=now - datetime.timedelta(seconds=300)),
            _make_task(status="completed"),
        ]
        backend = _make_backend(mock_sdk)
        step = _make_step(
            staleness_timeout=60,
            created_at=now - datetime.timedelta(seconds=120),
        )

        assert backend.check_step_is_stale(step) is True

    def test_not_stale_when_one_active_task_is_fresh(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        mock_sdk = MagicMock()
        mock_sdk.jobs.tasks.list.return_value.data = [
            _make_task(status="active", updated_at=now - datetime.timedelta(seconds=200)),
            _make_task(status="active", updated_at=now - datetime.timedelta(seconds=10)),
        ]
        backend = _make_backend(mock_sdk)
        step = _make_step(
            staleness_timeout=60,
            created_at=now - datetime.timedelta(seconds=120),
        )

        assert backend.check_step_is_stale(step) is False

    def test_returns_false_on_api_failure(self):
        mock_sdk = MagicMock()
        mock_sdk.jobs.tasks.list.side_effect = RuntimeError("connection error")
        backend = _make_backend(mock_sdk)
        step = _make_step(
            staleness_timeout=60,
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120),
        )

        assert backend.check_step_is_stale(step) is False

    def test_handles_naive_updated_at_as_utc(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        naive_old = (now - datetime.timedelta(seconds=200)).replace(tzinfo=None)
        mock_sdk = MagicMock()
        mock_sdk.jobs.tasks.list.return_value.data = [
            _make_task(status="active", updated_at=naive_old),
        ]
        backend = _make_backend(mock_sdk)
        step = _make_step(
            staleness_timeout=60,
            created_at=now - datetime.timedelta(seconds=120),
        )

        assert backend.check_step_is_stale(step) is True

    def test_returns_false_when_task_missing_updated_at(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        mock_sdk = MagicMock()
        mock_sdk.jobs.tasks.list.return_value.data = [
            _make_task(status="active", updated_at=None),
        ]
        backend = _make_backend(mock_sdk)
        step = _make_step(
            staleness_timeout=60,
            created_at=now - datetime.timedelta(seconds=120),
        )

        assert backend.check_step_is_stale(step) is False


class TestResolveTaskImage:
    """Tests for resolve_task_image."""

    def test_explicit_image_takes_precedence(self):
        assert resolve_task_image("my-image:v1", "default-image:latest") == "my-image:v1"

    def test_falls_back_to_default_task_image(self):
        assert resolve_task_image(None, "default-image:latest") == "default-image:latest"

    def test_explicit_image_without_default(self):
        assert resolve_task_image("my-image:v1", None) == "my-image:v1"

    def test_falls_back_to_platform_cpu_tasks_image_when_both_none(self):
        with patch("nemo_platform_plugin.jobs.image.get_platform_config") as mock_config:
            mock_config.return_value = MagicMock(image_registry="my-registry", image_tag="v1.0")
            assert resolve_task_image(None, None) == "my-registry/nmp-cpu-tasks:v1.0"
