# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for backend config field usage in NIMService compilation."""

from unittest.mock import MagicMock, patch

import pytest
from nmp.common.config import ImagePullSecret, PlatformConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler import compile_nimservice


@pytest.fixture
def sample_deployment():
    """Create a sample ModelDeployment for testing."""
    deployment = MagicMock()
    deployment.workspace = "test-ns"
    deployment.name = "test-deployment"
    deployment.entity_version = "v1"
    return deployment


@pytest.fixture
def minimal_nim_config():
    """Create minimal NIM deployment config."""
    config = MagicMock()
    config.workspace = "test-ns"
    config.name = "test-config"
    config.entity_version = "v1"
    config.engine = "nim"
    config.model_spec = MagicMock()
    config.model_spec.lora_enabled = False
    config.model_spec.model_name = None
    config.model_spec.model_namespace = None
    config.model_spec.model_revision = None
    config.model_spec.tool_call_config = None
    config.executor_config = MagicMock()
    config.executor_config.image_name = "nvcr.io/nim/test"
    config.executor_config.image_tag = "1.0.0"
    config.executor_config.gpu = 1
    config.executor_config.disk_size = None  # Will use backend default
    config.executor_config.additional_envs = {}
    config.executor_config.k8s_nim_operator_config = None
    config.executor_config.override_config = {}
    return config


def test_default_storage_class_is_used(sample_deployment, minimal_nim_config):
    """Test that default_storage_class from backend config is used in PVC."""
    backend_config = K8sNimOperatorConfig(default_storage_class="fast-ssd")

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.storage.pvc.storageClass == "fast-ssd"


def test_default_pvc_size_is_used_when_disk_size_not_specified(sample_deployment, minimal_nim_config):
    """Test that default_pvc_size is used when deployment config doesn't specify disk_size."""
    backend_config = K8sNimOperatorConfig(default_pvc_size="500Gi")
    minimal_nim_config.executor_config.disk_size = None

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.storage.pvc.size == "500Gi"


def test_deployment_disk_size_overrides_default_pvc_size(sample_deployment, minimal_nim_config):
    """Test that deployment config disk_size takes precedence over default_pvc_size."""
    backend_config = K8sNimOperatorConfig(default_pvc_size="500Gi")
    minimal_nim_config.executor_config.disk_size = "100Gi"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.storage.pvc.size == "100Gi"


def test_peft_source_only_used_when_lora_enabled(sample_deployment, minimal_nim_config):
    """Test that peft_source is only used when lora_enabled is true."""
    backend_config = K8sNimOperatorConfig(peft_source="http://custom-peft-source:8000")

    # Test with lora disabled
    minimal_nim_config.model_spec.lora_enabled = False
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )
    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert "NIM_PEFT_SOURCE" not in env_vars

    # Test with lora enabled
    minimal_nim_config.model_spec.lora_enabled = True
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )
    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert env_vars["NIM_PEFT_SOURCE"] == "/scratch/loras"


def test_peft_refresh_interval_only_used_when_lora_enabled(sample_deployment, minimal_nim_config):
    """Test that peft_refresh_interval is only used when lora_enabled is true."""
    backend_config = K8sNimOperatorConfig(peft_refresh_interval=60)

    # Test with lora disabled
    minimal_nim_config.model_spec.lora_enabled = False
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )
    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert "NIM_PEFT_REFRESH_INTERVAL" not in env_vars

    # Test with lora enabled
    minimal_nim_config.model_spec.lora_enabled = True
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )
    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert env_vars["NIM_PEFT_REFRESH_INTERVAL"] == "60"


def test_image_pull_secrets_included_when_set(sample_deployment, minimal_nim_config):
    """Test that image_pull_secrets are included when set in platform config."""
    backend_config = K8sNimOperatorConfig()

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
        models_url="http://models-service:8000",
        image_pull_secrets=[
            ImagePullSecret(name="secret1"),
            ImagePullSecret(name="secret2"),
            ImagePullSecret(name="secret3"),
        ],
    )

    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_nim_config,
            k8s_namespace="default",
            resource_name="test-resource",
        )

    assert nimservice.spec.image.pullSecrets == ["secret1", "secret2", "secret3"]


def test_image_pull_secrets_not_included_when_none(sample_deployment, minimal_nim_config):
    """Test that image_pull_secrets are not included when not set in platform config."""
    backend_config = K8sNimOperatorConfig()

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
        models_url="http://models-service:8000",
        image_pull_secrets=[],
    )

    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_nim_config,
            k8s_namespace="default",
            resource_name="test-resource",
        )

    assert nimservice.spec.image.pullSecrets is None


def test_image_pull_secrets_from_platform_config(sample_deployment, minimal_nim_config):
    """Test that image_pull_secrets are correctly read from platform config."""
    backend_config = K8sNimOperatorConfig()

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
        models_url="http://models-service:8000",
        image_pull_secrets=[
            ImagePullSecret(name="secret1"),
            ImagePullSecret(name="secret2"),
            ImagePullSecret(name="secret3"),
        ],
    )

    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_nim_config,
            k8s_namespace="default",
            resource_name="test-resource",
        )

    assert nimservice.spec.image.pullSecrets == ["secret1", "secret2", "secret3"]


