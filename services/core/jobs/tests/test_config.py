# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from nmp.common.config import Configuration, Runtime
from nmp.core.jobs.app.providers import (
    ComputeResources,
    ContainerSpec,
    CPUExecutionProvider,
    GPUExecutionProvider,
    SubprocessExecutionProvider,
)
from nmp.core.jobs.app.schemas import PlatformJobEnvironmentVariable
from nmp.core.jobs.config import JobsServiceConfig
from nmp.core.jobs.controllers.backends.base import JobExecutionProfileConfig, resolve_gpu_job_shm_size
from nmp.core.jobs.controllers.backends.config import (
    DefaultExecutionProfileConfig,
    get_default_executor_profiles_for_runtime,
    merge_executor_profiles,
)
from nmp.core.jobs.controllers.backends.docker import (
    DockerJobExecutionProfile,
    DockerJobExecutionProfileConfig,
    k8s_shm_quantity_to_docker,
)
from nmp.core.jobs.controllers.backends.kubernetes import (
    KubernetesJobExecutionProfile,
    KubernetesJobExecutionProfileConfig,
    KubernetesJobStorageConfig,
    VolcanoJobExecutionProfileConfig,
)
from nmp.core.jobs.controllers.backends.registry import BackendKey, BackendRegistry
from nmp.core.jobs.controllers.backends.subprocess import (
    SubprocessJobExecutionProfile,
    SubprocessJobExecutionProfileConfig,
)
from nmp.core.jobs.controllers.backends.test import (
    MockDockerCPUJobBackend,
    MockKubernetesCPUJobBackend,
    MockKubernetesGPUJobBackend,
)
from nmp.core.jobs.entities import PlatformJob
from pydantic import ValidationError


def test_job_instantiation_and_validation(sample_job_dict):
    """Test that a job can be instantiated and has correct step configuration."""
    # Instantiate the job from the dictionary
    job = PlatformJob.model_validate(sample_job_dict)

    # Validate basic job properties
    assert job.name == "docker-test-job"
    assert job.source == "curl-test"
    assert job.spec == {"parameters": {"test_param": "test_value"}}

    # Validate platform spec exists and has steps
    assert job.platform_spec is not None
    assert len(job.platform_spec.steps) == 3

    # Validate first step (CPU)
    cpu_step = job.platform_spec.steps[0]
    assert cpu_step.name == "docker-step-cpu-1"
    assert cpu_step.executor.provider == "cpu"
    assert cpu_step.executor.profile == "default"
    assert cpu_step.executor.container.image == "ubuntu:latest"
    assert cpu_step.environment == [PlatformJobEnvironmentVariable(name="TEST_ENV", value="test_value")]
    assert isinstance(cpu_step.executor, CPUExecutionProvider)

    # Validate second step (GPU)
    gpu_step = job.platform_spec.steps[1]
    assert gpu_step.name == "docker-step-gpu"
    assert gpu_step.executor.provider == "gpu"
    assert gpu_step.executor.profile == "default"
    assert gpu_step.executor.container.image == "ubuntu:latest"
    assert gpu_step.environment == [PlatformJobEnvironmentVariable(name="TEST_ENV", value="test_value")]
    assert gpu_step.executor.resources.num_gpus == 2
    assert isinstance(gpu_step.executor, GPUExecutionProvider)


def test_step_container_command_configuration(sample_job_dict):
    """Test that step container commands are properly configured."""
    job = PlatformJob.model_validate(sample_job_dict)

    expected_command = ["c1", "c2"]
    expected_entrypoint = ["a1", "a2"]

    # Test both steps have the same command structure
    step = job.platform_spec.steps[0]
    assert step.executor.container.command == expected_command
    # Test that entrypoint_list_or_none returns None for this configuration
    assert step.executor.container.entrypoint == expected_entrypoint


def test_step_container_command_is_none(sample_job_dict):
    """Test that step container commands are properly configured when using strings."""
    job = PlatformJob.model_validate(sample_job_dict)

    step = next((step for step in job.platform_spec.steps if step.name == "docker-step-no-command-or-entrypoint"), None)
    assert step is not None
    assert step.executor.container.command == []
    assert step.executor.container.entrypoint == []


