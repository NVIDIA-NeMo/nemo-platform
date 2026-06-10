# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for NIMService compiler."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml
from nmp.common.config import PlatformConfig
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler import (
    TOOL_CALL_PLUGIN_FINALIZE_SCRIPT_TEMPLATE,
    _apply_k8s_nim_operator_config,
    compile_nimcache,
    compile_nimservice,
)


@pytest.fixture
def backend_config():
    """Create a sample K8sNimOperatorConfig for testing."""
    return K8sNimOperatorConfig()


@pytest.fixture
def sample_deployment():
    """Create a sample ModelDeployment for testing."""
    deployment = MagicMock()
    deployment.workspace = "test-ns"
    deployment.name = "test-deployment"
    deployment.entity_version = "v1"
    return deployment


@pytest.fixture
def minimal_config():
    """Create a minimal ModelDeploymentConfig for testing."""
    config = MagicMock()
    config.workspace = "test-ns"
    config.name = "test-config"
    config.entity_version = "v1"

    # Minimal model_spec configuration
    config.engine = "nim"
    config.model_spec = MagicMock()
    config.model_spec.lora_enabled = False
    config.model_spec.model_name = None
    config.model_spec.model_namespace = None
    config.model_spec.model_revision = None
    config.model_spec.tool_call_config = None

    # Minimal executor_config configuration
    config.executor_config = MagicMock()
    config.executor_config.image_name = "nvcr.io/nim/meta/llama-3-8b-instruct"
    config.executor_config.image_tag = "1.0.0"
    config.executor_config.gpu = 1
    config.executor_config.disk_size = "50Gi"
    config.executor_config.additional_envs = {}
    config.executor_config.k8s_nim_operator_config = None
    config.executor_config.override_config = {}

    return config


@pytest.fixture
def full_config():
    """Create a full ModelDeploymentConfig with all options enabled."""
    config = MagicMock()
    config.workspace = "test-ns"
    config.name = "test-config"
    config.entity_version = "v1"

    # Full model_spec configuration
    config.engine = "nim"
    config.model_spec = MagicMock()
    config.model_spec.lora_enabled = True
    config.model_spec.model_name = "llama-3.2-3b-instruct"
    config.model_spec.model_namespace = "meta"
    config.model_spec.model_revision = None
    config.model_spec.tool_call_config = None

    # Full executor_config configuration
    config.executor_config = MagicMock()
    config.executor_config.image_name = "nvcr.io/nim/meta/llama-3.2-3b-instruct"
    config.executor_config.image_tag = "1.8.5"
    config.executor_config.gpu = 2
    config.executor_config.disk_size = "200Gi"
    config.executor_config.additional_envs = {
        "CUSTOM_VAR": "custom_value",
        "DEBUG": "true",
    }
    config.executor_config.k8s_nim_operator_config = None
    config.executor_config.override_config = {}

    return config


def test_compile_nimservice_basic(backend_config, sample_deployment, minimal_config):
    """Test basic NIMService compilation with minimal config."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify NIMService structure
    assert nimservice.apiVersion == "apps.nvidia.com/v1alpha1"
    assert nimservice.kind == "NIMService"
    assert nimservice.metadata is not None
    assert nimservice.spec is not None


def test_compile_nimservice_metadata(backend_config, sample_deployment, minimal_config):
    """Test that metadata is correctly set."""
    resource_name = "md-test-ns-test-deployment"
    k8s_namespace = "default"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace=k8s_namespace,
        resource_name=resource_name,
    )

    # Verify metadata
    assert nimservice.metadata["name"] == resource_name
    assert nimservice.metadata["namespace"] == k8s_namespace

    # Verify labels
    labels = nimservice.metadata["labels"]
    assert labels["app.kubernetes.io/name"] == resource_name
    assert labels[MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
    assert labels["nmp.nvidia.com/deployment-workspace"] == sample_deployment.workspace
    assert labels["nmp.nvidia.com/deployment-name"] == sample_deployment.name


def test_compile_nimservice_required_spec_fields(backend_config, sample_deployment, minimal_config):
    """Test that all required spec fields are present."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    spec = nimservice.spec

    # Required fields from the NIMService CRD
    assert spec.authSecret is not None
    assert spec.authSecret == "ngc-api"
    assert spec.image is not None
    assert spec.resources is not None
    assert spec.storage is not None
    assert spec.expose is not None
    assert spec.env is not None


def test_compile_nimservice_image_config(backend_config, sample_deployment, minimal_config):
    """Test that image configuration is correctly set."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    image = nimservice.spec.image
    assert image.repository == "nvcr.io/nim/meta/llama-3-8b-instruct"
    assert image.tag == "1.0.0"
    assert image.pullPolicy == "IfNotPresent"


def test_compile_nimservice_gpu_resources(backend_config, sample_deployment, minimal_config):
    """Test that GPU resources are correctly configured."""
    minimal_config.executor_config.gpu = 4

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    resources = nimservice.spec.resources
    assert resources.limits is not None
    assert "nvidia.com/gpu" in resources.limits
    assert resources.limits["nvidia.com/gpu"].root == "4"

    # Verify CPU requests
    assert resources.requests is not None
    assert "cpu" in resources.requests
    assert resources.requests["cpu"].root == "1000m"


def test_compile_nimservice_storage_pvc(backend_config, sample_deployment, minimal_config):
    """Test that PVC storage is correctly configured."""
    resource_name = "md-test-ns-test-deployment"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name=resource_name,
    )

    storage = nimservice.spec.storage
    assert storage.pvc is not None

    pvc = storage.pvc
    assert pvc.create is True
    assert pvc.name == resource_name
    assert pvc.size == "50Gi"
    assert pvc.storageClass is None  # unset = use cluster default
    assert pvc.volumeAccessMode == "ReadWriteOnce"


def test_compile_nimservice_storage_pvc_inherits_storage_class_from_backend_config(sample_deployment, minimal_config):
    """Test that PVC storageClass is inherited from backend config when set."""
    backend_config = K8sNimOperatorConfig(default_storage_class="nfs")
    resource_name = "md-test-ns-test-deployment"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name=resource_name,
    )

    storage = nimservice.spec.storage
    assert storage.pvc is not None
    assert storage.pvc.storageClass == "nfs"


def test_compile_nimservice_expose_service(backend_config, sample_deployment, minimal_config):
    """Test that service exposure is correctly configured."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    expose = nimservice.spec.expose
    assert expose.service is not None
    assert expose.service.type == "ClusterIP"
    assert expose.service.port == 8000


def test_compile_nimservice_default_env_vars(backend_config, sample_deployment, minimal_config):
    """Test that default environment variables are set."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    env_vars = {env.name: env.value for env in nimservice.spec.env}

    # Verify default env var
    assert "NIM_GUIDED_DECODING_BACKEND" in env_vars
    assert env_vars["NIM_GUIDED_DECODING_BACKEND"] == "outlines"


def test_compile_nimservice_model_env_vars(backend_config, sample_deployment, full_config):
    """Test that model-specific environment variables are set."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=full_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    env_vars = {env.name: env.value for env in nimservice.spec.env}

    # Verify model env vars
    expected_model_fqdn = "meta/llama-3.2-3b-instruct"
    assert "NIM_SERVED_MODEL_NAME" in env_vars
    assert env_vars["NIM_SERVED_MODEL_NAME"] == expected_model_fqdn
    assert "NIM_MODEL_NAME" in env_vars
    assert env_vars["NIM_MODEL_NAME"] == expected_model_fqdn


