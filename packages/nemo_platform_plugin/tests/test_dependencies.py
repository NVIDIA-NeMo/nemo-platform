# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for plugin-owned FastAPI dependency placeholders."""

import pytest
from nemo_platform_plugin.dependencies import get_effective_principal_id, get_nemo_client


def test_get_nemo_client_requires_platform_override() -> None:
    with pytest.raises(RuntimeError, match=r"get_nemo_client\(\) is not wired by platform services"):
        get_nemo_client()


def test_get_effective_principal_id_requires_platform_override() -> None:
    with pytest.raises(RuntimeError, match=r"get_effective_principal_id\(\) was called without being overridden"):
        get_effective_principal_id()
