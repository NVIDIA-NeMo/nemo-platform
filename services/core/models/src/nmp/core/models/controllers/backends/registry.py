# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend registry for Models Controller service."""

from logging import getLogger
from typing import Dict, Self, Union

from nemo_platform import AsyncNeMoPlatform
from nmp.core.models.controllers.backends.backends import ServiceBackend

# NOTE: import the config model from the plugin-free `config` module (not the
# package __init__) so the registry does not eagerly import the optional
# `nemo_deployments_plugin` dependency. The backend class itself is resolved
# lazily in `from_config` only when the deployments_plugin backend is selected.
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginBackendConfigModel
from nmp.core.models.controllers.backends.docker import DockerBackendConfig as DockerConfig
from nmp.core.models.controllers.backends.docker import DockerServiceBackend
from nmp.core.models.controllers.backends.k8s_nim_operator import K8sNimOperatorConfig, K8sNimOperatorServiceBackend
from nmp.core.models.controllers.backends.none_backend import NoneServiceBackend
from pydantic import BaseModel, Field

logger = getLogger(__name__)


class K8sNimOperatorBackendConfigModel(K8sNimOperatorConfig):
    """Configuration for Kubernetes NIM Operator backend (flat: enabled + operator fields at top level)."""

    enabled: bool = Field(default=False, description="Whether this backend is enabled")


class DockerBackendConfigModel(DockerConfig):
    """Configuration for Docker backend (flat: enabled + Docker config fields at top level)."""

    enabled: bool = Field(default=False, description="Whether this backend is enabled")


class NoneBackendConfigModel(BaseModel):
    """Configuration for the ``none`` backend (no deployment substrate).

    Used when ``platform.runtime`` is ``none``. The backend is a deliberate
    no-op: create/update/delete raise ``NotImplementedError``, status returns
    ``UNKNOWN``, and orphan reconciliation sees no managed deployments.
    """

    enabled: bool = Field(default=False, description="Whether this backend is enabled")


# Union of all backend configurations (no discriminator needed since dict key is the backend name)
BackendConfig = Union[
    DockerBackendConfigModel,
    K8sNimOperatorBackendConfigModel,
    DeploymentsPluginBackendConfigModel,
    NoneBackendConfigModel,
]


# Type alias for the backend name
BackendName = str

# Global registry of always-importable backend implementations. The
# `deployments_plugin` backend is intentionally excluded here because it imports
# the optional `nemo_deployments_plugin` package; it is resolved lazily by
# `_resolve_backend_class` when selected.
backend_classes: Dict[BackendName, type[ServiceBackend]] = {
    "docker": DockerServiceBackend,
    "nim_operator": K8sNimOperatorServiceBackend,
    "none": NoneServiceBackend,
}

# Backends whose implementation lives behind an optional dependency and must be
# imported lazily.
_LAZY_BACKEND_NAMES = frozenset({"deployments_plugin"})

_DEPLOYMENTS_PLUGIN_IMPORT_ERROR = (
    "The deployments_plugin models backend requires the nemo-deployments-plugin "
    "package. Install it (or include the deployments plugin in your platform "
    "profile) before setting models.controller.backends.deployments_plugin.enabled."
)


def _resolve_backend_class(
    name: BackendName, available_backends: Dict[BackendName, type[ServiceBackend]]
) -> type[ServiceBackend]:
    """Return the backend class for ``name``, importing optional backends lazily."""
    if name in available_backends:
        return available_backends[name]
    if name == "deployments_plugin":
        try:
            from nmp.core.models.controllers.backends.deployments_plugin.backend import (
                DeploymentsPluginServiceBackend,
            )
        except ImportError as exc:
            raise ImportError(_DEPLOYMENTS_PLUGIN_IMPORT_ERROR) from exc
        return DeploymentsPluginServiceBackend
    available = ", ".join(sorted({*available_backends, *_LAZY_BACKEND_NAMES}))
    raise KeyError(f"Unknown backend '{name}'. Available backends: {available}")