def test_compile_nimservice_lora_env_vars(backend_config, sample_deployment, full_config):
    """Test that LoRA support environment variables are set when enabled."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=full_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    env_vars = {env.name: env.value for env in nimservice.spec.env}

    # Verify LoRA env vars
    assert "NIM_PEFT_SOURCE" in env_vars
    assert "NIM_PEFT_REFRESH_INTERVAL" in env_vars
    # Default is now 30 seconds (matching DMS)
    assert env_vars["NIM_PEFT_REFRESH_INTERVAL"] == "30"


def test_compile_nimservice_sidecar_container_name_truncated_for_long_resource_name(
    backend_config, sample_deployment, full_config
):
    """Sidecar container name must be ≤63 chars (K8s DNS label). Long resource names are truncated with hash."""
    long_resource_name = "md-e2e-d2ad136f-sft-model-deployment-qwen-lora-base"
    assert len(long_resource_name) + len("-lora-sidecar") > 63

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=full_config,
        k8s_namespace="default",
        resource_name=long_resource_name,
    )

    assert nimservice.spec.sidecarContainers is not None
    assert len(nimservice.spec.sidecarContainers) == 1
    sidecar_name = nimservice.spec.sidecarContainers[0].name
    assert len(sidecar_name) <= 63, f"Sidecar name {sidecar_name!r} exceeds 63 chars"
    assert sidecar_name.endswith("-lora-sidecar")


def test_compile_nimservice_sidecar_command_includes_nemo_platform(backend_config, sample_deployment, full_config):
    """Sidecar command must be full argv for K8s (container.command overrides image ENTRYPOINT)."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=full_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    assert nimservice.spec.sidecarContainers is not None
    assert len(nimservice.spec.sidecarContainers) == 1
    sidecar = nimservice.spec.sidecarContainers[0]
    assert sidecar.command == [
        "nemo",
        "services",
        "run",
        "--sidecars",
        "adapters",
    ]


def test_compile_nimservice_sidecar_image_uses_platform_registry_and_tag(
    backend_config, sample_deployment, full_config
):
    """Sidecar image must use platform config registry and tag as separate fields (no split on ':')."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={
            "files": "http://nemo-files:8000",
            "models": "http://nemo-models:8000",
        },
        image_registry="localhost:5000",
        image_tag="sidecar-tag",
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=full_config,
            k8s_namespace="default",
            resource_name="md-test-ns-test-deployment",
        )

    assert nimservice.spec.sidecarContainers is not None
    assert len(nimservice.spec.sidecarContainers) == 1
    sidecar = nimservice.spec.sidecarContainers[0]
    assert sidecar.image.repository == "localhost:5000/nmp-api"
    assert sidecar.image.tag == "sidecar-tag"


def test_compile_nimservice_additional_env_vars(backend_config, sample_deployment, full_config):
    """Test that additional environment variables are added."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=full_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    env_vars = {env.name: env.value for env in nimservice.spec.env}

    # Verify additional env vars
    assert "CUSTOM_VAR" in env_vars
    assert env_vars["CUSTOM_VAR"] == "custom_value"
    assert "DEBUG" in env_vars
    assert env_vars["DEBUG"] == "true"


