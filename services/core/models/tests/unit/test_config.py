# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Models service configuration."""

import pytest
from nmp.common.config import Runtime
from nmp.core.models.config import (
    ControllerConfig,
    backends,
    config,
    get_default_backends_for_runtime,
    merge_backends,
)
from nmp.core.models.controllers.backends.registry import (
    DockerBackendConfigModel,
    K8sNimOperatorBackendConfigModel,
    NoneBackendConfigModel,
)
from pydantic import ValidationError


def test_models_controller_config_defaults():
    """Test that Models Controller config has correct default values."""
    assert config.controller.interval_seconds == 5
    assert isinstance(config.controller.backends, dict)


def test_models_controller_config_types():
    """Test that Models Controller config fields have correct types."""
    assert isinstance(config.controller.interval_seconds, int)


def test_models_controller_config_positive_values():
    """Test that Models Controller config has positive values."""
    assert config.controller.interval_seconds > 0


def test_config_structure():
    """Test that config has the correct structure."""
    # Test that we have the expected structure
    assert hasattr(config, "controller")
    assert hasattr(config, "parallelism")

    # Test that Controller config has expected fields
    assert hasattr(config.controller, "interval_seconds")
    assert hasattr(config.controller, "backends")

    # Parallelism config (Pydantic models with defaults)
    assert config.parallelism.gpus_per_node_default == 8
    assert config.parallelism.gpu_memory_gb_default == 80
    assert config.parallelism.memory.pressure_threshold == 0.60
    assert config.parallelism.model_size_thresholds.very_large == 300.0


def test_get_default_backends_for_docker_runtime():
    """Test that docker backend is selected and enabled for DOCKER runtime."""
    backends = get_default_backends_for_runtime(Runtime.DOCKER)
    assert "docker" in backends
    assert isinstance(backends["docker"], DockerBackendConfigModel)
    assert backends["docker"].enabled is True
    assert "nim_operator" not in backends


def test_get_default_backends_for_kubernetes_runtime():
    """Test that nim_operator backend is selected and enabled for KUBERNETES runtime."""
    backends = get_default_backends_for_runtime(Runtime.KUBERNETES)
    assert "nim_operator" in backends
    assert isinstance(backends["nim_operator"], K8sNimOperatorBackendConfigModel)
    assert backends["nim_operator"].enabled is True
    assert "docker" not in backends


def test_merge_backends_with_no_custom_backends():
    """Test that merge returns only default backends when no custom backends provided."""
    default_backends = {"docker": DockerBackendConfigModel()}
    custom_backends = {}

    merged = merge_backends(custom_backends, default_backends)

    assert "docker" in merged
    assert len(merged) == 1


def test_merge_backends_with_no_default_backends():
    """Test that merge returns only custom backends when no defaults provided."""
    default_backends = {}
    custom_backends = {"docker": DockerBackendConfigModel()}

    merged = merge_backends(custom_backends, default_backends)

    assert "docker" in merged
    assert len(merged) == 1


def test_merge_backends_custom_overrides_default():
    """Test that custom backend config overrides default backend config."""
    default_backends = {
        "docker": DockerBackendConfigModel(enabled=False),
    }
    custom_backends = {
        "docker": DockerBackendConfigModel(enabled=True),
    }

    merged = merge_backends(custom_backends, default_backends)

    assert "docker" in merged
    assert merged["docker"].enabled is True


def test_merge_backends_combines_different_backends():
    """Test that merge combines different backend types."""
    default_backends = {"docker": DockerBackendConfigModel()}
    custom_backends = {"nim_operator": K8sNimOperatorBackendConfigModel()}

    merged = merge_backends(custom_backends, default_backends)

    assert "docker" in merged
    assert "nim_operator" in merged
    assert len(merged) == 2


def test_merge_backends_preserves_enabled_flag():
    """Test that merge correctly handles enabled flag overrides."""
    default_backends = {
        "docker": DockerBackendConfigModel(enabled=False),
    }
    custom_backends = {
        "docker": DockerBackendConfigModel(enabled=True),
    }

    merged = merge_backends(custom_backends, default_backends)

    assert merged["docker"].enabled is True


def test_merge_backends_disables_conflicting_when_runtime_demoted_to_none():
    """When the runtime auto-demotes to NONE (docker unavailable), any
    user-enabled non-`none` backend must be disabled so the registry can
    pick the `none` fallback cleanly instead of crashing with
    'Multiple backends are enabled'."""
    # Default reflects post-demotion state: NemoPlatformConfig.validate_runtime
    # flipped DOCKER → NONE because the docker socket wasn't reachable.
    default_backends = {"none": NoneBackendConfigModel(enabled=True)}
    # User config (e.g. local.yaml or a downstream override) still asks for docker.
    custom_backends = {"docker": DockerBackendConfigModel(enabled=True)}

    merged = merge_backends(custom_backends, default_backends)

    # `none` survives as the runtime fallback; the conflicting docker entry
    # gets force-disabled.
    assert merged["none"].enabled is True
    assert merged["docker"].enabled is False


