# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for K8sNimOperatorServiceBackend."""

import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes import client as k8s_client
from kubernetes.dynamic import exceptions as k8s_dynamic_exceptions
from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform.types.shared import LinearLayerSpec, MambaConfig, ModelSpec, MoEConfig, SlidingWindowConfig
from nmp.common.config import PlatformConfig
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.common import deployment_elapsed_seconds, format_duration
from nmp.core.models.controllers.backends.k8s_nim_operator import K8sNimOperatorServiceBackend
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.resource_deleter import ResourceDeleter
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.status_projector import StatusProjector
from nmp.core.models.controllers.context import ModelContext
from pydantic import ValidationError

_K8S_BACKEND_MODULE = "nmp.core.models.controllers.backends.k8s_nim_operator.backend"
_RECON_K8S_MODULE = "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.k8s"
_RECON_STATUS_MODULE = "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.status_projector"
_RECON_NIM_MODULE = "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator"


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _nim_config():
    """A minimal NIM-routing ModelDeploymentConfig-like object.

    Engine is explicitly ``nim`` so the backend routes status/create/update to the
    NIM reconciler (the backend rejects unknown engine strings rather than
    defaulting them to NIM). The NIM status path only reads ``resource_name``, so
    the resolved model fields are irrelevant here.
    """
    config = MagicMock()
    config.engine = "nim"
    return config


def _make_nimservice_mock(state: str, conditions: list | None = None):
    """Create a mock NIMService response dict."""
    mock_resource = MagicMock()
    mock_resource.get.return_value = {
        "status": {"state": state, "conditions": conditions or []},
    }
    return mock_resource


def _make_pod(
    name: str = "test-pod-abc123",
    restart_count: int = 0,
    waiting_reason: str | None = None,
    phase: str = "Running",
) -> MagicMock:
    """Create a mock V1Pod with configurable restart/waiting state."""
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.creation_timestamp = datetime.now(timezone.utc)
    pod.status.phase = phase

    cs = MagicMock()
    cs.restart_count = restart_count

    if waiting_reason:
        cs.state.waiting.reason = waiting_reason
        cs.state.waiting.message = f"Back-off restarting failed container in pod {name}"
    else:
        cs.state.waiting = None
        cs.state.running = MagicMock()

    pod.status.container_statuses = [cs]
    return pod


def _wire_pod_lookup(mock_apps_v1, mock_core_v1, pod):
    """Wire up AppsV1 + CoreV1 mocks so _get_pod_status_from_deployment finds *pod*."""
    mock_deployment = MagicMock()
    mock_deployment.spec.selector.match_labels = {"app": "test"}
    mock_apps_v1.read_namespaced_deployment.return_value = mock_deployment

    pods_list = MagicMock()
    pods_list.items = [pod]
    mock_core_v1.list_namespaced_pod.return_value = pods_list

    events_list = MagicMock()
    events_list.items = []
    mock_core_v1.list_namespaced_event.return_value = events_list


@contextlib.contextmanager
def _mock_pod_backend(k8s_backend, pod=None, *, pod_logs=""):
    """Context manager that wires up AppsV1Api / CoreV1Api mocks on *k8s_backend*.

    Yields ``(mock_apps_v1, mock_core_v1)`` for further customisation.
    """
    mock_apps_v1 = MagicMock()
    mock_core_v1 = MagicMock()

    if pod is not None:
        _wire_pod_lookup(mock_apps_v1, mock_core_v1, pod)

    mock_core_v1.read_namespaced_pod_log.return_value = pod_logs

    with (
        patch(f"{_RECON_STATUS_MODULE}.k8s_client.AppsV1Api", return_value=mock_apps_v1),
        patch(f"{_RECON_STATUS_MODULE}.k8s_client.CoreV1Api", return_value=mock_core_v1),
    ):
        yield mock_apps_v1, mock_core_v1


@pytest.fixture
def mock_nmp_sdk():
    """Create a mock AsyncNeMoPlatform SDK."""
    mock = AsyncMock()
    mock.secrets = AsyncMock()
    mock.secrets.access = AsyncMock(return_value=MagicMock(value="test-hf-token-value"))
    return mock


@pytest.fixture
def mock_k8s_config():
    """Mock kubernetes config loading to avoid needing actual k8s config."""
    with (
        patch(f"{_K8S_BACKEND_MODULE}.k8s_config.load_incluster_config"),
        patch(f"{_K8S_BACKEND_MODULE}.k8s_config.load_kube_config"),
        patch(f"{_K8S_BACKEND_MODULE}.k8s_client.ApiClient"),
        patch(f"{_K8S_BACKEND_MODULE}.DynamicClient"),
        patch(f"{_K8S_BACKEND_MODULE}.os.path.exists", return_value=False),
    ):
        yield


def create_model_spec():
    """Create a sample ModelSpec for testing."""
    model_spec = ModelSpec(
        base_num_parameters=7000000000,
        context_size=4096,
        num_virtual_tokens=0,
        is_chat=True,
        checkpoint_model_name="meta-llama/Llama-3.2-1b-instruct",
        family="llama",
        num_layers=32,
        hidden_size=4096,
        num_attention_heads=32,
        num_kv_heads=32,
        ffn_hidden_size=16384,
        vocab_size=32000,
        tied_embeddings=True,
        gated_mlp=True,
        precision="fp16",
        moe_config=MoEConfig(
            num_experts=128,
            num_experts_per_tok=128,
            num_expert_layers=128,
            expert_ffn_size=16384,
            num_shared_experts=128,
        ),
        mamba_config=MambaConfig(
            num_layers=32,
            hidden_size=4096,
            num_attention_heads=32,
            num_kv_heads=32,
            ffn_hidden_size=16384,
            vocab_size=32000,
            is_hybrid=True,
            num_mamba_layers=32,
        ),
        sliding_window_config=SlidingWindowConfig(
            window_size=1024,
        ),
        minimum_gpus_all_weights=1,
        minimum_gpus_lora=1,
        linear_layers=[
            LinearLayerSpec(
                name="linear-layer-1",
                in_features=4096,
                out_features=4096,
            )
        ],
    )
    return model_spec


@pytest.fixture
def k8s_backend(mock_nmp_sdk, mock_k8s_config):
    """Create a K8sNimOperatorServiceBackend instance for testing."""
    return K8sNimOperatorServiceBackend(
        nmp_sdk=mock_nmp_sdk,
        config={},
        huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
    )


def _sync_reconcilers(backend):
    """Propagate the backend's (test-mocked) k8s state onto its reconcilers.

    Tests assign mock clients/config/namespace onto the backend *after*
    construction (``backend._dynamic_client = MagicMock()`` etc.). Reconciliation
    logic now lives on the two reconcilers, which captured their own clients at
    ``init()`` time. This helper re-points the reconcilers at whatever the test
    set on the backend so delegation exercises the test's mocks. Call it after
    setting up the backend's ``_dynamic_client`` / ``_core_v1`` / ``_apps_v1`` /
    ``_batch_v1`` / ``_backend_config`` / ``_k8s_namespace`` / ``_k8s_client``.
    """
    nim = backend._nim_reconciler
    k8s = backend._k8s_reconciler
    status = getattr(backend, "_status_projector", None)
    deleter = getattr(backend, "_resource_deleter", None)
    namespace = backend._k8s_namespace
    config = backend._backend_config
    client = backend._k8s_client

    if nim is not None:
        nim._k8s_namespace = namespace
        nim._backend_config = config
        if backend._dynamic_client is not None:
            nim._dynamic_client = backend._dynamic_client
    if k8s is not None:
        k8s._k8s_namespace = namespace
        k8s._backend_config = config
        k8s._k8s_client = client
        if getattr(backend, "_core_v1", None) is not None:
            k8s._core_v1 = backend._core_v1
        if getattr(backend, "_apps_v1", None) is not None:
            k8s._apps_v1 = backend._apps_v1
        if getattr(backend, "_batch_v1", None) is not None:
            k8s._batch_v1 = backend._batch_v1
    if status is not None:
        status._k8s_namespace = namespace
        status._backend_config = config
        status._k8s_client = client
    if deleter is not None:
        deleter._k8s_namespace = namespace
    return backend


def _status_helper_reconciler(*, namespace="default", backend_config=None, k8s_client_=None):
    """Build a StatusProjector exposing the shared status helpers for direct tests."""
    return StatusProjector(
        k8s_client_=k8s_client_ if k8s_client_ is not None else MagicMock(),
        backend_config=backend_config if backend_config is not None else K8sNimOperatorConfig(),
        k8s_namespace=namespace,
    )


@pytest.fixture
def sample_deployment():
    """Create a sample ModelDeployment for testing.

    ``created_at`` defaults to 5 minutes ago so that PENDING timeout (2 h)
    does NOT fire in the majority of tests.  Override in individual tests
    when timeout behaviour needs to be exercised.
    """
    deployment = MagicMock()
    deployment.workspace = "default"
    deployment.name = "test-deployment"
    deployment.entity_version = "v1"
    deployment.status = "CREATED"
    deployment.config = "test-config"
    deployment.config_version = "v1"
    deployment.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    return deployment


@pytest.fixture
def sample_config():
    """Create a sample ModelDeploymentConfig for testing.

    Engine is explicitly ``nim`` so the backend routes it to the NIM-operator
    reconciler (the backend now rejects unknown engine strings rather than
    defaulting them to NIM).
    """
    config = MagicMock()
    config.engine = "nim"
    return config


@pytest.mark.asyncio
async def test_k8s_backend_create_model_deployment(k8s_backend, sample_deployment, sample_config):
    """Test creating a model deployment with K8s NIM Operator backend."""
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()

    # Mock the dynamic client resource operations
    mock_resource = MagicMock()
    mock_created = MagicMock()
    mock_created.metadata.uid = "test-uid"
    mock_resource.create.return_value = mock_created
    k8s_backend._dynamic_client.resources.get.return_value = mock_resource

    # Mock the compile_nimservice function to avoid validation issues
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
    ) as mock_compile:
        mock_nimservice = MagicMock()
        mock_nimservice.model_dump.return_value = {"apiVersion": "apps.nvidia.com/v1alpha1", "kind": "NIMService"}
        mock_compile.return_value = mock_nimservice

        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.create_model_deployment(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=sample_config)
        )

        # Verify compile_nimservice was called
        mock_compile.assert_called_once()

        # Verify status update returned
        assert status_update is not None
        assert status_update.status == "PENDING"
        assert "initiated successfully" in status_update.status_message
        assert status_update.host_url is not None