def test_compile_nimservice_additional_envs_override_defaults(backend_config, sample_deployment, minimal_config):
    """Test that additional env vars can override defaults."""
    minimal_config.executor_config.additional_envs = {
        "NIM_GUIDED_DECODING_BACKEND": "custom_backend",
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    env_vars = {env.name: env.value for env in nimservice.spec.env}

    # Verify override
    assert env_vars["NIM_GUIDED_DECODING_BACKEND"] == "custom_backend"


def test_compile_nimservice_replicas(backend_config, sample_deployment, minimal_config):
    """Test that replicas are set correctly."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Should default to 1 replica
    assert nimservice.spec.replicas == 1


def test_compile_nimservice_labels(backend_config, sample_deployment, minimal_config):
    """Test that spec labels are set correctly."""
    resource_name = "md-test-ns-test-deployment"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name=resource_name,
    )

    labels = nimservice.spec.labels
    assert labels["app.kubernetes.io/name"] == resource_name
    assert labels[MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
    assert labels["nmp.nvidia.com/deployment-workspace"] == sample_deployment.workspace
    assert labels["nmp.nvidia.com/deployment-name"] == sample_deployment.name


def test_compile_nimservice_override_config_env_vars(backend_config, sample_deployment, minimal_config):
    """Test that override_config can add environment variables."""
    minimal_config.executor_config.override_config = {
        "env": [
            {"name": "OVERRIDE_VAR", "value": "override_value"},
            {"name": "ANOTHER_VAR", "value": "another_value"},
        ]
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # The override should replace the entire env array
    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert "OVERRIDE_VAR" in env_vars
    assert env_vars["OVERRIDE_VAR"] == "override_value"


def test_compile_nimservice_override_config_tolerations(backend_config, sample_deployment, minimal_config):
    """Test that override_config can add Kubernetes tolerations."""
    minimal_config.executor_config.override_config = {
        "tolerations": [
            {
                "key": "nvidia.com/gpu",
                "operator": "Equal",
                "value": "true",
                "effect": "NoSchedule",
            },
            {
                "key": "special-node",
                "operator": "Exists",
                "effect": "NoExecute",
            },
        ]
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify tolerations were added
    assert hasattr(nimservice.spec, "tolerations")
    assert len(nimservice.spec.tolerations) == 2
    assert nimservice.spec.tolerations[0].key == "nvidia.com/gpu"
    assert nimservice.spec.tolerations[1].key == "special-node"


def test_compile_nimservice_override_config_node_selector(backend_config, sample_deployment, minimal_config):
    """Test that override_config can add node selectors."""
    minimal_config.executor_config.override_config = {
        "nodeSelector": {
            "node-type": "gpu-node",
            "zone": "us-west1-a",
        }
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify node selector was added
    assert hasattr(nimservice.spec, "nodeSelector")
    assert nimservice.spec.nodeSelector["node-type"] == "gpu-node"
    assert nimservice.spec.nodeSelector["zone"] == "us-west1-a"


def test_compile_nimservice_override_config_resources(backend_config, sample_deployment, minimal_config):
    """Test that override_config can override resource limits."""
    minimal_config.executor_config.override_config = {
        "resources": {
            "limits": {
                "nvidia.com/gpu": "8",
                "memory": "64Gi",
            },
            "requests": {
                "cpu": "4000m",
                "memory": "32Gi",
            },
        }
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    resources = nimservice.spec.resources
    # Override should merge/replace resources
    assert resources.limits["nvidia.com/gpu"].root == "8"
    assert resources.limits["memory"].root == "64Gi"
    assert resources.requests["cpu"].root == "4000m"
    assert resources.requests["memory"].root == "32Gi"


def test_compile_nimservice_override_config_deep_merge(backend_config, sample_deployment, minimal_config):
    """Test that override_config performs deep merge on nested structures."""
    # Set up a base config with some resources
    minimal_config.executor_config.gpu = 2

    # Override only the memory limit, GPU limit should remain
    minimal_config.executor_config.override_config = {
        "resources": {
            "limits": {
                "memory": "128Gi",
            }
        }
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    resources = nimservice.spec.resources
    # GPU should still be there from base config
    assert resources.limits["nvidia.com/gpu"].root == "2"
    # Memory should be added from override
    assert resources.limits["memory"].root == "128Gi"
    # CPU requests should still be there from base config
    assert resources.requests["cpu"].root == "1000m"


def test_compile_nimservice_override_config_serializes_correctly(backend_config, sample_deployment, minimal_config):
    """Test that override_config values serialize correctly to dict for k8s API."""
    # Use override_config with multiple field types
    minimal_config.executor_config.override_config = {
        "env": [
            {"name": "OVERRIDE_VAR", "value": "override_value"},
            {"name": "ANOTHER_VAR", "value": "another_value"},
        ],
        "tolerations": [
            {
                "key": "nvidia.com/gpu",
                "operator": "Equal",
                "value": "true",
                "effect": "NoSchedule",
            },
        ],
        "nodeSelector": {
            "node-type": "gpu-node",
            "zone": "us-west1-a",
        },
        "resources": {
            "limits": {
                "nvidia.com/gpu": "4",
                "memory": "64Gi",
            },
            "requests": {
                "cpu": "2000m",
                "memory": "32Gi",
            },
        },
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Serialize to dict as would be sent to k8s API
    nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

    # Verify top-level structure
    assert nimservice_dict["apiVersion"] == "apps.nvidia.com/v1alpha1"
    assert nimservice_dict["kind"] == "NIMService"
    assert "spec" in nimservice_dict

    spec = nimservice_dict["spec"]

    # Verify env vars are in correct k8s format (list of dicts with name/value)
    assert "env" in spec
    assert isinstance(spec["env"], list)
    env_dict = {item["name"]: item["value"] for item in spec["env"]}
    assert "OVERRIDE_VAR" in env_dict
    assert env_dict["OVERRIDE_VAR"] == "override_value"
    assert "ANOTHER_VAR" in env_dict
    assert env_dict["ANOTHER_VAR"] == "another_value"

    # Verify tolerations are in correct k8s format
    assert "tolerations" in spec
    assert isinstance(spec["tolerations"], list)
    assert len(spec["tolerations"]) == 1
    assert spec["tolerations"][0]["key"] == "nvidia.com/gpu"
    assert spec["tolerations"][0]["operator"] == "Equal"
    assert spec["tolerations"][0]["value"] == "true"
    assert spec["tolerations"][0]["effect"] == "NoSchedule"

    # Verify nodeSelector is in correct k8s format (flat dict)
    assert "nodeSelector" in spec
    assert isinstance(spec["nodeSelector"], dict)
    assert spec["nodeSelector"]["node-type"] == "gpu-node"
    assert spec["nodeSelector"]["zone"] == "us-west1-a"

    # Verify resources are in correct k8s format (nested dicts with string values)
    assert "resources" in spec
    assert "limits" in spec["resources"]
    assert "requests" in spec["resources"]
    assert spec["resources"]["limits"]["nvidia.com/gpu"] == "4"
    assert spec["resources"]["limits"]["memory"] == "64Gi"
    assert spec["resources"]["requests"]["cpu"] == "2000m"
    assert spec["resources"]["requests"]["memory"] == "32Gi"

    # Verify the dict can be serialized to JSON (final check for k8s compatibility)
    json_str = json.dumps(nimservice_dict)
    assert json_str  # Should not raise an exception
    parsed_back = json.loads(json_str)
    assert parsed_back["spec"]["env"][0]["name"] == "OVERRIDE_VAR"


def test_compile_nimservice_override_config_serializes_to_yaml(backend_config, sample_deployment, minimal_config):
    """Test that override_config values serialize correctly to YAML for kubectl apply."""
    # Use override_config with various field types
    minimal_config.executor_config.override_config = {
        "env": [
            {"name": "CUSTOM_ENV", "value": "custom_value"},
        ],
        "tolerations": [
            {
                "key": "special-hardware",
                "operator": "Exists",
                "effect": "NoSchedule",
            },
        ],
        "nodeSelector": {
            "hardware": "gpu",
        },
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Serialize to dict then to YAML (as kubectl would do)
    nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)
    yaml_output = yaml.dump(nimservice_dict, default_flow_style=False, sort_keys=False)

    # Parse back from YAML to verify roundtrip
    parsed_yaml = yaml.safe_load(yaml_output)

    # Verify override values survived the roundtrip
    assert "env" in parsed_yaml["spec"]
    env_names = [e["name"] for e in parsed_yaml["spec"]["env"]]
    assert "CUSTOM_ENV" in env_names

    assert "tolerations" in parsed_yaml["spec"]
    assert parsed_yaml["spec"]["tolerations"][0]["key"] == "special-hardware"
    assert parsed_yaml["spec"]["tolerations"][0]["operator"] == "Exists"

    assert "nodeSelector" in parsed_yaml["spec"]
    assert parsed_yaml["spec"]["nodeSelector"]["hardware"] == "gpu"

    # Verify the YAML is in a format kubectl can apply
    # (basic sanity checks for k8s YAML format)
    assert parsed_yaml["apiVersion"] == "apps.nvidia.com/v1alpha1"
    assert parsed_yaml["kind"] == "NIMService"
    assert "metadata" in parsed_yaml
    assert "name" in parsed_yaml["metadata"]
    assert "namespace" in parsed_yaml["metadata"]


# ============================================================================
# k8s_nim_operator_config Tests
# ============================================================================


def test_compile_nimservice_k8s_nim_operator_config_resources(backend_config, sample_deployment, minimal_config):
    """Test that k8s_nim_operator_config can add/override resource limits and requests."""
    # Add k8s_nim_operator_config with resources
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "resources": {
            "limits": {
                "memory": "32Gi",
            },
            "requests": {
                "cpu": "4",
                "memory": "16Gi",
            },
        }
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    resources = nimservice.spec.resources
    # GPU should still be there from base config (gpu=1 from minimal_config)
    assert "nvidia.com/gpu" in resources.limits
    assert resources.limits["nvidia.com/gpu"].root == "1"

    # Memory limits from k8s_nim_operator_config should be merged
    assert "memory" in resources.limits
    assert resources.limits["memory"].root == "32Gi"

    # CPU requests should be overridden from k8s_nim_operator_config
    assert "cpu" in resources.requests
    assert resources.requests["cpu"].root == "4"

    # Memory requests from k8s_nim_operator_config
    assert "memory" in resources.requests
    assert resources.requests["memory"].root == "16Gi"


def test_compile_nimservice_k8s_nim_operator_config_tolerations(backend_config, sample_deployment, minimal_config):
    """Test that k8s_nim_operator_config can add tolerations."""
    # Add k8s_nim_operator_config with tolerations
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "tolerations": [
            {
                "key": "nvidia.com/gpu",
                "operator": "Exists",
                "effect": "NoSchedule",
            },
            {
                "key": "dedicated",
                "operator": "Equal",
                "value": "ml-workload",
                "effect": "NoSchedule",
            },
        ]
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify tolerations were added
    assert nimservice.spec.tolerations is not None
    assert len(nimservice.spec.tolerations) == 2

    # Check first toleration
    assert nimservice.spec.tolerations[0].key == "nvidia.com/gpu"
    assert nimservice.spec.tolerations[0].operator == "Exists"
    assert nimservice.spec.tolerations[0].effect == "NoSchedule"

    # Check second toleration
    assert nimservice.spec.tolerations[1].key == "dedicated"
    assert nimservice.spec.tolerations[1].operator == "Equal"
    assert nimservice.spec.tolerations[1].value == "ml-workload"
    assert nimservice.spec.tolerations[1].effect == "NoSchedule"


def test_compile_nimservice_k8s_nim_operator_config_node_selector(backend_config, sample_deployment, minimal_config):
    """Test that k8s_nim_operator_config can add node selector with snake_case to camelCase conversion."""
    # Add k8s_nim_operator_config with node_selector (snake_case)
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "node_selector": {
            "node-type": "gpu-node",
            "zone": "us-west1-a",
            "hardware": "a100",
        }
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify nodeSelector was added (camelCase in K8s)
    assert nimservice.spec.nodeSelector is not None
    assert nimservice.spec.nodeSelector["node-type"] == "gpu-node"
    assert nimservice.spec.nodeSelector["zone"] == "us-west1-a"
    assert nimservice.spec.nodeSelector["hardware"] == "a100"


def test_compile_nimservice_k8s_nim_operator_config_startup_probe_grace_seconds(
    backend_config, sample_deployment, minimal_config
):
    """Test that k8s_nim_operator_config can set startup_probe_grace_seconds."""
    # Add k8s_nim_operator_config with startup_probe_grace_seconds
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.startup_probe_grace_seconds = 600
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "startup_probe_grace_seconds": 600,
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify startup probe uses the calculated failureThreshold
    # 600 seconds / 10 = 60 failures
    assert nimservice.spec.startupProbe is not None
    assert nimservice.spec.startupProbe.enabled is True
    assert nimservice.spec.startupProbe.probe is not None
    assert nimservice.spec.startupProbe.probe.periodSeconds == 10
    assert nimservice.spec.startupProbe.probe.failureThreshold == 60


def test_compile_nimservice_k8s_nim_operator_config_startup_probe_grace_seconds_rounds_up(
    backend_config, sample_deployment, minimal_config
):
    """Test that startup_probe_grace_seconds rounds up when dividing by 10."""
    # Add k8s_nim_operator_config with grace_seconds that doesn't divide evenly
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.startup_probe_grace_seconds = 605
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "startup_probe_grace_seconds": 605,
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify it rounds up: 605 / 10 = 60.5 → 61
    assert nimservice.spec.startupProbe.probe.failureThreshold == 61


def test_compile_nimservice_k8s_nim_operator_config_startup_probe_grace_seconds_various_values(
    backend_config, sample_deployment, minimal_config
):
    """Test startup_probe_grace_seconds with various values to verify rounding."""
    test_cases = [
        (600, 60),  # Exact division
        (605, 61),  # Rounds up
        (1201, 121),  # Large value rounds up
        (10, 1),  # Small value
        (1, 1),  # Minimum practical value
        (999, 100),  # Rounds up
        (1000, 100),  # Exact division
    ]

    for grace_seconds, expected_threshold in test_cases:
        minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
        minimal_config.executor_config.k8s_nim_operator_config.startup_probe_grace_seconds = grace_seconds
        minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
            "startup_probe_grace_seconds": grace_seconds,
        }

        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_config,
            k8s_namespace="default",
            resource_name="md-test-ns-test-deployment",
        )

        assert nimservice.spec.startupProbe.probe.failureThreshold == expected_threshold, (
            f"For grace_seconds={grace_seconds}, expected failureThreshold={expected_threshold}, "
            f"but got {nimservice.spec.startupProbe.probe.failureThreshold}"
        )


def test_compile_nimservice_startup_probe_default_when_no_grace_seconds(
    backend_config, sample_deployment, minimal_config
):
    """Test that startup probe uses default 600 seconds (60 failures) when grace_seconds is not provided."""
    # No k8s_nim_operator_config provided
    minimal_config.executor_config.k8s_nim_operator_config = None

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify default startup probe: 600 seconds / 10 = 60 failures
    assert nimservice.spec.startupProbe is not None
    assert nimservice.spec.startupProbe.enabled is True
    assert nimservice.spec.startupProbe.probe.periodSeconds == 10
    assert nimservice.spec.startupProbe.probe.failureThreshold == 60


def test_compile_nimservice_k8s_nim_operator_config_multiple_fields(backend_config, sample_deployment, minimal_config):
    """Test that k8s_nim_operator_config can set multiple fields at once."""
    # Add k8s_nim_operator_config with multiple fields
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.startup_probe_grace_seconds = 1200
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "resources": {
            "limits": {"memory": "64Gi"},
            "requests": {"cpu": "8", "memory": "32Gi"},
        },
        "tolerations": [
            {"key": "gpu-node", "operator": "Exists", "effect": "NoSchedule"},
        ],
        "node_selector": {
            "accelerator": "nvidia-a100",
        },
        "startup_probe_grace_seconds": 1200,
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Verify all fields were applied
    assert nimservice.spec.resources.limits["memory"].root == "64Gi"
    assert nimservice.spec.resources.requests["cpu"].root == "8"
    assert len(nimservice.spec.tolerations) == 1
    assert nimservice.spec.tolerations[0].key == "gpu-node"
    assert nimservice.spec.nodeSelector["accelerator"] == "nvidia-a100"
    # Verify startup probe grace period: 1200 / 10 = 120
    assert nimservice.spec.startupProbe.probe.failureThreshold == 120


def test_compile_nimservice_k8s_nim_operator_config_precedence_over_defaults(
    backend_config, sample_deployment, minimal_config
):
    """Test that k8s_nim_operator_config takes precedence over defaults."""
    # Base config has gpu=1 which sets nvidia.com/gpu limit to "1"
    minimal_config.executor_config.gpu = 2

    # k8s_nim_operator_config should override GPU limit
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "resources": {
            "limits": {
                "nvidia.com/gpu": "4",  # Override from 2 to 4
            },
        }
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    resources = nimservice.spec.resources
    # Should be 4, not 2 from the base config
    assert resources.limits["nvidia.com/gpu"].root == "4"


def test_compile_nimservice_override_config_precedence_over_k8s_nim_operator_config(
    backend_config, sample_deployment, minimal_config
):
    """Test that override_config takes precedence over k8s_nim_operator_config."""
    # Set both k8s_nim_operator_config and override_config with conflicting values
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "node_selector": {
            "zone": "us-west1-a",
            "hardware": "gpu",
        },
        "tolerations": [
            {"key": "from-k8s-config", "operator": "Exists"},
        ],
    }

    minimal_config.executor_config.override_config = {
        "nodeSelector": {
            "zone": "us-east1-b",  # Override zone
            "environment": "production",  # Add new field
        },
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # override_config should win for nodeSelector
    assert nimservice.spec.nodeSelector["zone"] == "us-east1-b"
    assert nimservice.spec.nodeSelector["environment"] == "production"
    # hardware should still be there from k8s_nim_operator_config (deep merge)
    assert nimservice.spec.nodeSelector["hardware"] == "gpu"

    # tolerations from k8s_nim_operator_config should still be there
    assert len(nimservice.spec.tolerations) == 1
    assert nimservice.spec.tolerations[0].key == "from-k8s-config"


def test_compile_nimservice_k8s_nim_operator_config_empty_does_nothing(
    backend_config, sample_deployment, minimal_config
):
    """Test that empty k8s_nim_operator_config doesn't affect the spec."""
    # Set k8s_nim_operator_config with no fields
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {}

    nimservice_with_empty = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Remove k8s_nim_operator_config
    minimal_config.executor_config.k8s_nim_operator_config = None

    nimservice_without = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Should be equivalent
    assert nimservice_with_empty.spec.model_dump(exclude_none=True) == nimservice_without.spec.model_dump(
        exclude_none=True
    )


def test_compile_nimservice_k8s_nim_operator_config_serializes_correctly(
    backend_config, sample_deployment, minimal_config
):
    """Test that k8s_nim_operator_config values serialize correctly to dict for k8s API."""
    # Set k8s_nim_operator_config with various field types
    minimal_config.executor_config.k8s_nim_operator_config = MagicMock()
    minimal_config.executor_config.k8s_nim_operator_config.model_dump.return_value = {
        "resources": {
            "limits": {"memory": "32Gi"},
            "requests": {"cpu": "4", "memory": "16Gi"},
        },
        "tolerations": [
            {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"},
        ],
        "node_selector": {
            "hardware": "a100",
        },
    }

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Serialize to dict as would be sent to k8s API
    nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

    spec = nimservice_dict["spec"]

    # Verify resources are serialized correctly
    assert "resources" in spec
    assert spec["resources"]["limits"]["memory"] == "32Gi"
    assert spec["resources"]["requests"]["cpu"] == "4"
    assert spec["resources"]["requests"]["memory"] == "16Gi"

    # Verify tolerations are serialized correctly
    assert "tolerations" in spec
    assert len(spec["tolerations"]) == 1
    assert spec["tolerations"][0]["key"] == "nvidia.com/gpu"

    # Verify nodeSelector is serialized correctly (camelCase)
    assert "nodeSelector" in spec
    assert spec["nodeSelector"]["hardware"] == "a100"

    # Verify the dict can be serialized to JSON (final check for k8s compatibility)
    json_str = json.dumps(nimservice_dict)
    assert json_str
    parsed_back = json.loads(json_str)
    assert parsed_back["spec"]["nodeSelector"]["hardware"] == "a100"


def test_compile_nimservice_serializes_to_dict(backend_config, sample_deployment, minimal_config):
    """Test that compiled NIMService can be serialized to dict for k8s API."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Should be able to serialize to dict
    nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

    # Verify top-level structure
    assert "apiVersion" in nimservice_dict
    assert "kind" in nimservice_dict
    assert "metadata" in nimservice_dict
    assert "spec" in nimservice_dict

    # Verify it matches the expected API version
    assert nimservice_dict["apiVersion"] == "apps.nvidia.com/v1alpha1"
    assert nimservice_dict["kind"] == "NIMService"


def test_compile_nimservice_matches_example_structure(backend_config, sample_deployment):
    """Test that compiled NIMService matches the structure from example YAML."""
    # Create a config that matches the example YAML
    config = MagicMock()
    config.workspace = "ben-test"
    config.name = "llama-config"
    config.entity_version = "v1"

    config.engine = "nim"
    config.model_spec = MagicMock()
    config.model_spec.lora_enabled = True
    config.model_spec.model_name = "llama-3.2-3b-instruct"
    config.model_spec.model_namespace = "ben-test"
    config.model_spec.model_revision = None
    config.model_spec.tool_call_config = None
    config.executor_config = MagicMock()
    config.executor_config.image_name = "nvcr.io/nim/meta/llama-3.2-3b-instruct"
    config.executor_config.image_tag = "1.8.5"
    config.executor_config.gpu = 1
    config.executor_config.disk_size = "200Gi"
    config.executor_config.additional_envs = {}
    config.executor_config.k8s_nim_operator_config = None
    config.executor_config.override_config = {}

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=config,
        k8s_namespace="aire-cicd",
        resource_name="modeldeployment-ben-test-llama-3-2-3b-instruct-deployment",
    )

    # Verify structure matches example
    assert nimservice.apiVersion == "apps.nvidia.com/v1alpha1"
    assert nimservice.kind == "NIMService"
    assert nimservice.spec.authSecret == "ngc-api"
    assert nimservice.spec.image.repository == "nvcr.io/nim/meta/llama-3.2-3b-instruct"
    assert nimservice.spec.image.tag == "1.8.5"
    assert nimservice.spec.resources.limits["nvidia.com/gpu"].root == "1"
    assert nimservice.spec.expose.service.type == "ClusterIP"
    assert nimservice.spec.expose.service.port == 8000

    # Verify env vars
    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert "NIM_GUIDED_DECODING_BACKEND" in env_vars
    assert "NIM_SERVED_MODEL_NAME" in env_vars
    assert "NIM_PEFT_SOURCE" in env_vars
    assert "NIM_PEFT_REFRESH_INTERVAL" in env_vars


def test_compile_nimservice_serializes_to_valid_yaml(backend_config, sample_deployment, full_config):
    """Test that compiled NIMService can be serialized to valid YAML."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=full_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Serialize to dict (as would be sent to k8s API)
    nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

    # Convert to YAML
    yaml_output = yaml.dump(nimservice_dict, default_flow_style=False, sort_keys=False)

    # Verify YAML is parseable
    parsed_yaml = yaml.safe_load(yaml_output)

    # Verify required top-level fields
    assert parsed_yaml["apiVersion"] == "apps.nvidia.com/v1alpha1"
    assert parsed_yaml["kind"] == "NIMService"
    assert "metadata" in parsed_yaml
    assert "spec" in parsed_yaml

    # Verify metadata structure
    assert parsed_yaml["metadata"]["name"] == "md-test-ns-test-deployment"
    assert parsed_yaml["metadata"]["namespace"] == "default"
    assert "labels" in parsed_yaml["metadata"]

    # Verify spec has all required fields
    spec = parsed_yaml["spec"]
    assert "authSecret" in spec
    assert "image" in spec
    assert "resources" in spec
    assert "storage" in spec
    assert "expose" in spec
    assert "env" in spec

    # Verify image structure
    assert spec["image"]["repository"] == "nvcr.io/nim/meta/llama-3.2-3b-instruct"
    assert spec["image"]["tag"] == "1.8.5"
    assert spec["image"]["pullPolicy"] == "IfNotPresent"

    # Verify resources structure
    assert "limits" in spec["resources"]
    assert "nvidia.com/gpu" in spec["resources"]["limits"]
    assert "requests" in spec["resources"]
    assert "cpu" in spec["resources"]["requests"]

    # Verify storage structure
    assert "pvc" in spec["storage"]
    assert spec["storage"]["pvc"]["create"] is True
    assert spec["storage"]["pvc"]["size"] == "200Gi"

    # Verify expose structure
    assert "service" in spec["expose"]
    assert spec["expose"]["service"]["type"] == "ClusterIP"
    assert spec["expose"]["service"]["port"] == 8000

    # Verify env vars are present as a list
    assert isinstance(spec["env"], list)
    assert len(spec["env"]) > 0

    # Verify env vars have correct structure
    env_names = [env["name"] for env in spec["env"]]
    assert "NIM_GUIDED_DECODING_BACKEND" in env_names
    assert "NIM_SERVED_MODEL_NAME" in env_names


def test_compile_nimservice_yaml_structure_matches_example(backend_config, sample_deployment):
    """Test that compiled NIMService YAML has same structure as example."""
    # Create config matching the example
    config = MagicMock()
    config.workspace = "ben-test"
    config.name = "llama-config"
    config.entity_version = "v1"

    config.engine = "nim"
    config.model_spec = MagicMock()
    config.model_spec.lora_enabled = True
    config.model_spec.model_name = "llama-3.2-3b-instruct"
    config.model_spec.model_namespace = "ben-test"
    config.model_spec.model_revision = None
    config.model_spec.tool_call_config = None
    config.executor_config = MagicMock()
    config.executor_config.image_name = "nvcr.io/nim/meta/llama-3.2-3b-instruct"
    config.executor_config.image_tag = "1.8.5"
    config.executor_config.gpu = 1
    config.executor_config.disk_size = "200Gi"
    config.executor_config.additional_envs = {}
    config.executor_config.k8s_nim_operator_config = None
    config.executor_config.override_config = {}

    # Compile NIMService
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=config,
        k8s_namespace="aire-cicd",
        resource_name="modeldeployment-ben-test-llama-3-2-3b-instruct-deployment",
    )

    # Serialize to dict
    compiled_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

    # Load example YAML
    example_path = Path(__file__).parent / "data" / "example-nimservice.yaml"
    with open(example_path) as f:
        example_dict = yaml.safe_load(f)

    # Compare key structural elements (not exact values, since our config differs slightly)
    assert compiled_dict["apiVersion"] == example_dict["apiVersion"]
    assert compiled_dict["kind"] == example_dict["kind"]

    # Verify same top-level spec fields exist
    compiled_spec_keys = set(compiled_dict["spec"].keys())

    # Our compiled version should have all the same major sections
    # (though we may not implement every field yet)
    assert "authSecret" in compiled_spec_keys
    assert "image" in compiled_spec_keys
    assert "env" in compiled_spec_keys
    assert "expose" in compiled_spec_keys
    assert "resources" in compiled_spec_keys
    assert "storage" in compiled_spec_keys

    # Verify image structure matches (we may have a subset of fields)
    compiled_image_keys = set(compiled_dict["spec"]["image"].keys())
    # Our compiled version should have the core fields
    assert "repository" in compiled_image_keys
    assert "tag" in compiled_image_keys
    assert "pullPolicy" in compiled_image_keys

    # Verify expose structure matches
    assert "service" in compiled_dict["spec"]["expose"]
    assert "service" in example_dict["spec"]["expose"]
    assert set(compiled_dict["spec"]["expose"]["service"].keys()) <= set(
        example_dict["spec"]["expose"]["service"].keys()
    )

    # Verify resources structure matches
    assert "limits" in compiled_dict["spec"]["resources"]
    assert "requests" in compiled_dict["spec"]["resources"]
    assert "limits" in example_dict["spec"]["resources"]
    assert "requests" in example_dict["spec"]["resources"]

    # Verify storage structure matches
    assert "pvc" in compiled_dict["spec"]["storage"]
    assert "pvc" in example_dict["spec"]["storage"]


def test_compile_nimservice_can_roundtrip_through_yaml(backend_config, sample_deployment, minimal_config):
    """Test that NIMService can be serialized to YAML and parsed back."""
    # Compile NIMService
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    # Serialize to dict
    nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

    # Convert to YAML string
    yaml_string = yaml.dump(nimservice_dict, default_flow_style=False)

    # Parse back from YAML
    parsed_dict = yaml.safe_load(yaml_string)

    # Verify key fields survived the roundtrip
    assert parsed_dict["apiVersion"] == "apps.nvidia.com/v1alpha1"
    assert parsed_dict["kind"] == "NIMService"
    assert parsed_dict["metadata"]["name"] == "md-test-ns-test-deployment"
    assert parsed_dict["spec"]["authSecret"] == "ngc-api"
    assert parsed_dict["spec"]["image"]["repository"] == "nvcr.io/nim/meta/llama-3-8b-instruct"
    assert parsed_dict["spec"]["resources"]["limits"]["nvidia.com/gpu"] == "1"
    assert parsed_dict["spec"]["expose"]["service"]["port"] == 8000

    # Verify the parsed dict can be used to create a Kubernetes resource
    # (In real usage, this would be sent to kubectl or k8s Python client)
    assert "metadata" in parsed_dict
    assert "spec" in parsed_dict
    assert parsed_dict["kind"] == "NIMService"


# ============================================================================
# Multi-LLM Configuration Tests
# ============================================================================


def test_compile_nimservice_multi_llm_with_files_service(backend_config, sample_deployment, minimal_config):
    """Test multi-LLM configuration for Files service (no HF_TOKEN/HF_ENDPOINT in env)."""
    # Set up multi-LLM image (using default)
    minimal_config.executor_config.image_name = None  # Will use default
    minimal_config.model_spec.model_namespace = "nvidia"
    minimal_config.model_spec.model_name = "Llama-3.1-Nemotron-Nano-4B-v1.1"

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={
            "files": "http://nemo-files:8000",
            "models": "http://nemo-models:8000",
        },
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_config,
            k8s_namespace="default",
            resource_name="md-test-ns-test-deployment",
        )

        env_dict = {env.name: env.value for env in nimservice.spec.env if env.value}
        env_names = [env.name for env in nimservice.spec.env]

        # NIMCache pulls from Files; NIMService does not need HF_TOKEN or HF_ENDPOINT in env
        assert "HF_TOKEN" not in env_names
        assert "HF_ENDPOINT" not in env_dict

        assert "NIM_MODEL_NAME" in env_dict
        assert env_dict["NIM_MODEL_NAME"] == "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1"
        assert "NIM_SERVED_MODEL_NAME" in env_dict
        assert env_dict["NIM_SERVED_MODEL_NAME"] == "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1"
        assert "NIM_GUIDED_DECODING_BACKEND" in env_dict
        assert env_dict["NIM_GUIDED_DECODING_BACKEND"] == "outlines"


