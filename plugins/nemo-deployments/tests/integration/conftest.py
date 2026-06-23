# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test fixtures for docker-backed deployments."""

from __future__ import annotations

import pytest

try:
    import docker

    docker.from_env().ping()
    DOCKER_AVAILABLE = True
except Exception:
    DOCKER_AVAILABLE = False

skip_without_docker = pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker daemon not available")