def test_backend_registry_configuration(backend_registry):
    """Test that backend registry is properly configured."""
    # Validate Docker executor
    executor = backend_registry.get_backend(profile="default", provider="cpu")
    assert isinstance(executor, MockDockerCPUJobBackend)
    assert isinstance(executor._execution_profile_config, DockerJobExecutionProfileConfig)

    executor = backend_registry.get_backend(provider="cpu")
    assert isinstance(executor, MockDockerCPUJobBackend)
    assert isinstance(executor._execution_profile_config, DockerJobExecutionProfileConfig)

    executor = backend_registry.get_backend()
    assert isinstance(executor, MockDockerCPUJobBackend)
    assert isinstance(executor._execution_profile_config, DockerJobExecutionProfileConfig)

    # Test that we can get a kubernetes backend
    executor = backend_registry.get_backend(profile="k8s", provider="cpu")
    assert isinstance(executor, MockKubernetesCPUJobBackend)
    assert isinstance(executor._execution_profile_config, KubernetesJobExecutionProfileConfig)


def test_step_environment_variables(sample_job_dict):
    """Test that step environment variables are properly configured."""
    job = PlatformJob.model_validate(sample_job_dict)

    # Both steps should have the same environment configuration
    for step in job.platform_spec.steps:
        assert step.environment is not None
        assert step.environment == [PlatformJobEnvironmentVariable(name="TEST_ENV", value="test_value")]
        assert len(step.environment) == 1


def test_job_spec_parameters(sample_job_dict):
    """Test that job spec parameters are correctly configured."""
    job = PlatformJob.model_validate(sample_job_dict)

    assert job.spec is not None
    assert "parameters" in job.spec
    assert job.spec["parameters"]["test_param"] == "test_value"


@patch("nmp.common.sdk_factory.get_platform_sdk")
def test_full_integration_matching_test_registry(mock_get_sdk, sample_job_dict, backend_registry):
    """Test full integration flow matching the test_registry.py script."""
    mock_sdk = MagicMock()
    mock_get_sdk.return_value = mock_sdk

    # Get backend and validate
    backend = backend_registry.get_backend(profile="default", provider="cpu")
    assert backend is not None

    # Create and validate job
    job = PlatformJob.model_validate(sample_job_dict)
    assert job.name == "docker-test-job"
    assert len(job.platform_spec.steps) == 3

    # Validate command extraction works as expected
    first_step = job.platform_spec.steps[0]
    command_list = first_step.executor.container.command
    entrypoint_list = first_step.executor.container.entrypoint

    assert command_list is not None
    assert entrypoint_list is not None
    assert len(command_list) == 2
    assert command_list[0] == "c1"
    assert command_list[1] == "c2"

    assert entrypoint_list is not None
    assert len(entrypoint_list) == 2
    assert entrypoint_list[0] == "a1"
    assert entrypoint_list[1] == "a2"


@patch("nmp.common.sdk_factory.get_platform_sdk")
def test_gpu_step(mock_get_sdk, sample_job_dict, backend_registry):
    """Test full integration flow matching the test_registry.py script."""
    mock_sdk = MagicMock()
    mock_get_sdk.return_value = mock_sdk

    # Get backend and validate
    backend = backend_registry.get_backend(profile="default", provider="gpu")
    assert backend is not None
    assert isinstance(backend, MockKubernetesGPUJobBackend)

    # Create and validate job
    job = PlatformJob.model_validate(sample_job_dict)

    step = next((step for step in job.platform_spec.steps if step.name == "docker-step-gpu"), None)
    assert step is not None
    assert step.executor.container == ContainerSpec(
        image="ubuntu:latest", entrypoint=["a1", "a2"], command=["c1", "c2"]
    )