def test_compile_nimservice_multi_llm_user_overrides_decoding_backend(
    backend_config, sample_deployment, minimal_config
):
    """Test that user can override NIM_GUIDED_DECODING_BACKEND for multi-LLM."""
    # Set up multi-LLM with user override
    minimal_config.executor_config.image_name = None  # Will use default
    minimal_config.model_spec.model_namespace = "nvidia"
    minimal_config.model_spec.model_name = "Llama-3.1-Nemotron-Nano-4B-v1.1"
    minimal_config.executor_config.additional_envs = {
        "NIM_GUIDED_DECODING_BACKEND": "custom_backend",
    }

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={
            "files": "http://files-service:8000",
            "models": "http://models-service:8000",
        },
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_config,
            k8s_namespace="default",
            resource_name="md-test-ns-test-deployment",
        )

        env_dict = {env.name: env.value for env in nimservice.spec.env if env.value}

        # User override should take precedence
        assert env_dict["NIM_GUIDED_DECODING_BACKEND"] == "custom_backend"


def test_compile_nimservice_llm_specific_nim_traditional_behavior(backend_config, sample_deployment, minimal_config):
    """Test that LLM-specific NIMs use traditional configuration (not multi-LLM behavior)."""
    # Set up LLM-specific image (NOT default)
    minimal_config.executor_config.image_name = "nvcr.io/nim/meta/llama-3-8b-instruct"
    minimal_config.model_spec.model_namespace = "meta"
    minimal_config.model_spec.model_name = "llama-3-8b-instruct"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    env_dict = {env.name: env.value for env in nimservice.spec.env if env.value}

    # Should NOT have hf:// prefix for LLM-specific NIMs
    assert "NIM_MODEL_NAME" in env_dict
    assert env_dict["NIM_MODEL_NAME"] == "meta/llama-3-8b-instruct"
    assert not env_dict["NIM_MODEL_NAME"].startswith("hf://")

    # Should NOT have HF_ENDPOINT
    assert "HF_ENDPOINT" not in env_dict

    # Should use default backend (outlines) for LLM-specific
    assert "NIM_GUIDED_DECODING_BACKEND" in env_dict
    assert env_dict["NIM_GUIDED_DECODING_BACKEND"] == "outlines"


