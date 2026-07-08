# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for BackendRegistry."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nmp.core.models.controllers.backends.registry import (
    BackendRegistry,
    DockerBackendConfigModel,
    K8sNimOperatorBackendConfigModel,
)


@pytest.fixture(autouse=True)
def mock_docker_client():
    """Mock Docker client to avoid needing actual Docker daemon."""
    with patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock:
        client = MagicMock()
        mock.return_value = client

        # Setup default behaviors
        client.login = MagicMock()
        client.api = MagicMock()
        client.api.timeout = 600
        client.containers = MagicMock()
        client.images = MagicMock()
        client.volumes = MagicMock()

        yield client


@pytest.fixture(autouse=True)
def mock_k8s_config():
    """Mock kubernetes config loading to avoid needing actual k8s config."""
    with (
        patch("nmp.core.models.controllers.backends.k8s_nim_operator.backend.k8s_config.load_incluster_config"),
        patch("nmp.core.models.controllers.backends.k8s_nim_operator.backend.k8s_config.load_kube_config"),
        patch("nmp.core.models.controllers.backends.k8s_nim_operator.backend.k8s_client.ApiClient"),
        patch("nmp.core.models.controllers.backends.k8s_nim_operator.backend.DynamicClient"),
    ):
        yield


@pytest.fixture
def mock_nmp_sdk():
    """Create a mock AsyncNeMoPlatform SDK."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def sample_backend_configs():
    """Create sample backend configurations."""
    return {
        "docker": DockerBackendConfigModel(enabled=True),
    }


def test_backend_registry_from_config(mock_nmp_sdk, sample_backend_configs):
    """Test creating BackendRegistry from configuration."""
    registry = BackendRegistry.from_config(
        nmp_sdk=mock_nmp_sdk,
        backend_configs=sample_backend_configs,
        huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
    )

    # Verify registry was created
    assert isinstance(registry, BackendRegistry)

    # Verify backend can be retrieved
    docker_backend = registry.get_backend("docker")
    assert docker_backend is not None


def test_backend_registry_get_default_backend(mock_nmp_sdk, sample_backend_configs):
    """Test getting default backend (the single enabled one)."""
    registry = BackendRegistry.from_config(
        nmp_sdk=mock_nmp_sdk,
        backend_configs=sample_backend_configs,
        huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
    )

    # Get default backend (should be the enabled one - docker)
    default_backend = registry.get_backend()
    assert default_backend is not None


def test_backend_registry_get_backend_not_found(mock_nmp_sdk, sample_backend_configs):
    """Test that KeyError is raised for unknown backend."""
    registry = BackendRegistry.from_config(
        nmp_sdk=mock_nmp_sdk,
        backend_configs=sample_backend_configs,
        huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
    )

    with pytest.raises(KeyError, match="Backend 'unknown' not found"):
        registry.get_backend("unknown")


def test_backend_registry_list_backends(mock_nmp_sdk, sample_backend_configs):
    """Test listing all registered backends."""
    registry = BackendRegistry.from_config(
        nmp_sdk=mock_nmp_sdk,
        backend_configs=sample_backend_configs,
        huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
    )

    backends = registry.list_backends()
    assert "docker" in backends
    assert len(backends) == 1


def test_backend_registry_empty_config_raises_error(mock_nmp_sdk):
    """Test that empty backend config raises ValueError."""
    with pytest.raises(ValueError, match="At least one backend must be configured"):
        BackendRegistry.from_config(
            nmp_sdk=mock_nmp_sdk,
            backend_configs={},
            huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
        )


def test_backend_registry_init_with_empty_dict_raises_error():
    """Test that initializing BackendRegistry with empty dict raises ValueError."""
    with pytest.raises(ValueError, match="Backend registry cannot be empty"):
        BackendRegistry(registry={})


def test_backend_registry_unknown_backend_type(mock_nmp_sdk):
    """Test that unknown backend type raises KeyError when backend class not in registry."""
    bad_config = {"docker": DockerBackendConfigModel(enabled=True)}

    with pytest.raises(KeyError, match="Unknown backend 'docker'"):
        BackendRegistry.from_config(
            nmp_sdk=mock_nmp_sdk,
            backend_configs=bad_config,
            huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
            available_backends={},
        )


def test_backend_registry_single_backend(mock_nmp_sdk):
    """Test registry with only one backend."""
    single_config = {"docker": DockerBackendConfigModel(enabled=True)}

    registry = BackendRegistry.from_config(
        nmp_sdk=mock_nmp_sdk,
        backend_configs=single_config,
        huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
    )

    # Verify only one backend
    backends = registry.list_backends()
    assert len(backends) == 1
    assert backends[0] == "docker"

    # Verify default backend is set
    default_backend = registry.get_backend()
    assert default_backend is not None


def test_backend_config_discriminated_union_parsing():
    """Test that backend configs can be parsed from dict (simulating YAML loading)."""
    from nmp.core.models.controllers.backends.registry import BackendConfig
    from pydantic import TypeAdapter

    docker_dict = {"enabled": True}
    k8s_nim_dict = {
        "enabled": True,
        "default_storage_class": "fast-ssd",
        "default_pvc_size": "500Gi",
        "peft_source": "http://custom-entity-store:8000",
    }

    adapter = TypeAdapter(BackendConfig)

    docker_config = adapter.validate_python(docker_dict)
    assert docker_config.enabled is True
    assert isinstance(docker_config, DockerBackendConfigModel)
    assert hasattr(docker_config, "default_nimservice_image")

    k8s_config = adapter.validate_python(k8s_nim_dict)
    assert k8s_config.enabled is True
    assert isinstance(k8s_config, K8sNimOperatorBackendConfigModel)
    assert k8s_config.default_storage_class == "fast-ssd"
    assert k8s_config.default_pvc_size == "500Gi"
    assert k8s_config.peft_source == "http://custom-entity-store:8000"


def test_backend_config_from_yaml_to_registry(mock_nmp_sdk):
    """Test end-to-end: parse backend configs from dicts (like YAML) and use them with registry."""
    from nmp.core.models.config import ControllerConfig

    yaml_config = {
        "docker": {"enabled": False},
        "nim_operator": {"enabled": True, "default_pvc_size": "100Gi"},
    }

    # Use ControllerConfig so validate_backends uses backend key to pick the right model
    controller_config = ControllerConfig(backends=yaml_config)
    parsed_configs = controller_config.backends

    assert isinstance(parsed_configs["docker"], DockerBackendConfigModel)
    assert isinstance(parsed_configs["nim_operator"], K8sNimOperatorBackendConfigModel)
    assert parsed_configs["nim_operator"].default_pvc_size == "100Gi"

    registry = BackendRegistry.from_config(
        nmp_sdk=mock_nmp_sdk,
        backend_configs=parsed_configs,
        huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
    )

    assert len(registry.list_backends()) == 1
    assert "nim_operator" in registry.list_backends()


def test_backend_registry_no_enabled_backends_raises_error(mock_nmp_sdk):
    """Test that having no enabled backends raises ValueError."""
    config_with_no_enabled = {
        "docker": DockerBackendConfigModel(enabled=False),
        "nim_operator": K8sNimOperatorBackendConfigModel(enabled=False),
    }

    with pytest.raises(ValueError, match="No backends are enabled"):
        BackendRegistry.from_config(
            nmp_sdk=mock_nmp_sdk,
            backend_configs=config_with_no_enabled,
            huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
        )


def test_backend_registry_multiple_enabled_backends_raises_error(mock_nmp_sdk):
    """Test that having multiple enabled backends raises ValueError."""
    config_with_multiple_enabled = {
        "docker": DockerBackendConfigModel(enabled=True),
        "nim_operator": K8sNimOperatorBackendConfigModel(enabled=True),
    }

    with pytest.raises(ValueError, match="Multiple backends are enabled"):
        BackendRegistry.from_config(
            nmp_sdk=mock_nmp_sdk,
            backend_configs=config_with_multiple_enabled,
            huggingface_model_puller="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
        )