@pytest.mark.asyncio
async def test_k8s_backend_update_model_deployment(k8s_backend, sample_deployment, sample_config):
    """Test updating a model deployment with K8s NIM Operator backend."""
    # Mock the k8s clients
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()

    # Mock the dynamic client resource operations
    mock_resource = MagicMock()
    mock_updated = MagicMock()
    mock_updated.metadata.uid = "test-uid"
    mock_resource.replace.return_value = mock_updated
    k8s_backend._dynamic_client.resources.get.return_value = mock_resource

    # Mock the compile_nimservice function to avoid validation issues
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
    ) as mock_compile:
        mock_nimservice = MagicMock()
        mock_nimservice.model_dump.return_value = {"apiVersion": "apps.nvidia.com/v1alpha1", "kind": "NIMService"}
        mock_compile.return_value = mock_nimservice

        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.update_model_deployment(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=sample_config)
        )

        # Verify compile_nimservice was called
        mock_compile.assert_called_once()

        # Verify status update returned
        assert status_update is not None
        assert status_update.status == "PENDING"
        assert "initiated successfully" in status_update.status_message
        assert status_update.host_url is not None


@pytest.mark.asyncio
async def test_k8s_backend_get_model_deployment_status(k8s_backend, sample_deployment):
    """Test getting model deployment status with K8s NIM Operator backend."""
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = K8sNimOperatorConfig()

    k8s_backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("Ready")

    _sync_reconcilers(k8s_backend)
    status_update = await k8s_backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
    )

    assert status_update is not None
    assert status_update.status == "READY"
    assert status_update.status_message == ""
    assert status_update.host_url is not None


@pytest.mark.asyncio
async def test_k8s_backend_get_status_without_config_is_unknown(k8s_backend, sample_deployment):
    """No config -> backend cannot determine the engine/state, returns UNKNOWN.

    The controller retries on the next poll (which normally has a config) and
    escalates to ERROR after its retry budget; the backend does not probe.
    """
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = K8sNimOperatorConfig()
    _sync_reconcilers(k8s_backend)

    status_update = await k8s_backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=None)
    )

    assert status_update.status == "UNKNOWN"
    # No reconciler/cluster lookups happen without a config.
    k8s_backend._dynamic_client.resources.get.assert_not_called()


@pytest.mark.asyncio
async def test_k8s_backend_get_status_nimservice_not_found(k8s_backend, sample_deployment):
    """Test getting status when NIMService doesn't exist yet - should keep current status."""
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = K8sNimOperatorConfig()

    mock_resource = MagicMock()
    mock_resource.get.side_effect = k8s_dynamic_exceptions.NotFoundError(MagicMock())
    k8s_backend._dynamic_client.resources.get.return_value = mock_resource

    _sync_reconcilers(k8s_backend)
    status_update = await k8s_backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
    )

    assert status_update is not None
    assert status_update.status == "LOST"
    assert "not found" in status_update.status_message.lower()
    assert status_update.host_url is None


@pytest.mark.asyncio
async def test_k8s_backend_get_status_nimservice_not_ready(k8s_backend, sample_deployment):
    """Test getting status when NIMService is NotReady."""
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = K8sNimOperatorConfig()

    k8s_backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

    with patch.object(
        k8s_backend._status_projector,
        "pod_status_from_deployment",
        return_value=DeploymentStatusUpdate(
            status="PENDING", status_message="Waiting for NIMService to become ready", host_url=None
        ),
    ):
        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )

        assert status_update is not None
        assert status_update.status == "PENDING"
        assert "ready" in status_update.status_message.lower()
        # No elapsed/timeout in message (stable message to avoid new history entry every poll)
        assert status_update.host_url is None


@pytest.mark.asyncio
async def test_k8s_backend_get_status_nimservice_crash_loop_backoff(k8s_backend, sample_deployment):
    """Test getting status when NIMService pod is in CrashLoopBackoff with restarts >= max."""
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = K8sNimOperatorConfig()
    k8s_backend._k8s_client = MagicMock()

    k8s_backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

    pod = _make_pod(restart_count=5, waiting_reason="CrashLoopBackOff")

    with _mock_pod_backend(k8s_backend, pod=pod, pod_logs="ERROR: model failed to load"):
        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )

        assert status_update is not None
        assert status_update.status == "ERROR"
        assert "crash loop" in status_update.status_message
        assert "container restarts" in status_update.status_message
        assert "kubectl logs" in status_update.status_message
        assert status_update.error_details["reason"] == "crash_loop"
        assert status_update.error_details["restart_count"] == 5
        assert status_update.host_url is None


@pytest.mark.asyncio
async def test_k8s_backend_get_status_nimservice_pod_restarts_below_threshold(k8s_backend, sample_deployment):
    """Test getting status when pod has restarts but below the max_restart_count threshold."""
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = K8sNimOperatorConfig()
    k8s_backend._k8s_client = MagicMock()

    k8s_backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

    pod = _make_pod(restart_count=2)

    with _mock_pod_backend(k8s_backend, pod=pod):
        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )

        assert status_update is not None
        assert status_update.status == "PENDING"
        assert "restarts: 2" in status_update.status_message
        assert status_update.host_url is None


@pytest.mark.asyncio
async def test_k8s_backend_get_status_nimservice_pod_running_after_restarts(k8s_backend, sample_deployment):
    """Test getting status when pod has restarts >= max but is now running (not in waiting state)."""
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = K8sNimOperatorConfig()
    k8s_backend._k8s_client = MagicMock()

    k8s_backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

    pod = _make_pod(restart_count=5)  # No waiting_reason → running

    with _mock_pod_backend(k8s_backend, pod=pod):
        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )

        assert status_update is not None
        assert status_update.status == "PENDING"
        assert "restarts: 5" in status_update.status_message
        assert status_update.host_url is None


@pytest.mark.asyncio
async def test_k8s_backend_delete_model_deployment(k8s_backend, sample_deployment):
    """Test deleting a model deployment with K8s NIM Operator backend."""
    # Mock the k8s clients
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()

    # Mock the dynamic client resource operations
    mock_resource = MagicMock()
    k8s_backend._dynamic_client.resources.get.return_value = mock_resource

    _sync_reconcilers(k8s_backend)
    status_update = await k8s_backend.delete_model_deployment(sample_deployment.workspace, sample_deployment.name)

    # Verify status update returned
    assert status_update is not None
    assert status_update.status == "DELETED"
    assert "initiated successfully" in status_update.status_message


@pytest.mark.asyncio
async def test_k8s_backend_delete_model_deployment_with_secret(k8s_backend, sample_deployment):
    """Test deleting a model deployment."""
    # Mock the k8s clients
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()
    k8s_backend._k8s_client = MagicMock()

    # Mock the dynamic client resource operations
    mock_resource = MagicMock()
    k8s_backend._dynamic_client.resources.get.return_value = mock_resource

    _sync_reconcilers(k8s_backend)
    status_update = await k8s_backend.delete_model_deployment(sample_deployment.workspace, sample_deployment.name)

    # Verify status update returned
    assert status_update is not None
    assert status_update.status == "DELETED"
    assert "initiated successfully" in status_update.status_message


@pytest.mark.asyncio
async def test_k8s_backend_delete_model_deployment_without_secret(k8s_backend, sample_deployment):
    """Test deleting a model deployment (no HF secret)."""
    # Mock the k8s clients
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()

    # Mock the dynamic client resource operations
    mock_resource = MagicMock()
    k8s_backend._dynamic_client.resources.get.return_value = mock_resource

    _sync_reconcilers(k8s_backend)
    status_update = await k8s_backend.delete_model_deployment(sample_deployment.workspace, sample_deployment.name)

    # Verify status update returned
    assert status_update is not None
    assert status_update.status == "DELETED"


@pytest.mark.asyncio
async def test_delete_attempts_all_resource_types_and_tolerates_404(k8s_backend, sample_deployment):
    """Delete attempts CRs + raw vLLM objects by name; 404s are success -> DELETED."""
    k8s_backend._k8s_namespace = "default"
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._core_v1 = MagicMock()
    k8s_backend._apps_v1 = MagicMock()
    k8s_backend._batch_v1 = MagicMock()
    cr_api = MagicMock()
    cr_api.delete.side_effect = k8s_dynamic_exceptions.NotFoundError(MagicMock(status=404))
    k8s_backend._dynamic_client.resources.get.return_value = cr_api
    notfound = k8s_client.exceptions.ApiException(status=404)
    k8s_backend._apps_v1.delete_namespaced_deployment.side_effect = notfound
    k8s_backend._core_v1.delete_namespaced_service.side_effect = notfound
    k8s_backend._batch_v1.delete_namespaced_job.side_effect = notfound
    k8s_backend._core_v1.delete_namespaced_persistent_volume_claim.side_effect = notfound

    _sync_reconcilers(k8s_backend)
    result = await k8s_backend.delete_model_deployment("default", "qwen")

    assert result.status == "DELETED"
    assert k8s_backend._dynamic_client.resources.get.call_count == 2
    k8s_backend._apps_v1.delete_namespaced_deployment.assert_called_once()
    k8s_backend._core_v1.delete_namespaced_service.assert_called_once()
    k8s_backend._batch_v1.delete_namespaced_job.assert_called_once()
    k8s_backend._core_v1.delete_namespaced_persistent_volume_claim.assert_called_once()


@pytest.mark.asyncio
async def test_delete_real_failure_surfaces_error_but_attempts_all(k8s_backend, sample_deployment):
    """A non-404 delete failure -> ERROR (not DELETED), and other deletes still run."""
    k8s_backend._k8s_namespace = "default"
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._core_v1 = MagicMock()
    k8s_backend._apps_v1 = MagicMock()
    k8s_backend._batch_v1 = MagicMock()
    cr_api = MagicMock()
    cr_api.delete.side_effect = k8s_dynamic_exceptions.NotFoundError(MagicMock(status=404))
    k8s_backend._dynamic_client.resources.get.return_value = cr_api
    k8s_backend._apps_v1.delete_namespaced_deployment.side_effect = k8s_client.exceptions.ApiException(status=500)
    notfound = k8s_client.exceptions.ApiException(status=404)
    k8s_backend._core_v1.delete_namespaced_service.side_effect = notfound
    k8s_backend._batch_v1.delete_namespaced_job.side_effect = notfound
    k8s_backend._core_v1.delete_namespaced_persistent_volume_claim.side_effect = notfound

    _sync_reconcilers(k8s_backend)
    result = await k8s_backend.delete_model_deployment("default", "qwen")

    assert result.status == "ERROR"
    k8s_backend._core_v1.delete_namespaced_service.assert_called_once()
    k8s_backend._core_v1.delete_namespaced_persistent_volume_claim.assert_called_once()


@pytest.mark.asyncio
async def test_delete_forbidden_cr_does_not_block_vllm_cleanup(k8s_backend, sample_deployment):
    """A 403 deleting a NIMService still lets the raw vLLM objects be deleted (and surfaces ERROR)."""
    k8s_backend._k8s_namespace = "default"
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._core_v1 = MagicMock()
    k8s_backend._apps_v1 = MagicMock()
    k8s_backend._batch_v1 = MagicMock()
    cr_api = MagicMock()
    cr_api.delete.side_effect = k8s_dynamic_exceptions.ForbiddenError(MagicMock(status=403))
    k8s_backend._dynamic_client.resources.get.return_value = cr_api

    _sync_reconcilers(k8s_backend)
    result = await k8s_backend.delete_model_deployment("default", "qwen")

    assert result.status == "ERROR"
    assert "forbidden" in result.status_message.lower()
    k8s_backend._apps_v1.delete_namespaced_deployment.assert_called_once()
    k8s_backend._core_v1.delete_namespaced_persistent_volume_claim.assert_called_once()


