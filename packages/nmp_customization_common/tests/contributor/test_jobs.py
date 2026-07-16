# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime-gate tests for the shared customization submit scaffold.

Covers :func:`require_container_runtime` (automodel / unsloth) and
:func:`require_distributed_runtime` (rl). We patch the platform config and the
Docker-availability probe so the checks are exercised without a real runtime.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from nemo_platform_plugin.config import Runtime
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nmp.customization_common.contributor import jobs as jobs_mod
from nmp.customization_common.contributor.jobs import (
    require_container_runtime,
    require_distributed_runtime,
)


@pytest.fixture
def _patch_runtime(monkeypatch: pytest.MonkeyPatch):
    """Return a helper that pins the platform runtime and Docker availability."""

    def _apply(runtime: Runtime, *, docker_available: bool = True) -> None:
        monkeypatch.setattr(
            jobs_mod.NemoPlatformConfig,
            "get",
            classmethod(lambda cls: SimpleNamespace(runtime=runtime)),
        )
        monkeypatch.setattr(
            "nemo_platform_plugin.config.validate_docker_available",
            lambda: docker_available,
        )

    return _apply


class TestRequireContainerRuntime:
    def test_kubernetes_single_node_ok(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.KUBERNETES)
        require_container_runtime("Automodel")  # no raise

    def test_kubernetes_multi_node_ok(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.KUBERNETES)
        require_container_runtime("Automodel", num_nodes=2)  # no raise

    def test_docker_single_node_ok(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.DOCKER, docker_available=True)
        require_container_runtime("Automodel")  # no raise

    def test_docker_daemon_unavailable_raises(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.DOCKER, docker_available=False)
        with pytest.raises(PlatformJobCompilationError, match="reachable Docker daemon"):
            require_container_runtime("Automodel")

    def test_docker_multi_node_requires_kubernetes(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.DOCKER, docker_available=True)
        with pytest.raises(PlatformJobCompilationError, match="multi-node training .* requires"):
            require_container_runtime("Automodel", num_nodes=2)

    def test_none_runtime_raises(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.NONE)
        with pytest.raises(PlatformJobCompilationError, match="requires a container runtime"):
            require_container_runtime("Automodel")

    def test_none_runtime_multi_node_raises_kubernetes_message(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.NONE)
        with pytest.raises(PlatformJobCompilationError, match="multi-node training .* requires"):
            require_container_runtime("Automodel", num_nodes=4)


class TestRequireDistributedRuntime:
    def test_kubernetes_ok(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.KUBERNETES)
        require_distributed_runtime("NeMo-RL")  # no raise

    def test_docker_raises(self, _patch_runtime) -> None:
        _patch_runtime(Runtime.DOCKER)
        with pytest.raises(PlatformJobCompilationError, match="requires platform.runtime: kubernetes"):
            require_distributed_runtime("NeMo-RL")
