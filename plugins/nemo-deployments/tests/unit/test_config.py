# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from nemo_deployments_plugin.config import (
    ControllerConfig,
    DeploymentsConfig,
    ExecutorConfigEntry,
    runtime_compatible_executor_config,
)
from nemo_platform_plugin.config import Runtime


def test_controller_config_defaults() -> None:
    cfg = DeploymentsConfig()
    assert cfg.controller.interval_seconds == 5
    assert cfg.controller.drift_recovery_max_attempts == 5
    assert cfg.controller.orphan_cleanup_interval_seconds == 30
    assert cfg.controller.starting_timeout_seconds == 3600
    assert cfg.controller.deleting_timeout_seconds == 300


def test_controller_config_custom_orphan_interval() -> None:
    cfg = ControllerConfig(orphan_cleanup_interval_seconds=28)
    assert cfg.orphan_cleanup_interval_seconds == 28


def test_controller_config_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError):
        ControllerConfig(interval_seconds=0)


def test_controller_config_rejects_inverted_backoff() -> None:
    with pytest.raises(ValueError, match="drift_recovery_initial_delay_seconds"):
        ControllerConfig(drift_recovery_initial_delay_seconds=60, drift_recovery_max_delay_seconds=5)


def test_controller_config_allows_zero_orphan_interval_to_disable() -> None:
    cfg = ControllerConfig(orphan_cleanup_interval_seconds=0)
    assert cfg.orphan_cleanup_interval_seconds == 0


def test_controller_config_allows_zero_starting_timeout_to_disable() -> None:
    cfg = ControllerConfig(starting_timeout_seconds=0)
    assert cfg.starting_timeout_seconds == 0


def test_runtime_compatible_executor_config_keeps_executors_for_docker_runtime() -> None:
    cfg = DeploymentsConfig(
        executors=[ExecutorConfigEntry(name="local-docker", backend="docker")],
        default_executor="local-docker",
    )

    with patch(
        "nemo_deployments_plugin.config.get_platform_config",
        return_value=SimpleNamespace(runtime=Runtime.DOCKER),
    ):
        executors, default_executor = runtime_compatible_executor_config(cfg)

    assert executors == cfg.executors
    assert default_executor == "local-docker"


def test_runtime_compatible_executor_config_drops_executors_for_none_runtime(caplog) -> None:
    cfg = DeploymentsConfig(
        executors=[ExecutorConfigEntry(name="local-docker", backend="docker")],
        default_executor="local-docker",
    )

    caplog.set_level(logging.WARNING)
    with patch(
        "nemo_deployments_plugin.config.get_platform_config",
        return_value=SimpleNamespace(runtime=Runtime.NONE),
    ):
        executors, default_executor = runtime_compatible_executor_config(cfg)

    assert executors == []
    assert default_executor is None
    assert "Skipping deployments executor 'local-docker'" in caplog.text
    assert "Ignoring deployments default_executor 'local-docker'" in caplog.text