def test_merge_backends_leaves_docker_enabled_when_runtime_is_docker():
    """Sanity-check that the demotion-handling logic doesn't disable a
    legitimately-enabled custom backend when the runtime is still DOCKER."""
    default_backends = {"docker": DockerBackendConfigModel(enabled=True)}
    custom_backends = {"docker": DockerBackendConfigModel(enabled=True)}

    merged = merge_backends(custom_backends, default_backends)

    assert merged["docker"].enabled is True
    assert "none" not in merged


def test_merge_backends_force_enables_none_when_user_disabled_it_during_demotion():
    """If the user explicitly disabled `none` AND another backend is enabled,
    runtime demotion to NONE must still leave exactly one enabled backend.

    Without the force-enable, the user's `none: enabled=False` would win on
    merge, my non-`none` disable loop would drop docker, and the registry
    would crash with "No backends are enabled" (the zero-enabled case).
    """
    default_backends = {"none": NoneBackendConfigModel(enabled=True)}
    custom_backends = {
        "none": NoneBackendConfigModel(enabled=False),
        "docker": DockerBackendConfigModel(enabled=True),
    }

    merged = merge_backends(custom_backends, default_backends)

    # `none` is force-enabled (overrides user's explicit disable) so the
    # registry has exactly one enabled backend in the demotion path.
    assert merged["none"].enabled is True
    assert merged["docker"].enabled is False


def test_module_level_backends_variable_exists():
    """Test that the module-level backends variable exists and is a dict."""
    assert backends is not None
    assert isinstance(backends, dict)


def test_merge_backends_with_flat_config_partial_override():
    """Test that merge handles flat config overrides correctly.

    When a custom backend has partial values set, those values should override
    the default, but unset values should be preserved from the default.
    """
    # Default backend with flat config
    default_backends = {
        "nim_operator": K8sNimOperatorBackendConfigModel(
            enabled=True,
            default_storage_class="standard",
            default_pvc_size="100Gi",
        ),
    }

    # Custom backend that only overrides one field
    custom_backends = {
        "nim_operator": K8sNimOperatorBackendConfigModel(
            default_storage_class="fast-ssd",
        ),
    }

    merged = merge_backends(custom_backends, default_backends)

    # The custom storage class should override
    assert merged["nim_operator"].default_storage_class == "fast-ssd"
    # But the PVC size should be preserved from default
    assert merged["nim_operator"].default_pvc_size == "100Gi"


# ============================================================================
# ERROR Deployment GC TTL Config Tests
# ============================================================================


def test_error_deployment_ttl_default():
    """Test that error_deployment_ttl_seconds defaults to 3 hours (10800s)."""
    controller_config = ControllerConfig()
    assert controller_config.error_deployment_ttl_seconds == 10800


def test_error_deployment_ttl_custom_override():
    """Test that error_deployment_ttl_seconds can be overridden."""
    controller_config = ControllerConfig(error_deployment_ttl_seconds=3600)
    assert controller_config.error_deployment_ttl_seconds == 3600


def test_error_deployment_ttl_in_module_config():
    """Test that the module-level config includes error_deployment_ttl_seconds."""
    assert hasattr(config.controller, "error_deployment_ttl_seconds")
    assert isinstance(config.controller.error_deployment_ttl_seconds, int)
    assert config.controller.error_deployment_ttl_seconds > 0


# ============================================================================
# Provider Discovery Config Tests
# ============================================================================


def test_provider_discovery_timeout_default():
    """Provider discovery timeout defaults to 180 seconds for slow external catalogs."""
    controller_config = ControllerConfig()
    assert controller_config.provider_discovery_timeout_seconds == 180


def test_provider_discovery_timeout_custom_override():
    """Provider discovery timeout can be overridden."""
    controller_config = ControllerConfig(provider_discovery_timeout_seconds=240)
    assert controller_config.provider_discovery_timeout_seconds == 240


def test_provider_discovery_max_retries_default():
    """Provider discovery disables SDK retries by default."""
    controller_config = ControllerConfig()
    assert controller_config.provider_discovery_max_retries == 0


def test_provider_discovery_config_in_module_config():
    """Module-level config exposes provider discovery settings."""
    assert config.controller.provider_discovery_timeout_seconds == 180
    assert config.controller.provider_discovery_max_retries == 0


def test_provider_discovery_timeout_rejects_zero():
    """Provider discovery timeout must be at least one second."""
    with pytest.raises(ValidationError):
        ControllerConfig(provider_discovery_timeout_seconds=0)


def test_provider_discovery_max_retries_rejects_negative():
    """Provider discovery max retries must be non-negative."""
    with pytest.raises(ValidationError):
        ControllerConfig(provider_discovery_max_retries=-1)