def test_delete_one_404_is_success():
    """A typed 404 (object absent) is treated as success -> returns None."""
    deleter = ResourceDeleter(k8s_namespace="default")
    delete_fn = MagicMock(side_effect=k8s_client.exceptions.ApiException(status=404))
    assert deleter.delete_one(delete_fn, "PVC", "obj") is None


def test_delete_one_dynamic_notfound_is_success():
    """A dynamic NotFoundError is treated as success -> returns None."""
    deleter = ResourceDeleter(k8s_namespace="default")
    delete_fn = MagicMock(side_effect=k8s_dynamic_exceptions.NotFoundError(MagicMock(status=404)))
    assert deleter.delete_one(delete_fn, "PVC", "obj") is None


def test_delete_one_forbidden_is_classified_not_raised():
    """A 403 is classified and returned as an error string, not raised."""
    deleter = ResourceDeleter(k8s_namespace="default")
    delete_fn = MagicMock(side_effect=k8s_client.exceptions.ApiException(status=403))
    err = deleter.delete_one(delete_fn, "PVC", "obj")
    assert err is not None
    assert "forbidden" in err.lower()


def test_delete_one_unexpected_exception_is_classified_not_raised():
    """A non-API/transport error must be classified and returned, never raised.

    Guards the aggregation contract: the caller's per-resource delete loop must
    continue (and surface the failure) rather than abort cleanup partway.
    """
    deleter = ResourceDeleter(k8s_namespace="default")
    delete_fn = MagicMock(side_effect=ConnectionError("connection reset"))
    err = deleter.delete_one(delete_fn, "Deployment", "obj")
    assert err is not None
    assert "error deleting Deployment obj" in err


def test_k8s_backend_initialization(mock_nmp_sdk, mock_k8s_config):
    """Test K8s NIM Operator backend initializes correctly with custom namespace config."""
    config = {"namespace": "nim-system"}
    huggingface_model_puller = "nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10"

    backend = K8sNimOperatorServiceBackend(
        nmp_sdk=mock_nmp_sdk,
        config=config,
        huggingface_model_puller=huggingface_model_puller,
    )

    # Verify backend initialized correctly with custom config
    # Parent __init__ calls init() automatically, so everything should be set up
    assert backend is not None
    assert backend._nmp_sdk == mock_nmp_sdk
    assert backend._config == config
    assert backend._huggingface_model_puller == huggingface_model_puller
    # After init(), these should be set (mocked by mock_k8s_config fixture)
    assert backend._backend_config is not None
    # The custom namespace from config should be used
    assert backend._k8s_namespace == "nim-system"


def test_k8s_backend_initialization_with_empty_config(k8s_backend):
    """Test K8s NIM Operator backend initializes correctly with empty config and defaults to 'default' namespace."""
    # The fixture creates backend with empty config
    # Verify backend was fully initialized
    assert k8s_backend is not None
    assert k8s_backend._config == {}
    assert k8s_backend._huggingface_model_puller == "nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10"
    # After init(), these should be set (mocked by mock_k8s_config fixture)
    assert k8s_backend._backend_config is not None
    # With empty config and no service account file, should default to "default"
    assert k8s_backend._k8s_namespace == "default"


@pytest.mark.asyncio
async def test_k8s_backend_create_when_nimservice_already_exists(k8s_backend, sample_deployment, sample_config):
    """Test creating a deployment when NIMService already exists - should return PENDING without error."""
    # Mock the k8s clients
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()

    # Mock the dynamic client to raise ConflictError on create
    mock_resource = MagicMock()
    mock_resource.create.side_effect = k8s_dynamic_exceptions.ConflictError(MagicMock())
    k8s_backend._dynamic_client.resources.get.return_value = mock_resource

    # Mock the compile_nimservice function
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
    ) as mock_compile:
        mock_nimservice = MagicMock()
        mock_nimservice.model_dump.return_value = {"apiVersion": "apps.nvidia.com/v1alpha1", "kind": "NIMService"}
        mock_compile.return_value = mock_nimservice

        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.create_model_deployment(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=sample_config)
        )

        # Verify status update returned PENDING (not ERROR)
        assert status_update is not None
        assert status_update.status == "PENDING"
        assert "initiated successfully" in status_update.status_message
        assert status_update.host_url is not None

        # Verify create was attempted but replace was NOT called
        mock_resource.create.assert_called_once()
        mock_resource.replace.assert_not_called()


# ============================================================================
# SFT Model Deployment Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_model_deployment_with_sft_model(k8s_backend, sample_deployment, sample_config):
    """Test that SFT models trigger NIMCache creation."""
    # Setup backend state
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()
    k8s_backend._backend_config.default_storage_class = "local-storage"
    k8s_backend._backend_config.default_pvc_size = "200Gi"
    k8s_backend._backend_config.files_auth_secret = "nemo-models-files-token"
    k8s_backend._backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    k8s_backend._backend_config.default_user_id = None
    k8s_backend._backend_config.default_group_id = None
    k8s_backend._backend_config.default_resources = None
    k8s_backend._backend_config.default_tolerations = None
    k8s_backend._backend_config.default_node_selector = None

    # Configure sample_config for SFT
    sample_config.engine = "nim"
    sample_config.model_spec = MagicMock()
    sample_config.executor_config = MagicMock()
    sample_config.model_spec.model_namespace = "test-ns"
    sample_config.model_spec.model_name = "test-model"
    sample_config.model_spec.model_revision = None
    sample_config.executor_config.disk_size = "300Gi"

    # Create SFT model entity with fileset matching the model name
    sft_model_entity = ModelEntity(
        id="model-1",
        entity_id="model-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        workspace="test-ns",
        name="test-model",
        parent="models",
        db_version=1,
        fileset="test-ns/test-model",
        spec=create_model_spec(),
    )

    # Mock the dynamic client resource operations for both NIMCache and NIMService
    mock_nimcache_resource = MagicMock()
    mock_nimservice_resource = MagicMock()
    mock_created_cache = MagicMock()
    mock_created_cache.metadata.uid = "cache-uid"
    mock_created_service = MagicMock()
    mock_created_service.metadata.uid = "service-uid"

    mock_nimcache_resource.create.return_value = mock_created_cache
    mock_nimservice_resource.create.return_value = mock_created_service

    def get_resource_side_effect(api_version, kind):
        if kind == "NIMCache":
            return mock_nimcache_resource
        elif kind == "NIMService":
            return mock_nimservice_resource
        return MagicMock()

    k8s_backend._dynamic_client.resources.get.side_effect = get_resource_side_effect

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        with patch(
            "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
        ) as mock_compile:
            mock_nimservice = MagicMock()
            mock_nimservice.model_dump.return_value = {"apiVersion": "apps.nvidia.com/v1alpha1", "kind": "NIMService"}
            mock_compile.return_value = mock_nimservice

            _sync_reconcilers(k8s_backend)
            status_update = await k8s_backend.create_model_deployment(
                ModelContext(
                    model_deployment=sample_deployment,
                    model_deployment_config=sample_config,
                    model_entity=sft_model_entity,
                )
            )

            # Verify NIMCache was created
            mock_nimcache_resource.create.assert_called_once()
            nimcache_call_args = mock_nimcache_resource.create.call_args
            created_nimcache = nimcache_call_args.kwargs["body"]
            assert created_nimcache["kind"] == "NIMCache"
            assert created_nimcache["spec"]["source"]["hf"]["namespace"] == "test-ns"
            assert created_nimcache["spec"]["source"]["hf"]["modelName"] == "test-model"

            # Verify compile_nimservice was called with nimcache_name
            mock_compile.assert_called_once()
            compile_call_kwargs = mock_compile.call_args.kwargs
            assert compile_call_kwargs["nimcache_name"] is not None

            # Verify status update returned
            assert status_update is not None
            assert status_update.status == "PENDING"


@pytest.mark.asyncio
async def test_create_model_deployment_with_files_service_model_triggers_nimcache(
    k8s_backend, sample_deployment, sample_config
):
    """Test that FILES_SERVICE (fileset-backed, non-SFT) models trigger NIMCache creation."""
    # Setup backend state
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()
    k8s_backend._backend_config.default_storage_class = "local-storage"
    k8s_backend._backend_config.default_pvc_size = "200Gi"
    k8s_backend._backend_config.files_auth_secret = "nemo-models-files-token"
    k8s_backend._backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    k8s_backend._backend_config.default_user_id = None
    k8s_backend._backend_config.default_group_id = None
    k8s_backend._backend_config.default_resources = None
    k8s_backend._backend_config.default_tolerations = None
    k8s_backend._backend_config.default_node_selector = None

    # Configure sample_config
    sample_config.engine = "nim"
    sample_config.model_spec = MagicMock()
    sample_config.executor_config = MagicMock()
    sample_config.model_spec.model_namespace = "test-ns"
    sample_config.model_spec.model_name = "test-model"
    sample_config.model_spec.model_revision = None
    sample_config.executor_config.disk_size = "300Gi"

    # FILES_SERVICE: fileset set but NOT SFT (no spec, no finetuning_type LORA_MERGED/ALL_WEIGHTS)
    files_service_model_entity = ModelEntity(
        id="model-1",
        entity_id="model-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        workspace="test-ns",
        name="test-model",
        parent="models",
        db_version=1,
        fileset="test-ns/test-model",
        spec=None,
    )

    # Mock the dynamic client resource operations for both NIMCache and NIMService
    mock_nimcache_resource = MagicMock()
    mock_nimservice_resource = MagicMock()
    mock_created_cache = MagicMock()
    mock_created_cache.metadata.uid = "cache-uid"
    mock_created_service = MagicMock()
    mock_created_service.metadata.uid = "service-uid"

    mock_nimcache_resource.create.return_value = mock_created_cache
    mock_nimservice_resource.create.return_value = mock_created_service

    def get_resource_side_effect(api_version, kind):
        if kind == "NIMCache":
            return mock_nimcache_resource
        elif kind == "NIMService":
            return mock_nimservice_resource
        return MagicMock()

    k8s_backend._dynamic_client.resources.get.side_effect = get_resource_side_effect

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        with patch(
            "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
        ) as mock_compile:
            mock_nimservice = MagicMock()
            mock_nimservice.model_dump.return_value = {"apiVersion": "apps.nvidia.com/v1alpha1", "kind": "NIMService"}
            mock_compile.return_value = mock_nimservice

            _sync_reconcilers(k8s_backend)
            status_update = await k8s_backend.create_model_deployment(
                ModelContext(
                    model_deployment=sample_deployment,
                    model_deployment_config=sample_config,
                    model_entity=files_service_model_entity,
                )
            )

            # Verify NIMCache was created for FILES_SERVICE
            mock_nimcache_resource.create.assert_called_once()
            nimcache_call_args = mock_nimcache_resource.create.call_args
            created_nimcache = nimcache_call_args.kwargs["body"]
            assert created_nimcache["kind"] == "NIMCache"
            assert created_nimcache["spec"]["source"]["hf"]["namespace"] == "test-ns"
            assert created_nimcache["spec"]["source"]["hf"]["modelName"] == "test-model"

            # Verify compile_nimservice was called with nimcache_name
            mock_compile.assert_called_once()
            compile_call_kwargs = mock_compile.call_args.kwargs
            assert compile_call_kwargs["nimcache_name"] is not None

            # Verify status update returned
            assert status_update is not None
            assert status_update.status == "PENDING"