# ============================================================================
# NIMCache Compilation Tests
# ============================================================================


def test_compile_nimcache_basic(backend_config):
    """Test NIMCache CR generation for SFT models."""
    # Configure backend config
    backend_config.default_storage_class = "local-storage"
    backend_config.files_auth_secret = "nemo-models-files-token"
    backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    backend_config.default_user_id = 1000
    backend_config.default_group_id = 1000

    # Mock platform config
    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={
            "files": "http://files-service:8000",
            "models": "http://models-service:8000",
        },
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        # Generate NIMCache
        nimcache = compile_nimcache(
            backend_config=backend_config,
            k8s_namespace="default",
            resource_name="test-deployment",
            model_namespace="test-ns",
            model_name="test-model",
            pvc_size="200Gi",
            huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
            model_revision="v1",
        )

        # Verify NIMCache structure
        assert nimcache.apiVersion == "apps.nvidia.com/v1alpha1"
        assert nimcache.kind == "NIMCache"
        assert nimcache.metadata["name"] == "test-deployment"
        assert nimcache.metadata["namespace"] == "default"

        # Verify storage configuration
        assert nimcache.spec.storage.pvc.create is True
        assert nimcache.spec.storage.pvc.size == "200Gi"
        assert nimcache.spec.storage.pvc.storageClass == "local-storage"

        # Verify Files service source configuration (uses Hf CRD type for HF-compatible API)
        assert nimcache.spec.source.hf is not None
        assert nimcache.spec.source.hf.endpoint == "http://files-service:8000/apis/files/v2/hf"
        assert nimcache.spec.source.hf.namespace == "test-ns"
        assert nimcache.spec.source.hf.modelName == "test-model"
        assert nimcache.spec.source.hf.revision == "v1"
        assert nimcache.spec.source.hf.authSecret == "nemo-models-files-token"
        assert nimcache.spec.source.hf.modelPuller == "nvcr.io/nvidia/model-puller:latest"
        assert nimcache.spec.source.hf.pullSecret == "nvcr-secret"