def test_jobs_config_merge_with_defaults_docker_additional_volumes():
    """Test that Jobs config loaded from partial global_settings merges with defaults and docker additional_volume_mounts load correctly."""
    global_settings = {
        "jobs": {
            "executor_defaults": {
                "docker": {
                    "storage": {
                        "additional_volume_mounts": [
                            {
                                "volume_name": "nmp-e2e-additional-volume",
                                "mount_path": "/mnt/additional_storage",
                                "allow_create_volume": True,
                            }
                        ]
                    }
                }
            }
        }
    }
    config = Configuration.global_settings_to_service_config(global_settings, JobsServiceConfig)

    # Unspecified top-level keys keep defaults
    assert config.reconcile_interval_seconds == 2
    assert config.schedule_interval_seconds == 5

    # Docker executor_defaults: only storage.additional_volume_mounts was overridden
    docker_defaults = config.executor_defaults.docker
    assert docker_defaults.storage.volume_name == "nemo-jobs-storage"  # default unchanged
    additional = docker_defaults.storage.additional_volume_mounts
    assert len(additional) == 1
    assert additional[0].volume_name == "nmp-e2e-additional-volume"
    assert additional[0].mount_path == "/mnt/additional_storage"
    assert additional[0].allow_create_volume is True


def test_docker_default_profiles(monkeypatch):
    # Clear caches to ensure fresh config read
    Configuration.clear_cache()
    test_dir = pathlib.Path(__file__).parent
    monkeypatch.setenv("NMP_CONFIG_FILE_PATH", str(test_dir / "fixtures" / "docker.yaml"))

    config = Configuration.get_service_config(JobsServiceConfig)
    defaults = config.executor_defaults

    assert defaults.docker is not None
    assert defaults.docker.storage.volume_name == "nemo-platform_jobs_storage"


def test_kubernetes_default_profiles(monkeypatch):
    # Clear caches to ensure fresh config read
    Configuration.clear_cache()
    test_dir = pathlib.Path(__file__).parent
    monkeypatch.setenv("NMP_CONFIG_FILE_PATH", str(test_dir / "fixtures" / "kubernetes.yaml"))

    config = Configuration.get_service_config(JobsServiceConfig)
    defaults = config.executor_defaults

    assert defaults.kubernetes_job is not None
    assert defaults.kubernetes_job.storage.pvc_name == "nemo-network-storage"
    # service_account_name defaults to "default" when not set in config
    assert defaults.kubernetes_job.service_account_name == "default"


def test_kubernetes_job_service_account_name_default():
    """KubernetesJobExecutionProfileConfig defaults service_account_name to 'default'."""
    config = KubernetesJobExecutionProfileConfig()
    assert config.service_account_name == "default"


def test_kubernetes_job_service_account_name_from_executor_defaults():
    """executor_defaults.kubernetes_job.service_account_name is loaded from global config."""
    global_settings = {
        "jobs": {
            "executor_defaults": {
                "kubernetes_job": {
                    "service_account_name": "nmp-jobs-sa",
                    "storage": {"pvc_name": "test-pvc"},
                }
            }
        }
    }
    config = Configuration.global_settings_to_service_config(global_settings, JobsServiceConfig)
    assert config.executor_defaults.kubernetes_job.service_account_name == "nmp-jobs-sa"
    assert config.executor_defaults.kubernetes_job.storage.pvc_name == "test-pvc"


def test_volcano_job_service_account_name_default():
    """VolcanoJobExecutionProfileConfig defaults service_account_name to 'default'."""
    config = VolcanoJobExecutionProfileConfig()
    assert config.service_account_name == "default"


def test_job_execution_profile_config_rejects_reserved_env_vars():
    """JobExecutionProfileConfig raises when environment contains reserved names."""
    with pytest.raises(ValidationError) as exc_info:
        JobExecutionProfileConfig(env={"NEMO_JOB_ID": "x"})
    assert "NEMO_JOB_ID" in str(exc_info.value)
    assert "reserved" in str(exc_info.value).lower()


def test_job_execution_profile_config_accepts_non_reserved_env_vars():
    """JobExecutionProfileConfig accepts non-reserved env vars (e.g. HOME)."""
    config = JobExecutionProfileConfig(env={"HOME": "/tmp"})
    assert config.env == {"HOME": "/tmp"}


def test_default_profiles_include_subprocess_for_docker_runtime():
    profiles = get_default_executor_profiles_for_runtime(Runtime.DOCKER, DefaultExecutionProfileConfig())

    assert ("cpu", "default", "docker") in [(p.provider, p.profile, p.backend) for p in profiles]
    assert ("gpu", "default", "docker") in [(p.provider, p.profile, p.backend) for p in profiles]
    assert ("subprocess", "default", "subprocess") in [(p.provider, p.profile, p.backend) for p in profiles]