class BackendRegistry:
    """
    Registry for managing service backends.

    The BackendRegistry maintains instantiated backends and provides access
    to them by name. Each backend is configured from the service configuration
    and initialized once at startup.
    """

    def __init__(self, registry: Dict[BackendName, ServiceBackend]) -> None:
        """Initialize the registry with pre-instantiated backends.

        Args:
            registry: Dictionary mapping backend names to configured ServiceBackend instances

        Raises:
            ValueError: If registry is empty
        """
        if not registry:
            raise ValueError("Backend registry cannot be empty. At least one backend must be provided.")

        self._registry = registry
        self._default_backend = next(iter(self._registry.keys()))
        logger.info(f"Default backend set to: {self._default_backend}")

    @classmethod
    def from_config(
        cls,
        nmp_sdk: AsyncNeMoPlatform,
        backend_configs: Dict[BackendName, BackendConfig],
        huggingface_model_puller: str,
        available_backends: Dict[BackendName, type[ServiceBackend]] = backend_classes,
    ) -> Self:
        """Create a BackendRegistry from backend configurations.

        Args:
            nmp_sdk: NeMo Platform SDK client (for all API interactions including secrets)
            backend_configs: Dict of backend configurations from service config
            huggingface_model_puller: HuggingFace model puller image for NIMCache
            available_backends: Registry of available backend classes

        Returns:
            A configured BackendRegistry instance with the single enabled backend initialized

        Raises:
            KeyError: If a backend configuration references an unknown backend type
            ValueError: If zero or multiple backends are enabled
        """
        if not backend_configs:
            raise ValueError("At least one backend must be configured")

        enabled_backends = {name: config for name, config in backend_configs.items() if config.enabled}

        if len(enabled_backends) == 0:
            raise ValueError("No backends are enabled. Exactly one backend must be enabled.")

        if len(enabled_backends) > 1:
            enabled_names = ", ".join(enabled_backends.keys())
            raise ValueError(
                f"Multiple backends are enabled: {enabled_names}. Only one backend can be enabled at a time."
            )

        registry: Dict[BackendName, ServiceBackend] = {}

        for backend_name, backend_config in enabled_backends.items():
            backend_class = _resolve_backend_class(backend_name, available_backends)

            logger.info(f"Initializing backend: {backend_name}")
            config_dict = backend_config.model_dump(exclude={"enabled"})
            if backend_name in {"nim_operator", "deployments_plugin"}:
                registry[backend_name] = backend_class(nmp_sdk, config_dict, huggingface_model_puller)
            else:
                registry[backend_name] = backend_class(nmp_sdk, config_dict)

        logger.info(f"Backend registry initialized with {len(registry)} backend(s)")
        return cls(registry)

    def get_backend(self, name: str | None = None) -> ServiceBackend:
        """Retrieve a configured backend by name.

        Args:
            name: The backend name (e.g., "docker", "nim_operator").
                If None, returns the default backend.

        Returns:
            The configured ServiceBackend instance

        Raises:
            KeyError: If no backend is registered with the given name
            ValueError: If name is None and no default backend is set
        """
        if name is None:
            if self._default_backend is None:
                raise ValueError("No default backend configured")
            name = self._default_backend

        if name not in self._registry:
            available = ", ".join(self._registry.keys())
            raise KeyError(f"Backend '{name}' not found. Available backends: {available}")

        return self._registry[name]

    def list_backends(self) -> list[str]:
        """List all registered backend names.

        Returns:
            List of backend names currently registered
        """
        return list(self._registry.keys())

    def shutdown_all_backends(self) -> None:
        """Shutdown all registered backends.

        Calls shutdown() on each backend to release resources
        (e.g., close Docker clients, Kubernetes API clients).
        """
        for name, backend in self._registry.items():
            logger.info(f"Shutting down backend: {name}")
            try:
                backend.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down backend {name}: {e}")