@pytest.mark.asyncio
async def test_create_model_deployment_without_sft_model(k8s_backend, sample_deployment, sample_config):
    """Test that non-SFT models do NOT trigger NIMCache creation."""
    # Setup backend state
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()

    # Configure sample_config
    sample_config.engine = "nim"
    sample_config.model_spec = MagicMock()
    sample_config.executor_config = MagicMock()
    sample_config.model_spec.model_namespace = "test-ns"
    sample_config.model_spec.model_name = "test-model"

    # Create non-SFT model entity
    non_sft_model_entity = ModelEntity(
        id="model-1",
        entity_id="model-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        workspace="test-ns",
        name="test-model",
        parent="models",
        db_version=1,
        fileset=None,
    )

    # Mock the dynamic client resource operations for NIMService only
    mock_nimservice_resource = MagicMock()
    mock_created_service = MagicMock()
    mock_created_service.metadata.uid = "service-uid"
    mock_nimservice_resource.create.return_value = mock_created_service
    k8s_backend._dynamic_client.resources.get.return_value = mock_nimservice_resource

    # Mock the compile_nimservice function
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
    ) as mock_compile:
        mock_nimservice = MagicMock()
        mock_nimservice.model_dump.return_value = {"apiVersion": "apps.nvidia.com/v1alpha1", "kind": "NIMService"}
        mock_compile.return_value = mock_nimservice

        _sync_reconcilers(k8s_backend)
        status_update = await k8s_backend.create_model_deployment(
            ModelContext(
                model_deployment=sample_deployment,
                model_deployment_config=sample_config,
                model_entity=non_sft_model_entity,
            )
        )

        # Verify compile_nimservice was called with nimcache_name=None
        mock_compile.assert_called_once()
        compile_call_kwargs = mock_compile.call_args.kwargs
        assert compile_call_kwargs["nimcache_name"] is None

        # Verify status update returned
        assert status_update is not None
        assert status_update.status == "PENDING"


@pytest.mark.asyncio
async def test_create_model_deployment_with_sft_model_and_revision(k8s_backend, sample_deployment, sample_config):
    """Test that SFT models with revision in model_name trigger NIMCache creation with parsed revision."""
    # Setup backend state
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()
    k8s_backend._backend_config.default_pvc_size = "100Gi"
    k8s_backend._backend_config.default_storage_class = "standard"
    k8s_backend._backend_config.default_user_id = 1000
    k8s_backend._backend_config.default_group_id = 1000
    k8s_backend._backend_config.files_auth_secret = "files-api-token"
    k8s_backend._backend_config.huggingface_model_puller_image_pull_secret = "nvcrimagepullsecret"
    k8s_backend._backend_config.default_resources = None
    k8s_backend._backend_config.default_tolerations = None
    k8s_backend._backend_config.default_node_selector = None

    # Configure sample_config with model name containing revision
    sample_config.engine = "nim"
    sample_config.model_spec = MagicMock()
    sample_config.executor_config = MagicMock()
    sample_config.model_spec.model_namespace = "test-ns"
    sample_config.model_spec.model_name = "test-model@v1.0"
    sample_config.model_spec.model_revision = None
    sample_config.executor_config.disk_size = "50Gi"

    # Create SFT model entity with fileset matching the model name
    sft_model_entity = ModelEntity(
        id="model-1",
        entity_id="model-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        workspace="test-ns",
        name="test-model",
        parent="models",
        db_version=1,
        fileset="test-ns/test-model",
        spec=create_model_spec(),
    )

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        # Mock the dynamic client resource operations
        mock_nimcache_resource = MagicMock()
        mock_nimservice_resource = MagicMock()
        mock_created_cache = MagicMock()
        mock_created_cache.metadata.name = "test-cache"
        mock_nimcache_resource.create.return_value = mock_created_cache
        mock_created_service = MagicMock()
        mock_created_service.metadata.uid = "service-uid"
        mock_nimservice_resource.create.return_value = mock_created_service

        def get_resource(api_version, kind):
            if kind == "NIMCache":
                return mock_nimcache_resource
            return mock_nimservice_resource

        k8s_backend._dynamic_client.resources.get.side_effect = get_resource

        # Mock the compile_nimservice function
        with patch(
            "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
        ) as mock_compile:
            mock_nimservice = MagicMock()
            mock_nimservice.model_dump.return_value = {
                "apiVersion": "apps.nvidia.com/v1alpha1",
                "kind": "NIMService",
            }
            mock_compile.return_value = mock_nimservice

            _sync_reconcilers(k8s_backend)
            status_update = await k8s_backend.create_model_deployment(
                ModelContext(
                    model_deployment=sample_deployment,
                    model_deployment_config=sample_config,
                    model_entity=sft_model_entity,
                )
            )

            # Verify NIMCache was created
            assert mock_nimcache_resource.create.called

            # Verify the NIMCache has the correct model name (without @revision) and revision field
            nimcache_call = mock_nimcache_resource.create.call_args
            nimcache_dict = nimcache_call.kwargs["body"]
            # The body is a dict from model_dump()
            assert nimcache_dict["spec"]["source"]["hf"]["modelName"] == "test-model"
            assert nimcache_dict["spec"]["source"]["hf"]["revision"] == "v1.0"

            # Verify compile_nimservice was called with nimcache_name
            mock_compile.assert_called_once()
            compile_call_kwargs = mock_compile.call_args.kwargs
            assert compile_call_kwargs["nimcache_name"] is not None

            # Verify status update returned
            assert status_update is not None
            assert status_update.status == "PENDING"


@pytest.mark.asyncio
async def test_create_model_deployment_nimcache_uses_fileset_not_entity_name(
    k8s_backend, sample_deployment, sample_config
):
    """Test that NIMCache uses the fileset name from model entity, not the model entity name.

    This is the critical scenario for LoRA deployments where the base model entity
    name differs from the backing fileset name. The HF-compatible Files API resolves
    by fileset name, so the NIMCache must use the fileset path.
    """
    k8s_backend._dynamic_client = MagicMock()
    k8s_backend._k8s_namespace = "default"
    k8s_backend._backend_config = MagicMock()
    k8s_backend._backend_config.default_storage_class = "local-storage"
    k8s_backend._backend_config.default_pvc_size = "200Gi"
    k8s_backend._backend_config.files_auth_secret = "nemo-models-files-token"
    k8s_backend._backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    k8s_backend._backend_config.default_user_id = None
    k8s_backend._backend_config.default_group_id = None
    k8s_backend._backend_config.default_resources = None
    k8s_backend._backend_config.default_tolerations = None
    k8s_backend._backend_config.default_node_selector = None

    sample_config.engine = "nim"
    sample_config.model_spec = MagicMock()
    sample_config.executor_config = MagicMock()
    sample_config.model_spec.model_namespace = "my-workspace"
    sample_config.model_spec.model_name = "my-model-entity"
    sample_config.model_spec.model_revision = None
    sample_config.executor_config.disk_size = "300Gi"

    mismatched_model_entity = ModelEntity(
        id="model-1",
        entity_id="model-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        workspace="my-workspace",
        name="my-model-entity",
        parent="models",
        db_version=1,
        fileset="my-workspace/my-actual-fileset",
        spec=None,
    )

    mock_nimcache_resource = MagicMock()
    mock_nimservice_resource = MagicMock()
    mock_created_cache = MagicMock()
    mock_created_cache.metadata.uid = "cache-uid"
    mock_created_service = MagicMock()
    mock_created_service.metadata.uid = "service-uid"
    mock_nimcache_resource.create.return_value = mock_created_cache
    mock_nimservice_resource.create.return_value = mock_created_service

    def get_resource_side_effect(api_version, kind):
        if kind == "NIMCache":
            return mock_nimcache_resource
        elif kind == "NIMService":
            return mock_nimservice_resource
        return MagicMock()

    k8s_backend._dynamic_client.resources.get.side_effect = get_resource_side_effect

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        with patch(
            "nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator.compile_nimservice"
        ) as mock_compile:
            mock_nimservice = MagicMock()
            mock_nimservice.model_dump.return_value = {"apiVersion": "apps.nvidia.com/v1alpha1", "kind": "NIMService"}
            mock_compile.return_value = mock_nimservice

            _sync_reconcilers(k8s_backend)
            status_update = await k8s_backend.create_model_deployment(
                ModelContext(
                    model_deployment=sample_deployment,
                    model_deployment_config=sample_config,
                    model_entity=mismatched_model_entity,
                )
            )

            mock_nimcache_resource.create.assert_called_once()
            nimcache_call_args = mock_nimcache_resource.create.call_args
            created_nimcache = nimcache_call_args.kwargs["body"]
            assert created_nimcache["kind"] == "NIMCache"
            assert created_nimcache["spec"]["source"]["hf"]["namespace"] == "my-workspace"
            assert created_nimcache["spec"]["source"]["hf"]["modelName"] == "my-actual-fileset"

            assert status_update is not None
            assert status_update.status == "PENDING"


# ============================================================================
# Config field tests
# ============================================================================


class TestConfigFields:
    """Tests for K8sNimOperatorConfig pending_timeout_seconds and max_restart_count."""

    def test_defaults(self):
        config = K8sNimOperatorConfig()
        assert config.pending_timeout_seconds == 7200
        assert config.max_restart_count == 5

    def test_explicit_values(self):
        config = K8sNimOperatorConfig(pending_timeout_seconds=120, max_restart_count=3)
        assert config.pending_timeout_seconds == 120
        assert config.max_restart_count == 3

    def test_pending_timeout_minimum(self):
        with pytest.raises(ValidationError):
            K8sNimOperatorConfig(pending_timeout_seconds=30)

    def test_max_restart_count_minimum(self):
        with pytest.raises(ValidationError):
            K8sNimOperatorConfig(max_restart_count=0)


# ============================================================================
# Static helper unit tests
# ============================================================================