def test_compile_nimcache_without_v2hf_suffix(backend_config):
    """Test NIMCache CR generation when files service URL does NOT include /v2/hf suffix."""
    # Configure backend config
    backend_config.default_storage_class = "local-storage"
    backend_config.files_auth_secret = "nemo-models-files-token"
    backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    backend_config.default_user_id = None
    backend_config.default_group_id = None

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        # Generate NIMCache
        nimcache = compile_nimcache(
            backend_config=backend_config,
            k8s_namespace="default",
            resource_name="test-deployment",
            model_namespace="test-ns",
            model_name="test-model",
            pvc_size="200Gi",
            huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
            model_revision=None,
        )

        # Verify endpoint HAS /apis/files/v2/hf appended
        assert nimcache.spec.source.hf is not None
        assert nimcache.spec.source.hf.endpoint == "http://files-service:8000/apis/files/v2/hf"


def test_compile_nimcache_with_v2hf_suffix(backend_config):
    """Test NIMCache CR generation when files service URL already includes /v2/hf suffix."""
    # Configure backend config
    backend_config.default_storage_class = "local-storage"
    backend_config.files_auth_secret = "nemo-models-files-token"
    backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    backend_config.default_user_id = None
    backend_config.default_group_id = None

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000/v2/hf"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        # Generate NIMCache
        nimcache = compile_nimcache(
            backend_config=backend_config,
            k8s_namespace="default",
            resource_name="test-deployment",
            model_namespace="test-ns",
            model_name="test-model",
            pvc_size="200Gi",
            huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
            model_revision=None,
        )

        # When base URL has /v2/hf, urljoin appends apis/files/v2/hf to it
        assert nimcache.spec.source.hf is not None
        assert nimcache.spec.source.hf.endpoint == "http://files-service:8000/v2/apis/files/v2/hf"


