# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_deployments_plugin.config import ControllerConfig, DeploymentsConfig


def test_controller_config_defaults() -> None:
    cfg = DeploymentsConfig()
    assert cfg.controller.interval_seconds == 5
    assert cfg.controller.drift_recovery_max_attempts == 5
    assert cfg.controller.orphan_cleanup_interval_seconds == 30


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