class TestFormatDuration:
    """Tests for shared format_duration helper."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0s"),
            (59, "59s"),
            (60, "1m 0s"),
            (90, "1m 30s"),
            (3600, "1h 0s"),
            (3661, "1h 1m 1s"),
            (7200, "2h 0s"),
            (7325, "2h 2m 5s"),
        ],
    )
    def test_format_duration(self, seconds, expected):
        assert format_duration(seconds) == expected


class TestWithRestartInfo:
    """Tests for StatusProjector._with_restart_info."""

    def test_no_restarts(self):
        assert StatusProjector._with_restart_info("some status", 0) == "some status"

    def test_with_restarts(self):
        assert StatusProjector._with_restart_info("some status", 3) == "some status, restarts: 3"


class TestGetPodRestartCount:
    """Tests for StatusProjector._get_pod_restart_count."""

    def test_no_container_statuses(self):
        pod = MagicMock()
        pod.status.container_statuses = None
        assert StatusProjector._get_pod_restart_count(pod) == 0

    def test_multiple_containers_returns_max(self):
        pod = MagicMock()
        cs1 = MagicMock()
        cs1.restart_count = 2
        cs2 = MagicMock()
        cs2.restart_count = 7
        pod.status.container_statuses = [cs1, cs2]
        assert StatusProjector._get_pod_restart_count(pod) == 7


class TestDeploymentElapsedSeconds:
    """Tests for shared deployment_elapsed_seconds helper."""

    def test_returns_positive_elapsed(self):
        deployment = MagicMock()
        deployment.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        elapsed = deployment_elapsed_seconds(deployment)
        assert 590 <= elapsed <= 620

    def test_handles_naive_datetime(self):
        deployment = MagicMock()
        deployment.created_at = (datetime.now(timezone.utc) - timedelta(seconds=30)).replace(tzinfo=None)
        elapsed = deployment_elapsed_seconds(deployment)
        assert 25 <= elapsed <= 35

    def test_returns_zero_when_created_at_is_none(self):
        deployment = MagicMock()
        deployment.created_at = None
        assert deployment_elapsed_seconds(deployment) == 0.0


# ============================================================================
# PENDING timeout status transitions
# ============================================================================


class TestPendingTimeoutStatusTransition:
    """Tests for PENDING -> ERROR transition based on deployment.created_at."""

    @pytest.fixture
    def backend_with_short_timeout(self, mock_nmp_sdk, mock_k8s_config):
        backend = K8sNimOperatorServiceBackend(nmp_sdk=mock_nmp_sdk, config={}, huggingface_model_puller="img:tag")
        backend._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=60, max_restart_count=5)
        backend._k8s_namespace = "default"
        return backend

    @pytest.mark.asyncio
    async def test_pending_within_timeout_stays_pending(self, backend_with_short_timeout, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(seconds=30)

        backend = backend_with_short_timeout
        backend._dynamic_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        with patch.object(
            backend._status_projector,
            "pod_status_from_deployment",
            return_value=DeploymentStatusUpdate(status="PENDING", status_message="Waiting", host_url=None),
        ):
            _sync_reconcilers(backend)
            result = await backend.get_model_deployment_status(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
            )
            assert result.status == "PENDING"
            # No elapsed/timeout in message (stable message to avoid new history entry every poll)

    @pytest.mark.asyncio
    async def test_pending_beyond_timeout_transitions_to_error(self, backend_with_short_timeout, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(seconds=120)

        backend = backend_with_short_timeout
        backend._dynamic_client = MagicMock()
        backend._k8s_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        with patch.object(
            backend._status_projector,
            "pod_status_from_deployment",
            return_value=DeploymentStatusUpdate(status="PENDING", status_message="Waiting", host_url=None),
        ):
            with _mock_pod_backend(backend, pod_logs="timeout error log"):
                _sync_reconcilers(backend)
                result = await backend.get_model_deployment_status(
                    ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
                )
                assert result.status == "ERROR"
                assert "timed out" in result.status_message
                assert "kubectl logs" in result.status_message
                assert result.error_details["reason"] == "pending_timeout"

    @pytest.mark.asyncio
    async def test_ready_not_affected_by_elapsed_time(self, backend_with_short_timeout, sample_deployment):
        """READY status should be returned as-is regardless of elapsed time."""
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=10)

        backend = backend_with_short_timeout
        backend._dynamic_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("Ready")

        _sync_reconcilers(backend)
        result = await backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )
        assert result.status == "READY"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("nim_state", ["Ready", "Failed"])
    async def test_terminal_states_not_affected_by_timeout(
        self, backend_with_short_timeout, sample_deployment, nim_state
    ):
        """Terminal NIMService states should never be overridden by timeout logic."""
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=10)

        backend = backend_with_short_timeout
        backend._dynamic_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock(nim_state)

        _sync_reconcilers(backend)
        result = await backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )
        assert result.status != "PENDING"

    @pytest.mark.asyncio
    async def test_pending_timeout_at_exact_boundary(self, backend_with_short_timeout, sample_deployment):
        """At exactly the timeout boundary, should transition to ERROR."""
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(seconds=60)

        backend = backend_with_short_timeout
        backend._dynamic_client = MagicMock()
        backend._k8s_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        with patch.object(
            backend._status_projector,
            "pod_status_from_deployment",
            return_value=DeploymentStatusUpdate(status="PENDING", status_message="Waiting", host_url=None),
        ):
            with _mock_pod_backend(backend):
                _sync_reconcilers(backend)
                result = await backend.get_model_deployment_status(
                    ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
                )
                assert result.status == "ERROR"
                assert result.error_details["reason"] == "pending_timeout"


# ============================================================================
# Crash loop detection
# ============================================================================


class TestCrashLoopDetection:
    """Tests for crash loop detection via _check_crash_loop."""

    @pytest.fixture
    def backend(self, mock_nmp_sdk, mock_k8s_config):
        return _status_helper_reconciler(
            namespace="test-ns",
            backend_config=K8sNimOperatorConfig(pending_timeout_seconds=7200, max_restart_count=5),
        )

    def test_no_container_statuses(self, backend):
        pod = MagicMock()
        pod.metadata.name = "pod-1"
        pod.status.phase = "Pending"
        pod.status.container_statuses = None
        assert backend.check_crash_loop(pod, "res-1") is None

    def test_below_threshold_no_error(self, backend):
        pod = _make_pod(restart_count=4, waiting_reason="CrashLoopBackOff")
        assert backend.check_crash_loop(pod, "res-1") is None

    def test_at_threshold_with_waiting_returns_error(self, backend):
        pod = _make_pod(restart_count=5, waiting_reason="CrashLoopBackOff")

        with _mock_pod_backend(backend, pod_logs="crash log"):
            result = backend.check_crash_loop(pod, "res-1")
            assert result is not None
            assert result.status == "ERROR"
            assert result.error_details["reason"] == "crash_loop"
            assert result.error_details["restart_count"] == 5
            assert result.error_details["max_restart_count"] == 5

    def test_above_threshold_without_waiting_returns_none(self, backend):
        pod = _make_pod(restart_count=10)  # running, not waiting
        result = backend.check_crash_loop(pod, "res-1")
        assert result is None

    @pytest.mark.parametrize("max_restarts", [1, 3, 10])
    def test_configurable_threshold(self, backend, max_restarts):
        backend._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=7200, max_restart_count=max_restarts)
        pod = _make_pod(restart_count=max_restarts, waiting_reason="CrashLoopBackOff")
        with _mock_pod_backend(backend, pod_logs=""):
            result = backend.check_crash_loop(pod, "res-1")
            assert result is not None
            assert result.status == "ERROR"

    def test_crash_loop_error_includes_kubectl_command(self, backend):
        pod = _make_pod(name="my-pod-xyz", restart_count=5, waiting_reason="CrashLoopBackOff")
        with _mock_pod_backend(backend, pod_logs="some logs"):
            result = backend.check_crash_loop(pod, "res-1")
            assert "kubectl logs -n test-ns my-pod-xyz" in result.status_message

    def test_crash_loop_error_includes_pod_logs_in_details(self, backend):
        pod = _make_pod(restart_count=5, waiting_reason="CrashLoopBackOff")
        with _mock_pod_backend(backend, pod_logs="RuntimeError: CUDA OOM"):
            result = backend.check_crash_loop(pod, "res-1")
            assert result.error_details["error_stack"] == "RuntimeError: CUDA OOM"


# ============================================================================
# Error message content tests
# ============================================================================


class TestPendingTimeoutErrorMessage:
    """Tests for the error message content of pending timeout."""

    @pytest.fixture
    def backend(self, mock_nmp_sdk, mock_k8s_config):
        return _status_helper_reconciler(
            namespace="my-ns",
            backend_config=K8sNimOperatorConfig(pending_timeout_seconds=120, max_restart_count=5),
        )

    def test_error_message_with_pod_name(self, backend):
        with _mock_pod_backend(backend, pod_logs="error log tail"):
            result = backend.build_pending_timeout_error("my-resource", 150.0, "my-pod-123")
            assert result.status == "ERROR"
            assert "timed out" in result.status_message
            assert "kubectl logs -n my-ns my-pod-123" in result.status_message
            assert result.error_details["pod_name"] == "my-pod-123"
            assert result.error_details["namespace"] == "my-ns"
            assert result.error_details["reason"] == "pending_timeout"

    def test_error_message_without_pod_name(self, backend):
        result = backend.build_pending_timeout_error("my-resource", 150.0, None)
        assert "kubectl logs -n my-ns deployment/my-resource" in result.status_message
        assert "pod_name" not in result.error_details

    def test_error_details_contain_timing(self, backend):
        result = backend.build_pending_timeout_error("res", 200.0, None)
        assert result.error_details["elapsed_seconds"] == 200
        assert result.error_details["timeout_seconds"] == 120

    def test_crash_loop_error_message(self, backend):
        with _mock_pod_backend(backend, pod_logs="segfault"):
            result = backend.build_crash_loop_error("res", "pod-abc", 7)
            assert result.status == "ERROR"
            assert "crash loop" in result.status_message
            assert "7 container restarts" in result.status_message
            assert "max: 5" in result.status_message
            assert "kubectl logs -n my-ns pod-abc" in result.status_message
            assert result.error_details["error_stack"] == "segfault"


# ============================================================================
# Controller restart resilience
# ============================================================================


class TestControllerRestartResilience:
    """Verify that timeout detection works after a controller restart.

    Because we use deployment.created_at from the entity store (not in-memory
    tracking), a new controller instance with no prior state should still be
    able to detect that a deployment has been PENDING for too long.
    """

    @pytest.mark.asyncio
    async def test_timeout_detected_after_restart(self, mock_nmp_sdk, mock_k8s_config, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=3)

        backend = K8sNimOperatorServiceBackend(nmp_sdk=mock_nmp_sdk, config={}, huggingface_model_puller="img:tag")
        backend._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=7200, max_restart_count=5)
        backend._k8s_namespace = "default"
        backend._dynamic_client = MagicMock()
        backend._k8s_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        with patch.object(
            backend._status_projector,
            "pod_status_from_deployment",
            return_value=DeploymentStatusUpdate(status="PENDING", status_message="Waiting", host_url=None),
        ):
            with _mock_pod_backend(backend):
                _sync_reconcilers(backend)
                result = await backend.get_model_deployment_status(
                    ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
                )
                assert result.status == "ERROR"
                assert result.error_details["reason"] == "pending_timeout"

    @pytest.mark.asyncio
    async def test_no_false_positive_after_restart(self, mock_nmp_sdk, mock_k8s_config, sample_deployment):
        """Fresh controller, deployment only 10 min old -> should stay PENDING."""
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)

        backend = K8sNimOperatorServiceBackend(nmp_sdk=mock_nmp_sdk, config={}, huggingface_model_puller="img:tag")
        backend._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=7200, max_restart_count=5)
        backend._k8s_namespace = "default"
        backend._dynamic_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        with patch.object(
            backend._status_projector,
            "pod_status_from_deployment",
            return_value=DeploymentStatusUpdate(status="PENDING", status_message="Waiting", host_url=None),
        ):
            _sync_reconcilers(backend)
            result = await backend.get_model_deployment_status(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
            )
            assert result.status == "PENDING"
            # No elapsed/timeout in message (stable message to avoid new history entry every poll)


# ============================================================================
# Pod log fetching edge cases
# ============================================================================


class TestFetchPodLogs:
    """Tests for _fetch_pod_logs edge cases."""

    @pytest.fixture
    def backend(self, mock_nmp_sdk, mock_k8s_config):
        return _status_helper_reconciler(namespace="default")

    def test_returns_logs_normally(self, backend):
        with _mock_pod_backend(backend, pod_logs="log line 1\nlog line 2"):
            result = backend.fetch_pod_logs("pod-1")
            assert result == "log line 1\nlog line 2"

    def test_truncates_long_logs(self, backend):
        long_logs = "x" * 3000
        with _mock_pod_backend(backend, pod_logs=long_logs):
            result = backend.fetch_pod_logs("pod-1")
            assert len(result) == 2048

    def test_returns_empty_on_exception(self, backend):
        mock_core_v1 = MagicMock()
        mock_core_v1.read_namespaced_pod_log.side_effect = Exception("API error")
        with patch(f"{_RECON_STATUS_MODULE}.k8s_client.CoreV1Api", return_value=mock_core_v1):
            result = backend.fetch_pod_logs("pod-1")
            assert result == ""


# ============================================================================
# Augmented PENDING message tests
# ============================================================================


class TestAugmentedPendingMessages:
    """Verify that PENDING messages include elapsed/remaining timing and restart info."""

    @pytest.fixture
    def backend(self, mock_nmp_sdk, mock_k8s_config):
        b = K8sNimOperatorServiceBackend(nmp_sdk=mock_nmp_sdk, config={}, huggingface_model_puller="img:tag")
        b._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=7200, max_restart_count=5)
        b._k8s_namespace = "default"
        b._k8s_client = MagicMock()
        b._dynamic_client = MagicMock()
        return b

    @pytest.mark.asyncio
    async def test_timing_info_appended_to_pending(self, backend, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)

        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        with patch.object(
            backend._status_projector,
            "pod_status_from_deployment",
            return_value=DeploymentStatusUpdate(status="PENDING", status_message="Waiting", host_url=None),
        ):
            _sync_reconcilers(backend)
            result = await backend.get_model_deployment_status(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
            )
            assert result.status == "PENDING"
            # No elapsed/timeout appended (stable message to avoid new history entry every poll)
            assert result.status_message == "Waiting"

    @pytest.mark.asyncio
    async def test_restart_info_in_pod_status(self, backend, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        pod = _make_pod(restart_count=3, phase="Running")

        with _mock_pod_backend(backend, pod=pod):
            _sync_reconcilers(backend)
            result = await backend.get_model_deployment_status(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
            )
            assert result.status == "PENDING"
            assert "restarts: 3" in result.status_message

    @pytest.mark.asyncio
    async def test_no_restart_info_when_zero(self, backend, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        pod = _make_pod(restart_count=0, phase="Running")

        with _mock_pod_backend(backend, pod=pod):
            _sync_reconcilers(backend)
            result = await backend.get_model_deployment_status(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
            )
            assert result.status == "PENDING"
            assert "restarts" not in result.status_message


# ============================================================================
# _find_pod_name edge cases
# ============================================================================


class TestFindPodName:
    """Tests for _find_pod_name best-effort lookup."""

    @pytest.fixture
    def backend(self, mock_nmp_sdk, mock_k8s_config):
        return _status_helper_reconciler(namespace="default")

    def test_returns_pod_name(self, backend):
        pod = _make_pod(name="found-pod-xyz")
        with _mock_pod_backend(backend, pod=pod) as (mock_apps_v1, _):
            result = backend.find_pod_name("resource-1")
            assert result == "found-pod-xyz"

    def test_returns_none_when_no_pods(self, backend):
        mock_apps_v1 = MagicMock()
        mock_core_v1 = MagicMock()
        mock_deployment = MagicMock()
        mock_deployment.spec.selector.match_labels = {"app": "test"}
        mock_apps_v1.read_namespaced_deployment.return_value = mock_deployment
        pods_list = MagicMock()
        pods_list.items = []
        mock_core_v1.list_namespaced_pod.return_value = pods_list

        with (
            patch(f"{_RECON_STATUS_MODULE}.k8s_client.AppsV1Api", return_value=mock_apps_v1),
            patch(f"{_RECON_STATUS_MODULE}.k8s_client.CoreV1Api", return_value=mock_core_v1),
        ):
            result = backend.find_pod_name("resource-1")
            assert result is None

    def test_returns_none_on_api_exception(self, backend):
        mock_apps_v1 = MagicMock()
        mock_apps_v1.read_namespaced_deployment.side_effect = k8s_client.exceptions.ApiException(status=404)

        with patch(f"{_RECON_STATUS_MODULE}.k8s_client.AppsV1Api", return_value=mock_apps_v1):
            result = backend.find_pod_name("resource-1")
            assert result is None


# ============================================================================
# Integration: crash loop takes precedence over pending timeout
# ============================================================================


class TestCrashLoopPrecedence:
    """Crash loop ERROR from pod status should be returned directly, not overridden by timeout."""

    @pytest.mark.asyncio
    async def test_crash_loop_overrides_timeout(self, mock_nmp_sdk, mock_k8s_config, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=5)

        backend = K8sNimOperatorServiceBackend(nmp_sdk=mock_nmp_sdk, config={}, huggingface_model_puller="img:tag")
        backend._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=60, max_restart_count=3)
        backend._k8s_namespace = "default"
        backend._dynamic_client = MagicMock()
        backend._k8s_client = MagicMock()
        backend._dynamic_client.resources.get.return_value = _make_nimservice_mock("NotReady")

        pod = _make_pod(restart_count=3, waiting_reason="CrashLoopBackOff")

        with _mock_pod_backend(backend, pod=pod, pod_logs="crash"):
            _sync_reconcilers(backend)
            result = await backend.get_model_deployment_status(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
            )
            assert result.status == "ERROR"
            assert result.error_details["reason"] == "crash_loop"


# ============================================================================
# NIMService failed state
# ============================================================================


class TestNIMServiceFailedState:
    """Verify that a Failed NIMService goes to ERROR without timeout interference."""

    @pytest.mark.asyncio
    async def test_failed_nimservice_returns_error(self, mock_nmp_sdk, mock_k8s_config, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=5)

        backend = K8sNimOperatorServiceBackend(nmp_sdk=mock_nmp_sdk, config={}, huggingface_model_puller="img:tag")
        backend._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=60)
        backend._k8s_namespace = "default"
        backend._dynamic_client = MagicMock()

        mock_resource = _make_nimservice_mock("Failed", [{"type": "Failed", "message": "out of GPU memory"}])
        backend._dynamic_client.resources.get.return_value = mock_resource

        _sync_reconcilers(backend)
        result = await backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )
        assert result.status == "ERROR"
        assert "NIMService failed" in result.status_message


# ============================================================================
# LOST state
# ============================================================================


class TestLostState:
    """Verify that a LOST NIMService is not confused with PENDING timeout."""

    @pytest.mark.asyncio
    async def test_lost_nimservice_not_treated_as_pending(self, mock_nmp_sdk, mock_k8s_config, sample_deployment):
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=5)

        backend = K8sNimOperatorServiceBackend(nmp_sdk=mock_nmp_sdk, config={}, huggingface_model_puller="img:tag")
        backend._backend_config = K8sNimOperatorConfig(pending_timeout_seconds=60)
        backend._k8s_namespace = "default"
        backend._dynamic_client = MagicMock()

        mock_resource = MagicMock()
        mock_resource.get.side_effect = k8s_dynamic_exceptions.NotFoundError(MagicMock())
        backend._dynamic_client.resources.get.return_value = mock_resource

        _sync_reconcilers(backend)
        result = await backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=_nim_config())
        )
        assert result.status == "LOST"


# =============================================================================
# Orphan reconciliation: list_managed_deployment_names, delete_model_deployment (by workspace/name)
# =============================================================================


@pytest.mark.asyncio
async def test_list_managed_deployment_names_returns_workspace_name_from_labels(mock_nmp_sdk, mock_k8s_config):
    """list_managed_deployment_names returns sorted workspace/name from NIMService metadata labels."""
    with patch(f"{_K8S_BACKEND_MODULE}.K8sNimOperatorServiceBackend._get_current_namespace", return_value="default"):
        backend = K8sNimOperatorServiceBackend(mock_nmp_sdk, {}, "pull-image")
    backend._k8s_namespace = "default"
    backend._dynamic_client = MagicMock()

    item1 = MagicMock()
    item1.metadata.labels = {
        "nmp.nvidia.com/deployment-workspace": "ws-a",
        "nmp.nvidia.com/deployment-name": "dep1",
    }
    item2 = MagicMock()
    item2.metadata.labels = {
        "nmp.nvidia.com/deployment-workspace": "ws-b",
        "nmp.nvidia.com/deployment-name": "dep2",
    }
    list_result = MagicMock()
    list_result.items = [item1, item2]
    mock_nimservice_api = MagicMock()
    mock_nimservice_api.get.return_value = list_result
    backend._dynamic_client.resources.get.return_value = mock_nimservice_api

    _sync_reconcilers(backend)
    names = await backend.list_managed_deployment_names()

    assert names == ["ws-a/dep1", "ws-b/dep2"]


@pytest.mark.asyncio
async def test_list_managed_deployment_names_empty_when_no_resources(mock_nmp_sdk, mock_k8s_config):
    """list_managed_deployment_names returns empty list when no NIMServices match."""
    with patch(f"{_K8S_BACKEND_MODULE}.K8sNimOperatorServiceBackend._get_current_namespace", return_value="default"):
        backend = K8sNimOperatorServiceBackend(mock_nmp_sdk, {}, "pull-image")
    backend._k8s_namespace = "default"
    backend._dynamic_client = MagicMock()
    list_result = MagicMock()
    list_result.items = []
    mock_nimservice_api = MagicMock()
    mock_nimservice_api.get.return_value = list_result
    backend._dynamic_client.resources.get.return_value = mock_nimservice_api

    _sync_reconcilers(backend)
    names = await backend.list_managed_deployment_names()

    assert names == []


@pytest.mark.asyncio
async def test_delete_model_deployment_by_id_calls_delete_resources(mock_nmp_sdk, mock_k8s_config):
    """delete_model_deployment(workspace, name) calls _delete_resources_by_model_deployment_id."""
    with patch(f"{_K8S_BACKEND_MODULE}.K8sNimOperatorServiceBackend._get_current_namespace", return_value="default"):
        backend = K8sNimOperatorServiceBackend(mock_nmp_sdk, {}, "pull-image")
    backend._k8s_namespace = "default"
    with patch.object(backend, "_delete_resources_by_model_deployment_id", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = DeploymentStatusUpdate(status="DELETED", status_message="")
        result = await backend.delete_model_deployment("my-ws", "my-name")
    mock_delete.assert_called_once_with("my-ws", "my-name")
    assert result.status == "DELETED"


# ===========================================================================
# vLLM path (native Kubernetes objects, no operator)
# ===========================================================================


def _vllm_config(*, gpu: int = 1, lora_enabled: bool = False):
    """A minimal vLLM ModelDeploymentConfig-like object for dispatch/compile."""
    return SimpleNamespace(
        engine="vllm",
        model_spec=SimpleNamespace(
            model_type=None,
            model_namespace="default",
            model_name="qwen",
            model_revision=None,
            chat_template=None,
            tool_call_config=None,
            lora_enabled=lora_enabled,
        ),
        executor_config=SimpleNamespace(
            gpu=gpu,
            disk_size="50Gi",
            image_name=None,
            image_tag=None,
            health_check_path=None,
            additional_envs=None,
            additional_args=[],
            k8s_nim_operator_config=None,
            override_config=None,
        ),
    )


def _vllm_backend(k8s_backend):
    """Wire a k8s_backend with mocked typed clients for the vLLM path."""
    k8s_backend._k8s_namespace = "nemo"
    k8s_backend._backend_config = K8sNimOperatorConfig()
    k8s_backend._k8s_client = MagicMock()
    k8s_backend._core_v1 = MagicMock()
    k8s_backend._apps_v1 = MagicMock()
    k8s_backend._batch_v1 = MagicMock()
    return k8s_backend


def _api_exception(status: int):
    return k8s_client.exceptions.ApiException(status=status)


@pytest.mark.asyncio
async def test_vllm_create_emits_pvc_and_job_only(k8s_backend, sample_deployment):
    """vLLM create (phase P0) emits the PVC + puller Job, not the Deployment/Service."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config(gpu=2)

    with patch.object(backend, "_resolve_model_source", return_value=("default", "qwen", None)):
        _sync_reconcilers(backend)
        result = await backend.create_model_deployment(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=config, model_entity=None)
        )

    assert result.status == "PENDING"
    backend._core_v1.create_namespaced_persistent_volume_claim.assert_called_once()
    backend._batch_v1.create_namespaced_job.assert_called_once()
    # Deployment + Service are NOT created at P0.
    backend._apps_v1.create_namespaced_deployment.assert_not_called()
    backend._core_v1.create_namespaced_service.assert_not_called()

    # The puller Job requests the same GPU as the server (topology pin).
    job = backend._batch_v1.create_namespaced_job.call_args.kwargs["body"]
    assert job.spec.template.spec.containers[0].resources.requests["nvidia.com/gpu"] == "2"