def test_default_profiles_include_subprocess_for_none_runtime():
    profiles = get_default_executor_profiles_for_runtime(Runtime.NONE, DefaultExecutionProfileConfig())

    assert [(p.provider, p.profile, p.backend) for p in profiles] == [("subprocess", "default", "subprocess")]


def test_backend_registry_resolves_subprocess_default(mock_nmp_client):
    class DummyBackend:
        def __init__(self, nmp_sdk, execution_profile_config, profile_name):
            self.nmp_sdk = nmp_sdk
            self.execution_profile_config = execution_profile_config
            self.profile_name = profile_name

    profiles = get_default_executor_profiles_for_runtime(Runtime.NONE, DefaultExecutionProfileConfig())

    registry = BackendRegistry.from_config(
        nmp_sdk=mock_nmp_client,
        profiles=profiles,
        backends={BackendKey("subprocess", "subprocess"): DummyBackend},
    )

    assert registry.get_backend(provider="subprocess", profile="default") is not None


def test_subprocess_execution_profile_defaults_provider_to_subprocess():
    profile = SubprocessJobExecutionProfile(profile="default")

    assert profile.provider == "subprocess"
    assert profile.backend == "subprocess"


def test_default_profiles_exclude_subprocess_for_kubernetes_runtime():
    profiles = get_default_executor_profiles_for_runtime(Runtime.KUBERNETES, DefaultExecutionProfileConfig())

    assert ("subprocess", "default", "subprocess") not in [(p.provider, p.profile, p.backend) for p in profiles]


def test_merged_profiles():
    default_executors = [
        *get_default_executor_profiles_for_runtime(
            runtime=Runtime.KUBERNETES,
            defaults=DefaultExecutionProfileConfig(
                kubernetes_job=KubernetesJobExecutionProfileConfig(
                    storage=KubernetesJobStorageConfig(
                        pvc_name="default-pvc",
                    ),
                ),
                volcano_job=VolcanoJobExecutionProfileConfig(
                    storage=KubernetesJobStorageConfig(
                        pvc_name="default-pvc",
                    ),
                ),
            ),
        ),
        *get_default_executor_profiles_for_runtime(runtime=Runtime.DOCKER, defaults=DefaultExecutionProfileConfig())[
            2:
        ],
    ]

    assert len(default_executors) == 4
    # Assert that the storage config is set correctly
    for executor in default_executors:
        if hasattr(executor.config, "storage"):
            assert executor.config.storage.pvc_name == "default-pvc"

    custom_executor_profiles = [
        # Override the default GPU profile
        KubernetesJobExecutionProfile(
            provider="gpu",
            profile="default",
            backend="kubernetes_job",
            config=KubernetesJobExecutionProfileConfig(
                namespace="custom-namespace",
            ),
        ),
        # Add a custom profile with a non-default name
        KubernetesJobExecutionProfile(
            provider="gpu",
            profile="high_mem",
            backend="kubernetes_job",
            config=KubernetesJobExecutionProfileConfig(ttl_seconds_active=3600),
        ),
    ]

    merged = merge_executor_profiles(custom_executor_profiles, default_executors)

    assert len(merged) == 5

    cpu_default = next((p for p in merged if p.provider == "cpu" and p.profile == "default"), None)
    assert cpu_default is not None
    assert type(cpu_default.config) is KubernetesJobExecutionProfileConfig
    assert cpu_default.config.namespace is None
    assert cpu_default.config.storage.pvc_name == "default-pvc"

    gpu_default = next((p for p in merged if p.provider == "gpu" and p.profile == "default"), None)
    assert gpu_default is not None
    assert type(gpu_default.config) is KubernetesJobExecutionProfileConfig
    assert gpu_default.config.namespace == "custom-namespace"
    assert gpu_default.config.storage.pvc_name == "default-pvc"

    gpu_high_mem = next((p for p in merged if p.provider == "gpu" and p.profile == "high_mem"), None)
    assert gpu_high_mem is not None
    assert type(gpu_high_mem.config) is KubernetesJobExecutionProfileConfig
    assert gpu_high_mem.config.ttl_seconds_active == 3600

    gpu_distributed = next((p for p in merged if p.provider == "gpu_distributed" and p.profile == "default"), None)
    assert gpu_distributed is not None
    assert type(gpu_distributed.config) is VolcanoJobExecutionProfileConfig
    assert gpu_distributed.config.storage.pvc_name == "default-pvc"

    subprocess_default = next((p for p in merged if p.provider == "subprocess" and p.profile == "default"), None)
    assert subprocess_default is not None
    assert type(subprocess_default.config) is SubprocessJobExecutionProfileConfig