def test_default_user_id_included_when_set(sample_deployment, minimal_nim_config):
    """Test that default_user_id is included when set."""
    backend_config = K8sNimOperatorConfig(default_user_id=1000)

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.userID == 1000


def test_default_user_id_not_included_when_none(sample_deployment, minimal_nim_config):
    """Test that default_user_id is not included when not set."""
    backend_config = K8sNimOperatorConfig(default_user_id=None)

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.userID is None


def test_default_group_id_included_when_set(sample_deployment, minimal_nim_config):
    """Test that default_group_id is included when set."""
    backend_config = K8sNimOperatorConfig(default_group_id=1000)

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.groupID == 1000


def test_default_group_id_not_included_when_none(sample_deployment, minimal_nim_config):
    """Test that default_group_id is not included when not set."""
    backend_config = K8sNimOperatorConfig(default_group_id=None)

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.groupID is None


def test_both_user_and_group_id_can_be_set(sample_deployment, minimal_nim_config):
    """Test that both user_id and group_id can be set together."""
    backend_config = K8sNimOperatorConfig(default_user_id=1000, default_group_id=2000)

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.userID == 1000
    assert nimservice.spec.groupID == 2000


def test_auth_secret_is_always_included(sample_deployment, minimal_nim_config):
    """Test that authSecret is set from auth_secret when no NIMCache, and from files_auth_secret when NIMCache."""
    backend_config = K8sNimOperatorConfig(auth_secret="my-custom-ngc-secret")

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )
    assert nimservice.spec.authSecret == "my-custom-ngc-secret"

    backend_config_files = K8sNimOperatorConfig(files_auth_secret="my-custom-files-token")
    nimservice_with_cache = compile_nimservice(
        backend_config=backend_config_files,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
        nimcache_name="test-resource",
    )
    assert nimservice_with_cache.spec.authSecret == "my-custom-files-token"


def test_auth_secret_default_value(sample_deployment, minimal_nim_config):
    """Test that authSecret uses auth_secret default (ngc-api) when no NIMCache."""
    backend_config = K8sNimOperatorConfig()  # Use defaults

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.authSecret == "ngc-api"


def test_all_backend_config_fields_together(sample_deployment, minimal_nim_config):
    """Test that all backend config fields work together correctly."""
    backend_config = K8sNimOperatorConfig(
        default_storage_class="premium-ssd",
        default_pvc_size="1Ti",
        peft_source="http://custom-peft:8000",
        peft_refresh_interval=45,
        default_user_id=1001,
        default_group_id=2001,
        auth_secret="custom-ngc-api",
    )

    # Enable lora to test peft fields
    minimal_nim_config.model_spec.lora_enabled = True
    minimal_nim_config.executor_config.disk_size = None  # Use backend default

    platform_config = PlatformConfig(  # type: ignore[abstract]
        base_url="http://platform-service:8080",
        image_pull_secrets=[
            ImagePullSecret(name="secret1"),
            ImagePullSecret(name="secret2"),
        ],
    )

    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_nim_config,
            k8s_namespace="default",
            resource_name="test-resource",
        )

    # Verify storage
    assert nimservice.spec.storage.pvc.storageClass == "premium-ssd"
    assert nimservice.spec.storage.pvc.size == "1Ti"

    # Verify peft env vars
    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert env_vars["NIM_PEFT_SOURCE"] == "/scratch/loras"
    assert env_vars["NIM_PEFT_REFRESH_INTERVAL"] == "45"

    # Verify image pull secrets (from platform config)
    assert nimservice.spec.image.pullSecrets == ["secret1", "secret2"]

    # Verify security context
    assert nimservice.spec.userID == 1001
    assert nimservice.spec.groupID == 2001

    # Verify auth (NGC secret when no NIMCache)
    assert nimservice.spec.authSecret == "custom-ngc-api"

    assert nimservice.spec.sidecarContainers is not None
    assert len(nimservice.spec.sidecarContainers) == 1
    assert nimservice.spec.sidecarContainers[0].name == "test-resource-lora-sidecar"
    assert len(nimservice.spec.sidecarContainers[0].env) >= 1

    keys = set([e.name for e in nimservice.spec.sidecarContainers[0].env])
    assert "NMP_FILES_URL" in keys
    assert "NMP_MODELS_URL" in keys


def test_default_resources_applied(sample_deployment, minimal_nim_config):
    """Test that default_resources from backend config is applied to NIMService."""
    backend_config = K8sNimOperatorConfig(
        default_resources={
            "requests": {"cpu": "2", "memory": "8Gi"},
            "limits": {"memory": "16Gi"},
        }
    )

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    # Should have default resources merged with GPU limits (from gpu=1)
    assert nimservice.spec.resources.requests["cpu"].root == "2"
    assert nimservice.spec.resources.requests["memory"].root == "8Gi"
    assert nimservice.spec.resources.limits["memory"].root == "16Gi"
    # GPU should still be there (deployment gpu count wins over default_resources)
    assert "nvidia.com/gpu" in nimservice.spec.resources.limits
    assert nimservice.spec.resources.limits["nvidia.com/gpu"].root == "1"


