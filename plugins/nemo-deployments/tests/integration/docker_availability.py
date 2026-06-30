# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared Docker daemon availability check for integration tests."""

from __future__ import annotations

import pytest

try:
    import docker

    docker.from_env().ping()
    DOCKER_AVAILABLE: bool = True
except Exception:
    DOCKER_AVAILABLE = False

skip_without_docker: pytest.MarkDecorator = pytest.mark.skipif(
    not DOCKER_AVAILABLE, reason="Docker daemon not available"
)
