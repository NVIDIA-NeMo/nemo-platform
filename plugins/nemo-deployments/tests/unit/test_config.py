# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_deployments_plugin.config import DeploymentsConfig


def test_config_rejects_inverted_port_range() -> None:
    with pytest.raises(ValueError, match="port_range_end"):
        DeploymentsConfig.model_validate({"port_range_start": 9100, "port_range_end": 9000})