def _generic_config(*, gpu: int = 0, image="nvcr.io/nim/nvidia/nemoguard-jailbreak-detect", tag="1.10.1"):
    """A minimal generic ModelDeploymentConfig-like object (no model weights)."""
    return SimpleNamespace(
        engine="generic",
        model_spec=SimpleNamespace(
            model_type=None,
            model_namespace=None,
            model_name=None,
            model_revision=None,
            chat_template=None,
            tool_call_config=None,
            lora_enabled=False,
        ),
        executor_config=SimpleNamespace(
            gpu=gpu,
            disk_size="50Gi",
            image_name=image,
            image_tag=tag,
            health_check_path="/v1/health/ready",
            additional_envs={"FOO": "bar"},
            additional_args=["--port", "8000"],
            k8s_nim_operator_config=None,
            override_config=None,
        ),
    )


@pytest.mark.asyncio
async def test_generic_create_emits_deployment_and_service_no_pvc(k8s_backend, sample_deployment):
    """Generic create emits the Deployment + Service immediately, with no PVC/puller Job."""
    backend = _vllm_backend(k8s_backend)
    config = _generic_config()

    created_dep = MagicMock()
    created_dep.metadata.name = backend._get_resource_name(sample_deployment)
    created_dep.metadata.uid = "dep-uid"
    backend._apps_v1.create_namespaced_deployment.return_value = created_dep

    _sync_reconcilers(backend)
    result = await backend.create_model_deployment(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config, model_entity=None)
    )

    assert result.status == "PENDING"
    backend._apps_v1.create_namespaced_deployment.assert_called_once()
    backend._core_v1.create_namespaced_service.assert_called_once()
    # No model weights for generic: no PVC, no puller Job.
    backend._core_v1.create_namespaced_persistent_volume_claim.assert_not_called()
    backend._batch_v1.create_namespaced_job.assert_not_called()

    # The container runs the user's image + raw args + env verbatim, with no
    # model-store volume mounted.
    dep_obj = backend._apps_v1.create_namespaced_deployment.call_args.kwargs["body"]
    container = dep_obj.spec.template.spec.containers[0]
    assert container.image == "nvcr.io/nim/nvidia/nemoguard-jailbreak-detect:1.10.1"
    assert container.args == ["--port", "8000"]
    assert {e.name: e.value for e in container.env} == {"FOO": "bar"}
    volume_names = {v.name for v in dep_obj.spec.template.spec.volumes}
    assert "model-store" not in volume_names
    mount_names = {m.name for m in container.volume_mounts}
    assert "model-store" not in mount_names
    # Readiness/startup probes use the explicit health_check_path.
    assert container.readiness_probe.http_get.path == "/v1/health/ready"


