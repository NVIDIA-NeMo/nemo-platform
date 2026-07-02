# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_deployments_plugin.backends.docker.config import DockerExecutorConfig
from pydantic import ValidationError


def test_docker_executor_config_defaults() -> None:
    cfg = DockerExecutorConfig()
    assert cfg.port_range_start == 9000
    assert cfg.port_range_end == 9100


def test_docker_executor_config_rejects_inverted_port_range() -> None:
    with pytest.raises(ValidationError, match="port_range_start must not exceed port_range_end"):
        DockerExecutorConfig(port_range_start=9200, port_range_end=9100)
