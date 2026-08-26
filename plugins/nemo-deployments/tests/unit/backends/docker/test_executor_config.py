# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_deployments_plugin.backends.docker.config import DockerExecutorConfig
from nemo_deployments_plugin.backends.labels import DEFAULT_RESOURCE_SCOPE
from pydantic import ValidationError


def test_docker_executor_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEMO_DEPLOYMENTS_DOCKER_NETWORK", raising=False)
    monkeypatch.delenv("MODELS_DOCKER_NETWORK", raising=False)

    cfg = DockerExecutorConfig()
    assert cfg.port_range_start == 49152
    assert cfg.port_range_end == 49251
    assert cfg.resource_scope == DEFAULT_RESOURCE_SCOPE
    assert cfg.oneshot_observe_timeout_seconds == 5
    assert cfg.network is None


def test_docker_executor_config_reads_network_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEMO_DEPLOYMENTS_DOCKER_NETWORK", "nmp-e2e-test-network")
    monkeypatch.setenv("MODELS_DOCKER_NETWORK", "legacy-network")

    cfg = DockerExecutorConfig()

    assert cfg.network == "nmp-e2e-test-network"


def test_docker_executor_config_reads_legacy_models_network_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEMO_DEPLOYMENTS_DOCKER_NETWORK", raising=False)
    monkeypatch.setenv("MODELS_DOCKER_NETWORK", "legacy-network")

    cfg = DockerExecutorConfig()

    assert cfg.network == "legacy-network"


def test_docker_executor_config_rejects_inverted_port_range() -> None:
    with pytest.raises(ValidationError, match="port_range_start must not exceed port_range_end"):
        DockerExecutorConfig(port_range_start=9200, port_range_end=9100)