def test_compile_nimcache_with_custom_auth_secret(backend_config):
    """Test NIMCache CR generation with custom files_auth_secret config."""
    # Configure backend config with CUSTOM auth secret name
    backend_config.default_storage_class = "local-storage"
    backend_config.files_auth_secret = "my-custom-files-secret"
    backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    backend_config.default_user_id = None
    backend_config.default_group_id = None

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        # Generate NIMCache
        nimcache = compile_nimcache(
            backend_config=backend_config,
            k8s_namespace="default",
            resource_name="test-deployment",
            model_namespace="test-ns",
            model_name="test-model",
            pvc_size="200Gi",
            huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
            model_revision=None,
        )

        # Verify custom auth secret is used in NIMCache
        assert nimcache.spec.source.hf is not None
        assert nimcache.spec.source.hf.authSecret == "my-custom-files-secret"
        # Ensure it's not using the default value
        assert nimcache.spec.source.hf.authSecret != "nemo-models-files-token"


def test_compile_nimcache_default_resources_tolerations_node_selector(backend_config):
    """Test NIMCache honors default_resources, default_tolerations, default_node_selector like NIMService."""
    backend_config.default_storage_class = "local-storage"
    backend_config.files_auth_secret = "nemo-models-files-token"
    backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    backend_config.default_user_id = 1000
    backend_config.default_group_id = 1000
    backend_config.default_resources = {
        "requests": {"cpu": "2", "memory": "8Gi"},
        "limits": {"memory": "16Gi"},
    }
    backend_config.default_tolerations = [
        {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"},
    ]
    backend_config.default_node_selector = {"node-type": "gpu-node", "zone": "us-west1-a"}

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimcache = compile_nimcache(
            backend_config=backend_config,
            k8s_namespace="default",
            resource_name="test-deployment",
            model_namespace="test-ns",
            model_name="test-model",
            pvc_size="200Gi",
            huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
            model_revision=None,
        )

    # Resources: mapped from requests (then limits) to NIMCache cpu/memory
    assert nimcache.spec.resources is not None
    assert nimcache.spec.resources.cpu is not None
    assert nimcache.spec.resources.memory is not None
    # RootModel types may wrap int/str
    cpu_val = getattr(nimcache.spec.resources.cpu, "root", nimcache.spec.resources.cpu)
    mem_val = getattr(nimcache.spec.resources.memory, "root", nimcache.spec.resources.memory)
    assert cpu_val == "2"
    assert mem_val == "8Gi"

    # Tolerations
    assert nimcache.spec.tolerations is not None
    assert len(nimcache.spec.tolerations) == 1
    assert nimcache.spec.tolerations[0].key == "nvidia.com/gpu"
    assert nimcache.spec.tolerations[0].operator == "Exists"
    assert nimcache.spec.tolerations[0].effect == "NoSchedule"

    # Node selector
    assert nimcache.spec.nodeSelector is not None
    assert nimcache.spec.nodeSelector == {"node-type": "gpu-node", "zone": "us-west1-a"}


def test_compile_nimcache_no_defaults_when_unset(backend_config):
    """Test NIMCache has no resources/tolerations/nodeSelector when backend defaults are unset."""
    backend_config.default_storage_class = "local-storage"
    backend_config.files_auth_secret = "nemo-models-files-token"
    backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    backend_config.default_user_id = None
    backend_config.default_group_id = None
    # Explicitly leave default_resources, default_tolerations, default_node_selector as None

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimcache = compile_nimcache(
            backend_config=backend_config,
            k8s_namespace="default",
            resource_name="test-deployment",
            model_namespace="test-ns",
            model_name="test-model",
            pvc_size="200Gi",
            huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
            model_revision=None,
        )

    assert nimcache.spec.resources is None
    assert nimcache.spec.tolerations is None
    assert nimcache.spec.nodeSelector is None


def test_compile_nimcache_default_labels_and_annotations(backend_config):
    """Test that default_labels and default_annotations from backend config are applied to NIMCache CR and PVC."""
    backend_config.default_storage_class = "local-storage"
    backend_config.files_auth_secret = "nemo-models-files-token"
    backend_config.huggingface_model_puller_image_pull_secret = "nvcr-secret"
    backend_config.default_labels = {"team": "ml-platform", "env": "prod"}
    backend_config.default_annotations = {"prometheus.io/scrape": "true"}

    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimcache = compile_nimcache(
            backend_config=backend_config,
            k8s_namespace="default",
            resource_name="test-deployment",
            model_namespace="test-ns",
            model_name="test-model",
            pvc_size="200Gi",
            huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
            model_revision=None,
        )

    assert nimcache.metadata["labels"]["team"] == "ml-platform"
    assert nimcache.metadata["labels"]["env"] == "prod"
    assert nimcache.metadata["labels"]["app.kubernetes.io/name"] == "test-deployment"
    assert nimcache.metadata["annotations"] == {"prometheus.io/scrape": "true"}
    assert nimcache.spec.storage.pvc.annotations == {"prometheus.io/scrape": "true"}


def test_compile_nimservice_nimcache_files_service_no_ft_env(backend_config, sample_deployment, minimal_config):
    """With NIMCache + multi-LLM image, do not set NIM_FT_MODEL (match docker)."""
    minimal_config.model_spec.model_namespace = "e2e-workspace"
    minimal_config.model_spec.model_name = "qwen-2-5-1-5b"
    minimal_config.executor_config.image_name = "nvcr.io/nim/nvidia/llm-nim"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
        nimcache_name="md-test-ns-test-deployment",
    )

    env_dict = {env.name: env.value for env in nimservice.spec.env if env.value}
    assert env_dict["NIM_MODEL_NAME"] == "/model-store"
    assert env_dict["NIM_SERVED_MODEL_NAME"] == "e2e-workspace/qwen-2-5-1-5b"
    # NIM_CACHE_PATH not set by compiler (reverted for isolation test)
    assert "NIM_FT_MODEL" not in env_dict
    # FILES_SERVICE (multi-LLM) does not get NIM_FT_MODEL or NIM_CUSTOM_MODEL
    assert "NIM_CUSTOM_MODEL" not in env_dict
    # NGC_API_KEY from auth secret for parity with Docker
    ngc_env = next(e for e in nimservice.spec.env if e.name == "NGC_API_KEY")
    assert ngc_env.valueFrom is not None
    assert ngc_env.valueFrom.secretKeyRef is not None
    assert ngc_env.valueFrom.secretKeyRef.key == "NGC_API_KEY"
    assert ngc_env.valueFrom.secretKeyRef.name == backend_config.auth_secret