def test_default_tolerations_applied(sample_deployment, minimal_nim_config):
    """Test that default_tolerations from backend config is applied to NIMService."""
    backend_config = K8sNimOperatorConfig(
        default_tolerations=[
            {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"},
        ]
    )

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.tolerations is not None
    assert len(nimservice.spec.tolerations) == 1
    assert nimservice.spec.tolerations[0].key == "nvidia.com/gpu"
    assert nimservice.spec.tolerations[0].operator == "Exists"
    assert nimservice.spec.tolerations[0].effect == "NoSchedule"


def test_default_node_selector_applied(sample_deployment, minimal_nim_config):
    """Test that default_node_selector from backend config is applied to NIMService."""
    backend_config = K8sNimOperatorConfig(default_node_selector={"node-type": "gpu-node", "zone": "us-west1-a"})

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.spec.nodeSelector is not None
    assert nimservice.spec.nodeSelector["node-type"] == "gpu-node"
    assert nimservice.spec.nodeSelector["zone"] == "us-west1-a"


def test_default_startup_probe_grace_period_seconds_applied(sample_deployment, minimal_nim_config):
    """Test that default_startup_probe_grace_period_seconds from backend config is applied."""
    backend_config = K8sNimOperatorConfig(default_startup_probe_grace_period_seconds=1200)

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    # 1200 seconds / 10 = 120 failureThreshold
    assert nimservice.spec.startupProbe.probe.failureThreshold == 120
    assert nimservice.spec.startupProbe.probe.periodSeconds == 10


def test_per_deployment_config_overrides_backend_defaults(sample_deployment, minimal_nim_config):
    """Test that per-deployment k8s_nim_operator_config overrides backend defaults."""
    backend_config = K8sNimOperatorConfig(
        default_resources={"requests": {"cpu": "2", "memory": "8Gi"}},
        default_node_selector={"zone": "us-west1-a"},
        default_startup_probe_grace_period_seconds=600,
    )

    # Per-deployment config overrides
    minimal_nim_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_nim_config.executor_config.k8s_nim_operator_config.startup_probe_grace_seconds = 1200
    minimal_nim_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "resources": {"requests": {"cpu": "4"}},  # Override CPU
        "node_selector": {"zone": "us-east1-b"},  # Override zone
        "startup_probe_grace_seconds": 1200,  # Override grace period
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    # Per-deployment overrides should win
    assert nimservice.spec.resources.requests["cpu"].root == "4"
    assert nimservice.spec.nodeSelector["zone"] == "us-east1-b"
    # 1200 seconds / 10 = 120
    assert nimservice.spec.startupProbe.probe.failureThreshold == 120


def test_backend_defaults_not_applied_when_none(sample_deployment, minimal_nim_config):
    """Test that backend defaults are not applied when set to None."""
    backend_config = K8sNimOperatorConfig(
        default_resources=None,
        default_tolerations=None,
        default_node_selector=None,
        default_startup_probe_grace_period_seconds=None,
    )

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    # Should use defaults from compiler, not backend config
    # Default startup probe is 600 seconds = 60 failureThreshold
    assert nimservice.spec.startupProbe.probe.failureThreshold == 60


def test_default_labels_applied_to_nimservice_metadata_and_spec(sample_deployment, minimal_nim_config):
    """Test that default_labels from backend config are applied to NIMService CR metadata and spec (pods)."""
    backend_config = K8sNimOperatorConfig(
        default_labels={"team": "ml-platform", "environment": "prod"},
    )

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    # CR metadata labels: defaults + controller labels (controller wins on conflict)
    meta_labels = nimservice.metadata["labels"]
    assert meta_labels["team"] == "ml-platform"
    assert meta_labels["environment"] == "prod"
    assert meta_labels["app.kubernetes.io/name"] == "test-resource"

    # Spec labels (pod): same merge
    spec_labels = nimservice.spec.labels
    assert spec_labels["team"] == "ml-platform"
    assert spec_labels["environment"] == "prod"
    assert spec_labels["nmp.nvidia.com/deployment-workspace"] == sample_deployment.workspace


def test_default_annotations_applied_to_nimservice_metadata_and_spec(sample_deployment, minimal_nim_config):
    """Test that default_annotations from backend config are applied to NIMService CR metadata and spec (pods)."""
    backend_config = K8sNimOperatorConfig(
        default_annotations={"prometheus.io/scrape": "true", "custom/key": "value"},
    )

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_nim_config,
        k8s_namespace="default",
        resource_name="test-resource",
    )

    assert nimservice.metadata["annotations"] == {"prometheus.io/scrape": "true", "custom/key": "value"}
    assert nimservice.spec.annotations == {"prometheus.io/scrape": "true", "custom/key": "value"}