def test_merge_executor_profiles_replaces_when_backend_or_config_type_differs():
    default_executors = [
        DockerJobExecutionProfile(
            provider="cpu",
            profile="default",
            backend="docker",
            config=DockerJobExecutionProfileConfig(ttl_seconds_active=123),
        )
    ]
    custom_executors = [
        KubernetesJobExecutionProfile(
            provider="cpu",
            profile="default",
            backend="kubernetes_job",
            config=KubernetesJobExecutionProfileConfig(namespace="custom-namespace"),
        )
    ]

    merged = merge_executor_profiles(custom_executors, default_executors)

    assert len(merged) == 1
    assert merged[0].backend == "kubernetes_job"
    assert type(merged[0].config) is KubernetesJobExecutionProfileConfig
    assert merged[0].config.namespace == "custom-namespace"


def test_merge_executor_profiles_replaces_default_with_subprocess_profile():
    default_executors = [
        SubprocessJobExecutionProfile(
            profile="default",
            backend="subprocess",
            config=SubprocessJobExecutionProfileConfig(ttl_seconds_active=123),
        )
    ]
    custom_executors = [
        SubprocessJobExecutionProfile(
            profile="default",
            backend="subprocess",
            config=SubprocessJobExecutionProfileConfig(working_directory="/tmp/custom-subprocess-jobs"),
        )
    ]

    merged = merge_executor_profiles(custom_executors, default_executors)

    assert len(merged) == 1
    assert merged[0].backend == "subprocess"
    assert type(merged[0].config) is SubprocessJobExecutionProfileConfig
    assert merged[0].config.working_directory == "/tmp/custom-subprocess-jobs"
    assert merged[0].config.ttl_seconds_active == 123


def test_subprocess_execution_provider_requires_command():
    assert SubprocessExecutionProvider(command=["python", "-m", "task"]).command == ["python", "-m", "task"]

    with pytest.raises(ValidationError, match="command"):
        SubprocessExecutionProvider(command=[])


def test_resolve_gpu_job_shm_size_defaults_and_override():
    assert resolve_gpu_job_shm_size(None, None, 2) == "2Gi"
    executor = ComputeResources(shm_size="4Gi")
    assert resolve_gpu_job_shm_size(executor, None, 2) == "4Gi"
    profile = ComputeResources(shm_size="8Gi")
    assert resolve_gpu_job_shm_size(None, profile, 1) == "8Gi"
    assert resolve_gpu_job_shm_size(executor, profile, 1) == "4Gi"


def test_k8s_shm_quantity_to_docker():
    assert k8s_shm_quantity_to_docker("1Gi") == "1g"
    assert k8s_shm_quantity_to_docker("512Mi") == "512m"


def test_compute_resources_shm_size_validation():
    assert ComputeResources(shm_size="1Gi").shm_size == "1Gi"
    assert ComputeResources(shm_size="  2Gi  ").shm_size == "2Gi"
    assert ComputeResources(shm_size="512Mi").shm_size == "512Mi"
    assert ComputeResources(shm_size="2G").shm_size == "2G"
    assert ComputeResources(shm_size="128M").shm_size == "128M"

    with pytest.raises(ValidationError):
        ComputeResources(shm_size="1Ti")

    with pytest.raises(ValidationError):
        ComputeResources(shm_size="10")

    with pytest.raises(ValidationError):
        ComputeResources(shm_size="1Ki")

    with pytest.raises(ValidationError):
        ComputeResources(shm_size="1Ei")

    with pytest.raises(ValidationError) as exc:
        ComputeResources(shm_size="not-a-quantity")
    assert "shm_size" in str(exc.value).lower() or "suffix" in str(exc.value).lower()

    with pytest.raises(ValidationError):
        ComputeResources(shm_size="")

    with pytest.raises(ValidationError):
        ComputeResources(shm_size="   ")