@pytest.mark.asyncio
async def test_generic_status_ready_when_deployment_ready(k8s_backend, sample_deployment):
    """Generic status projects the serving Deployment's readiness directly (no Job/PVC)."""
    backend = _vllm_backend(k8s_backend)
    config = _generic_config()

    dep = MagicMock()
    dep.status.ready_replicas = 1
    backend._apps_v1.read_namespaced_deployment.return_value = dep

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )

    assert result.status == "READY"
    # Generic status never consults the puller Job.
    backend._batch_v1.read_namespaced_job.assert_not_called()


@pytest.mark.asyncio
async def test_generic_status_lost_when_deployment_missing(k8s_backend, sample_deployment):
    """Generic status reports LOST when the serving Deployment was deleted externally."""
    backend = _vllm_backend(k8s_backend)
    config = _generic_config()
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )
    assert result.status == "LOST"


def _generic_weighted_config(*, gpu: int = 1):
    """A generic config that also references a model (fileset-backed weights)."""
    config = _generic_config(gpu=gpu)
    config.model_spec.model_namespace = "default"
    config.model_spec.model_name = "qwen"
    return config


def _fileset_model_entity():
    """A model entity with a fileset -> resolves to FILES_SERVICE weights."""
    return SimpleNamespace(
        workspace="default", name="qwen", spec=None, trust_remote_code=False, fileset="hf://default/qwen"
    )


@pytest.mark.asyncio
async def test_generic_with_fileset_runs_staged_puller(k8s_backend, sample_deployment):
    """A generic deployment whose config resolves to a fileset pulls weights (staged)."""
    backend = _vllm_backend(k8s_backend)
    config = _generic_weighted_config(gpu=1)

    with patch.object(backend, "_resolve_model_source", return_value=("default", "qwen", None)):
        _sync_reconcilers(backend)
        result = await backend.create_model_deployment(
            ModelContext(
                model_deployment=sample_deployment,
                model_deployment_config=config,
                model_entity=_fileset_model_entity(),
            )
        )

    assert result.status == "PENDING"
    # Weighted generic => staged rollout: PVC + puller Job, no Deployment yet.
    backend._core_v1.create_namespaced_persistent_volume_claim.assert_called_once()
    backend._batch_v1.create_namespaced_job.assert_called_once()
    backend._apps_v1.create_namespaced_deployment.assert_not_called()


@pytest.mark.asyncio
async def test_generic_with_fileset_p3_mounts_model_store(k8s_backend, sample_deployment):
    """At P3 the weighted generic serving Deployment mounts the model-store PVC + uses raw args."""
    backend = _vllm_backend(k8s_backend)
    config = _generic_weighted_config(gpu=1)

    job = MagicMock()
    job.status.failed = None
    job.status.succeeded = 1
    backend._batch_v1.read_namespaced_job.return_value = job
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)
    backend._core_v1.list_namespaced_pod.return_value = MagicMock(items=[])
    created_dep = MagicMock()
    created_dep.metadata.name = backend._get_resource_name(sample_deployment)
    created_dep.metadata.uid = "dep-uid"
    backend._apps_v1.create_namespaced_deployment.return_value = created_dep

    with patch.object(backend, "_resolve_model_source", return_value=("default", "qwen", None)):
        _sync_reconcilers(backend)
        result = await backend.get_model_deployment_status(
            ModelContext(
                model_deployment=sample_deployment,
                model_deployment_config=config,
                model_entity=_fileset_model_entity(),
            )
        )

    assert result.status == "PENDING"
    backend._apps_v1.create_namespaced_deployment.assert_called_once()
    dep_obj = backend._apps_v1.create_namespaced_deployment.call_args.kwargs["body"]
    container = dep_obj.spec.template.spec.containers[0]
    # Weighted: model-store PVC is mounted so the pulled weights are available.
    volume_names = {v.name for v in dep_obj.spec.template.spec.volumes}
    assert "model-store" in volume_names
    # Still a generic container: runs the user's raw args (no vLLM serve synthesis).
    assert container.args == ["--port", "8000"]


@pytest.mark.asyncio
async def test_generic_update_patches_deployment(k8s_backend, sample_deployment):
    """Updating a (weightless) generic deployment patches the serving objects in place."""
    backend = _vllm_backend(k8s_backend)
    config = _generic_config()
    # Serving Deployment already exists -> patch, don't recreate.
    backend._apps_v1.read_namespaced_deployment.return_value = MagicMock()

    _sync_reconcilers(backend)
    result = await backend.update_model_deployment(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config, model_entity=None)
    )

    assert result.status == "PENDING"
    backend._apps_v1.patch_namespaced_deployment.assert_called_once()
    backend._core_v1.patch_namespaced_service.assert_called_once()
    # Patched in place, not recreated.
    backend._apps_v1.create_namespaced_deployment.assert_not_called()


