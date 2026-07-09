# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Self, Sequence

from nemo_platform import NeMoPlatform
from nmp.core.jobs.app.profiles import ExecutionProfileT
from nmp.core.jobs.app.schemas import BackendRef, ProfileRef, ProviderRef
from nmp.core.jobs.controllers.backends.base import DEFAULT_PROFILE, DEFAULT_PROVIDER, JobBackend
from nmp.core.jobs.controllers.backends.docker import CPUDockerJobBackend, GPUDockerJobBackend
from nmp.core.jobs.controllers.backends.kubernetes import (
    CPUKubernetesJobBackend,
    GPUKubernetesJobBackend,
    VolcanoJobBackend,
)
from nmp.core.jobs.controllers.backends.subprocess import SubprocessJobBackend
from nmp.core.jobs.controllers.backends.test import TestE2ECPUJobBackend, TestE2EGPUJobBackend


@dataclass(frozen=True)
class RegistryKey:
    """Immutable key for identifying unique backend instances in the registry.

    Combines provider and execution profile to create a unique identifier
    for backend configurations.
    """

    provider: ProviderRef
    """The provider reference (e.g., "cpu", "gpu")"""
    profile: ProfileRef
    """The executor profile reference for this specific configuration (e.g., "default", ...)"""


@dataclass(frozen=True)
class BackendKey:
    """Immutable key for identifying unique backend instances in the registry.

    Combines provider and backend key to create a unique identifier
    for backend configurations.
    """

    provider: ProviderRef
    """The provider reference (e.g., "cpu", "gpu", "gpu_distributed")"""
    backend: BackendRef
    """The backend reference (e.g., "docker", "kubernetes", "volcano_job")"""


# Type alias for the backend registry mapping provider references to backend classes
BackendRegistryT = dict[BackendKey, type[JobBackend]]

# Global registry of available job backends mapped by provider name
backend_registry: BackendRegistryT = {
    BackendKey("cpu", "docker"): CPUDockerJobBackend,
    BackendKey("gpu", "docker"): GPUDockerJobBackend,
    BackendKey("cpu", "kubernetes_job"): CPUKubernetesJobBackend,
    BackendKey("gpu", "kubernetes_job"): GPUKubernetesJobBackend,
    BackendKey("gpu_distributed", "kubernetes_job"): GPUKubernetesJobBackend,
    BackendKey("gpu_distributed", "volcano_job"): VolcanoJobBackend,
    BackendKey("subprocess", "subprocess"): SubprocessJobBackend,
    BackendKey("cpu", "e2e"): TestE2ECPUJobBackend,
    BackendKey("gpu", "e2e"): TestE2EGPUJobBackend,
}


class BackendRegistry:
    """Registry for managing job execution backends across different providers and profiles.

    The BackendRegistry serves as a central repository for instantiated job backends,
    allowing the system to maintain separate backend instances for different execution
    profiles even when using the same underlying provider technology.

    Each backend instance is uniquely identified by a combination of provider and
    execution profile, enabling fine-grained control over job execution environments.
    """

    def __init__(self, registry: dict[RegistryKey, JobBackend]) -> None:
        """Initialize the registry with a pre-populated mapping of backends.

        Args:
            registry: Dictionary mapping RegistryKey instances to configured JobBackend instances
        """
        self._registry = registry

    @classmethod
    def from_config(
        cls,
        nmp_sdk: NeMoPlatform,
        profiles: Sequence[ExecutionProfileT],
        backends: BackendRegistryT = backend_registry,
    ) -> Self:
        """Create a BackendRegistry from a list of execution profiles.

        This factory method processes execution profiles and instantiates the appropriate
        backend for each profile using the provided backend registry. Each execution
        profile's configuration is validated during backend instantiation.

        Args:
            profiles: List of execution profiles defining backend configurations
            backends: Registry of available backend classes (defaults to global backend_registry)

        Returns:
            A configured BackendRegistry instance with all backends initialized

        Raises:
            KeyError: If a profile references an executor not found in the backends registry
            ValidationError: If a profile's configuration is invalid for its backend type
        """
        registry: dict[RegistryKey, JobBackend] = {}

        for executor in profiles:
            # Execution profiles are unique with respect to the provider
            # and profile combination
            registry_key = RegistryKey(executor.provider, executor.profile)
            backend_key = BackendKey(executor.provider, executor.backend)
            backend = backends[backend_key]

            # The config from the execution profile hasn't been validated
            # yet. Calling the backend constructor will serialize the raw
            # config into the backend's expected format and validate it
            registry[registry_key] = backend(nmp_sdk, executor.config, executor.profile)
        return cls(registry)

    def get_backend(self, *, provider: str | None = None, profile: str | None = None) -> JobBackend:
        """Retrieve a configured backend for the specified provider and profile.

        Args:
            provider: The provider identifier (e.g., "cpu", "gpu")
            profile: The execution profile identifier (e.g., "default", "a100", "test")

        Returns:
            The configured JobBackend instance for the specified provider and profile

        Raises:
            KeyError: If no backend is registered for the given provider and profile combination
        """
        if profile is None:
            profile = DEFAULT_PROFILE

        if provider is None:
            provider = DEFAULT_PROVIDER

        key = RegistryKey(provider, profile)
        if key in self._registry:
            return self._registry[key]

        raise KeyError(f"No backend found for provider '{provider}' and profile '{profile}'")

    def get_all_backends(self) -> list[JobBackend]:
        # sort by keys
        sorted_keys = sorted(list(self._registry.keys()), key=lambda k: f"{k.provider} {k.profile}")
        return [self._registry[k] for k in sorted_keys]

    def shutdown_all_backends(self) -> None:
        """Shutdown all registered backends in the registry."""
        for backend in self._registry.values():
            backend.shutdown()