def test_compile_nimservice_nimcache_files_service_sft_has_ft_env(backend_config, sample_deployment, minimal_config):
    """With NIMCache and model-specific image, set NIM_FT_MODEL and NGC_API_KEY."""
    minimal_config.model_spec.model_namespace = "e2e-workspace"
    minimal_config.model_spec.model_name = "sft-model"
    # Model-specific image (not multi-LLM) so NIM_FT_MODEL is set.
    minimal_config.executor_config.image_name = "nvcr.io/nim/meta/llama-3_1-8b-instruct"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
        nimcache_name="md-test-ns-test-deployment",
    )

    env_dict = {env.name: env.value for env in nimservice.spec.env if env.value}
    assert env_dict["NIM_MODEL_NAME"] == "/model-store"
    assert env_dict["NIM_SERVED_MODEL_NAME"] == "e2e-workspace/sft-model"
    assert env_dict["NIM_FT_MODEL"] == "/model-store"
    assert env_dict["NIM_CUSTOM_MODEL"] == "/model-store"
    # NIM_CACHE_PATH not set by compiler (reverted for isolation test)
    # NGC_API_KEY from auth secret for parity with Docker
    ngc_env = next(e for e in nimservice.spec.env if e.name == "NGC_API_KEY")
    assert ngc_env.valueFrom is not None
    assert ngc_env.valueFrom.secretKeyRef is not None
    assert ngc_env.valueFrom.secretKeyRef.key == "NGC_API_KEY"
    assert ngc_env.valueFrom.secretKeyRef.name == backend_config.auth_secret


def test_compile_nimservice_nimcache_files_service_sft_multi_llm_no_ft_env(
    backend_config, sample_deployment, minimal_config
):
    """With NIMCache but multi-LLM image, do NOT set NIM_FT_MODEL (breaks LoRA)."""
    minimal_config.model_spec.model_namespace = "e2e-workspace"
    minimal_config.model_spec.model_name = "sft-model"
    # Explicit multi-LLM image so NIM_FT_MODEL is omitted (minimal_config fixture uses model-specific image).
    minimal_config.executor_config.image_name = "nvcr.io/nim/nvidia/llm-nim"

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
        nimcache_name="md-test-ns-test-deployment",
    )

    env_dict = {env.name: env.value for env in nimservice.spec.env if env.value}
    assert env_dict["NIM_MODEL_NAME"] == "/model-store"
    assert "NIM_FT_MODEL" not in env_dict


def test_compile_nimservice_tool_call_plugin_init_containers(backend_config, sample_deployment, minimal_config):
    """tool_call_plugin compiles three init containers and sets deterministic plugin path."""
    minimal_config.model_spec.tool_call_config = SimpleNamespace(
        tool_call_plugin="test-ws/my-plugin-fileset",
        tool_call_parser=None,
        auto_tool_choice=None,
    )

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
        huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
    )

    assert nimservice.spec.initContainers is not None
    assert len(nimservice.spec.initContainers) == 3

    prepare_container, pull_container, finalize_container = nimservice.spec.initContainers

    assert prepare_container.command is not None
    assert prepare_container.command[0:2] == ["sh", "-c"]
    assert "/model-store/plugin" in prepare_container.command[2]

    assert pull_container.command == ["download", "test-ws/my-plugin-fileset", "--local-dir", "/scratch/plugin"]
    pull_env = {env.name: env.value for env in (pull_container.env or [])}
    assert pull_env["HF_TOKEN"] == "service:models"
    assert pull_env["HF_ENDPOINT"].endswith("/apis/files/v2/hf")

    assert finalize_container.command is not None
    assert finalize_container.command[0:2] == ["sh", "-c"]
    assert "/model-store/plugin/plugin.py" in finalize_container.command[2]

    env_dict = {env.name: env.value for env in nimservice.spec.env if env.value}
    assert env_dict["NIM_TOOL_PARSER_PLUGIN"] == "/model-store/plugin/plugin.py"


def test_tool_call_plugin_finalize_script_moves_single_py(tmp_path):
    """Finalize script moves exactly one discovered .py to plugin_path."""
    scratch_dir = tmp_path / "scratch" / "plugin"
    plugin_path = tmp_path / "model-store" / "plugin" / "plugin.py"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    plugin_path.parent.mkdir(parents=True, exist_ok=True)
    source = scratch_dir / "custom_plugin.py"
    source.write_text("print('ok')\n")

    script = TOOL_CALL_PLUGIN_FINALIZE_SCRIPT_TEMPLATE.format(
        scratch_dir=str(scratch_dir), plugin_path=str(plugin_path)
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert plugin_path.exists()
    assert plugin_path.read_text() == "print('ok')\n"
    assert not source.exists()


def test_tool_call_plugin_finalize_script_fails_with_multiple_py_files(tmp_path):
    """Finalize script fails when more than one .py file exists."""
    scratch_dir = tmp_path / "scratch" / "plugin"
    plugin_path = tmp_path / "model-store" / "plugin" / "plugin.py"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    plugin_path.parent.mkdir(parents=True, exist_ok=True)
    (scratch_dir / "a.py").write_text("print('a')\n")
    (scratch_dir / "b.py").write_text("print('b')\n")

    script = TOOL_CALL_PLUGIN_FINALIZE_SCRIPT_TEMPLATE.format(
        scratch_dir=str(scratch_dir), plugin_path=str(plugin_path)
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    assert result.returncode != 0
    combined_output = (result.stdout or "") + (result.stderr or "")
    assert "must contain exactly one .py file" in combined_output
    assert not plugin_path.exists()


def test_apply_k8s_nim_operator_config_tolerations_replaced(backend_config, sample_deployment, minimal_config):
    """Tolerations from config replace spec tolerations when present (full list)."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files:8000", "models": "http://models:8000"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_config,
            k8s_namespace="default",
            resource_name="md-test",
        )
    spec = nimservice.spec
    assert spec.tolerations is None
    k8s_config = {
        "tolerations": [
            {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"},
        ],
    }
    result = _apply_k8s_nim_operator_config(spec, k8s_config)
    assert len(result.tolerations) == 1
    t = result.tolerations[0]
    assert t.key == "nvidia.com/gpu"
    assert t.operator == "Exists"
    assert t.effect == "NoSchedule"


def test_apply_k8s_nim_operator_config_empty_config_returns_unchanged(
    backend_config, sample_deployment, minimal_config
):
    """Empty k8s_config leaves spec unchanged."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files:8000", "models": "http://models:8000"},
    )
    with patch(
        "nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler.get_platform_config",
        return_value=platform_config,
    ):
        nimservice = compile_nimservice(
            backend_config=backend_config,
            deployment=sample_deployment,
            config=minimal_config,
            k8s_namespace="default",
            resource_name="md-test",
        )
    spec = nimservice.spec
    result = _apply_k8s_nim_operator_config(spec, {})
    assert result.resources == spec.resources
    assert result.nodeSelector == spec.nodeSelector


def test_compile_nimservice_trust_remote_code_env_var(backend_config, sample_deployment, minimal_config):
    """Test that NIM_FORCE_TRUST_REMOTE_CODE=1 is set when model_entity.trust_remote_code is True."""
    from nemo_platform.types.models.model_entity import ModelEntity

    model_entity = ModelEntity(
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
        trust_remote_code=True,
    )

    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
        model_entity=model_entity,
    )

    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert env_vars.get("NIM_FORCE_TRUST_REMOTE_CODE") == "1"


def test_compile_nimservice_no_trust_remote_code_by_default(backend_config, sample_deployment, minimal_config):
    """Test that NIM_FORCE_TRUST_REMOTE_CODE is NOT set when model_entity is None or trust_remote_code is False."""
    nimservice = compile_nimservice(
        backend_config=backend_config,
        deployment=sample_deployment,
        config=minimal_config,
        k8s_namespace="default",
        resource_name="md-test-ns-test-deployment",
    )

    env_vars = {env.name: env.value for env in nimservice.spec.env}
    assert "NIM_FORCE_TRUST_REMOTE_CODE" not in env_vars
