# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from unittest.mock import MagicMock

from nemo_platform.quickstart.cluster import QuickstartCluster
from nemo_platform.quickstart.config import QuickstartConfig
from nemo_platform.quickstart.platform_config import PlatformConfig


def test_start_generates_canonical_platform_config_when_missing(tmp_path: Path) -> None:
    config = QuickstartConfig(storage_path=tmp_path, platform_config_path=None)
    cluster = QuickstartCluster(config=config, platform_config=PlatformConfig(nvidia_api_key="nvapi-test"))
    cluster._preflight_checker.results = []
    cluster._preflight_checker.has_failures = MagicMock(return_value=False)
    cluster._preflight_checker.run_all = MagicMock(return_value=[])
    cluster._storage_manager.initialize = MagicMock()
    cluster._container_manager.start = MagicMock()

    cluster.start()

    assert config.platform_config_path == (tmp_path / "platform-config.yaml").resolve()
    assert config.platform_config_path.exists()
    cluster._container_manager.start.assert_called_once_with(platform_config=cluster.platform_config, pull=True)