@pytest.mark.asyncio
async def test_vllm_status_job_running_is_pending(k8s_backend, sample_deployment):
    """While the puller Job is running, status is PENDING."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config()
    job = MagicMock()
    job.status.failed = None
    job.status.succeeded = None
    backend._batch_v1.read_namespaced_job.return_value = job
    # No serving Deployment yet (still in pull phase).
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )
    assert result.status == "PENDING"
    assert "weights" in result.status_message.lower()
    backend._apps_v1.create_namespaced_deployment.assert_not_called()


@pytest.mark.asyncio
async def test_vllm_status_job_failed_is_error(k8s_backend, sample_deployment):
    """A failed puller Job surfaces as ERROR."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config()
    job = MagicMock()
    job.status.failed = 5
    job.status.succeeded = None
    backend._batch_v1.read_namespaced_job.return_value = job
    backend._core_v1.list_namespaced_pod.return_value = MagicMock(items=[])
    # No serving Deployment yet (failed during pull phase).
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )
    assert result.status == "ERROR"
    assert result.error_details["reason"] == "weight_pull_failed"


@pytest.mark.asyncio
async def test_vllm_status_job_complete_creates_deployment(k8s_backend, sample_deployment):
    """When the Job completes (phase P3), the Deployment + Service are created."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config(gpu=1)

    job = MagicMock()
    job.status.failed = None
    job.status.succeeded = 1
    backend._batch_v1.read_namespaced_job.return_value = job
    # Deployment does not exist yet -> triggers P3 creation.
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)
    # After the puller Job is deleted, no puller pod remains (volume released).
    backend._core_v1.list_namespaced_pod.return_value = MagicMock(items=[])
    created_dep = MagicMock()
    created_dep.metadata.name = backend._get_resource_name(sample_deployment)
    created_dep.metadata.uid = "dep-uid"
    backend._apps_v1.create_namespaced_deployment.return_value = created_dep

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )

    assert result.status == "PENDING"
    # Puller Job deleted (release RWO volume) before the Deployment is created.
    backend._batch_v1.delete_namespaced_job.assert_called_once()
    backend._apps_v1.create_namespaced_deployment.assert_called_once()
    backend._core_v1.create_namespaced_service.assert_called_once()
    # ownerRef patched onto the PVC so it cascades with the Deployment (Job is gone).
    backend._core_v1.patch_namespaced_persistent_volume_claim.assert_called_once()
    backend._batch_v1.patch_namespaced_job.assert_not_called()


@pytest.mark.asyncio
async def test_vllm_status_p3_waits_for_puller_pod_to_release_volume(k8s_backend, sample_deployment):
    """At P3, if the puller pod is still present, defer Deployment creation (RWO release)."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config(gpu=1)

    job = MagicMock()
    job.status.failed = None
    job.status.succeeded = 1
    backend._batch_v1.read_namespaced_job.return_value = job
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)
    # Puller pod still terminating -> volume not yet released.
    backend._core_v1.list_namespaced_pod.return_value = MagicMock(items=[MagicMock()])

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )

    assert result.status == "PENDING"
    backend._batch_v1.delete_namespaced_job.assert_called_once()
    # Deployment is NOT created until the puller pod is gone.
    backend._apps_v1.create_namespaced_deployment.assert_not_called()


@pytest.mark.asyncio
async def test_vllm_status_job_complete_with_lora_wires_sidecar(k8s_backend, sample_deployment):
    """At P3 with LoRA enabled, the Deployment gets the cache-init + adapter sidecar."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config(gpu=1, lora_enabled=True)

    job = MagicMock()
    job.status.failed = None
    job.status.succeeded = 1
    backend._batch_v1.read_namespaced_job.return_value = job
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)
    backend._core_v1.list_namespaced_pod.return_value = MagicMock(items=[])
    created_dep = MagicMock()
    created_dep.metadata.name = backend._get_resource_name(sample_deployment)
    created_dep.metadata.uid = "dep-uid"
    backend._apps_v1.create_namespaced_deployment.return_value = created_dep

    platform_cfg = MagicMock()
    platform_cfg.image_pull_secrets = []
    platform_cfg.image_registry = "my-registry"
    platform_cfg.image_tag = "local"
    platform_cfg.to_shared_envvars.return_value = {"NMP_SHARED": "1"}
    with patch(f"{_RECON_K8S_MODULE}.get_platform_config", return_value=platform_cfg):
        _sync_reconcilers(backend)
        result = await backend.get_model_deployment_status(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
        )

    assert result.status == "PENDING"
    dep_obj = backend._apps_v1.create_namespaced_deployment.call_args.kwargs["body"]
    pod = dep_obj.spec.template.spec
    assert pod.init_containers[0].name == "lora-cache-init"
    sidecar = next(ctr for ctr in pod.containers if ctr.name == "lora-sidecar")
    env = {e.name: e.value for e in sidecar.env}
    assert env["NIM_PEFT_SOURCE"] == "/scratch/loras"
    assert env["VLLM_LORA_BASE_MODEL_OVERRIDE"] == "/model-store"
    assert env["NMP_SHARED"] == "1"


@pytest.mark.asyncio
async def test_vllm_status_job_absent_pvc_present_resumes_p3_not_lost(k8s_backend, sample_deployment):
    """Job deleted (RWO release) + PVC present + no Deployment -> resume P3, not LOST."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config(gpu=1)

    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)
    backend._batch_v1.read_namespaced_job.side_effect = _api_exception(404)  # Job already deleted
    # PVC still present -> we're mid-P3, not orphaned.
    backend._core_v1.read_namespaced_persistent_volume_claim.return_value = MagicMock()
    backend._core_v1.list_namespaced_pod.return_value = MagicMock(items=[])
    created_dep = MagicMock()
    created_dep.metadata.name = backend._get_resource_name(sample_deployment)
    created_dep.metadata.uid = "dep-uid"
    backend._apps_v1.create_namespaced_deployment.return_value = created_dep

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )

    assert result.status == "PENDING"
    assert result.status != "LOST"
    backend._apps_v1.create_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_vllm_status_job_and_pvc_absent_is_lost(k8s_backend, sample_deployment):
    """Both Job and PVC gone + no Deployment -> genuine drift -> LOST."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config(gpu=1)

    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)
    backend._batch_v1.read_namespaced_job.side_effect = _api_exception(404)
    backend._core_v1.read_namespaced_persistent_volume_claim.side_effect = _api_exception(404)

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )
    assert result.status == "LOST"


@pytest.mark.asyncio
async def test_vllm_status_deployment_ready_is_ready(k8s_backend, sample_deployment):
    """A ready serving Deployment maps to READY + host_url."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config()

    job = MagicMock()
    job.status.failed = None
    job.status.succeeded = 1
    backend._batch_v1.read_namespaced_job.return_value = job

    dep = MagicMock()
    dep.status.ready_replicas = 1
    backend._apps_v1.read_namespaced_deployment.return_value = dep

    _sync_reconcilers(backend)
    result = await backend.get_model_deployment_status(
        ModelContext(model_deployment=sample_deployment, model_deployment_config=config)
    )
    assert result.status == "READY"
    assert result.host_url is not None


@pytest.mark.asyncio
async def test_vllm_update_unchanged_source_does_not_repull(k8s_backend, sample_deployment):
    """Unchanged model source: no resource deletion; serving objects patched in place."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config()

    existing_job = MagicMock()
    existing_job.metadata.labels = {"nmp.nvidia.com/engine": "vllm"}
    existing_job.metadata.annotations = {"nmp.nvidia.com/model-source": "default/qwen"}
    backend._batch_v1.read_namespaced_job.return_value = existing_job
    # Serving Deployment already exists -> update patches it in place.
    backend._apps_v1.read_namespaced_deployment.return_value = MagicMock()

    with patch.object(backend, "_resolve_model_source", return_value=("default", "qwen", None)):
        with patch.object(backend._k8s_reconciler, "_delete_serving_resources") as mock_delete:
            _sync_reconcilers(backend)
            result = await backend.update_model_deployment(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=config, model_entity=None)
            )

    mock_delete.assert_not_called()
    backend._batch_v1.create_namespaced_job.assert_not_called()
    # Patched, not recreated.
    backend._apps_v1.patch_namespaced_deployment.assert_called_once()
    assert result.status == "PENDING"


@pytest.mark.asyncio
async def test_vllm_update_changed_source_repulls(k8s_backend, sample_deployment):
    """Changed model source: delete resources and re-run the phased create."""
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config()

    existing_job = MagicMock()
    existing_job.metadata.labels = {"nmp.nvidia.com/engine": "vllm"}
    existing_job.metadata.annotations = {"nmp.nvidia.com/model-source": "default/old-model"}
    backend._batch_v1.read_namespaced_job.return_value = existing_job

    with patch.object(backend, "_resolve_model_source", return_value=("default", "qwen", "v2")):
        with patch.object(backend._k8s_reconciler, "_delete_serving_resources") as mock_delete:
            _sync_reconcilers(backend)
            result = await backend.update_model_deployment(
                ModelContext(model_deployment=sample_deployment, model_deployment_config=config, model_entity=None)
            )

    mock_delete.assert_called_once()
    # Re-pull: a new PVC + Job are created.
    backend._core_v1.create_namespaced_persistent_volume_claim.assert_called_once()
    backend._batch_v1.create_namespaced_job.assert_called_once()
    assert result.status == "PENDING"


@pytest.mark.asyncio
async def test_vllm_update_during_pull_is_noop(k8s_backend, sample_deployment):
    """Unchanged source, serving Deployment not yet created but puller Job present.

    Mid-pull updates must be a no-op (the status path emits the serving objects at
    P3); we must not re-run create() or patch a non-existent Deployment.
    """
    backend = _vllm_backend(k8s_backend)
    config = _vllm_config()

    existing_job = MagicMock()
    existing_job.metadata.labels = {"nmp.nvidia.com/engine": "vllm"}
    existing_job.metadata.annotations = {"nmp.nvidia.com/model-source": "default/qwen"}
    backend._batch_v1.read_namespaced_job.return_value = existing_job
    # Serving Deployment does not exist yet (still pulling).
    backend._apps_v1.read_namespaced_deployment.side_effect = _api_exception(404)

    with patch.object(backend, "_resolve_model_source", return_value=("default", "qwen", None)):
        _sync_reconcilers(backend)
        result = await backend.update_model_deployment(
            ModelContext(model_deployment=sample_deployment, model_deployment_config=config, model_entity=None)
        )

    assert result.status == "PENDING"
    # No-op: no re-create of PVC/Job, no Deployment patch.
    backend._core_v1.create_namespaced_persistent_volume_claim.assert_not_called()
    backend._batch_v1.create_namespaced_job.assert_not_called()
    backend._apps_v1.patch_namespaced_deployment.assert_not_called()


@pytest.mark.asyncio
async def test_vllm_list_managed_unions_deployments(k8s_backend):
    """list_managed_deployment_names unions NIMServices and raw vLLM Deployments."""
    backend = _vllm_backend(k8s_backend)
    backend._dynamic_client = MagicMock()
    backend._dynamic_client.resources.get.return_value.get.return_value = MagicMock(items=[])

    dep = MagicMock()
    dep.metadata.labels = {
        "nmp.nvidia.com/deployment-workspace": "default",
        "nmp.nvidia.com/deployment-name": "qwen",
    }
    backend._apps_v1.list_namespaced_deployment.return_value = MagicMock(items=[dep])

    _sync_reconcilers(backend)
    names = await backend.list_managed_deployment_names()
    assert "default/qwen" in names
