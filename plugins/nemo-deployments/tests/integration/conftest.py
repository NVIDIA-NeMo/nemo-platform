# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test fixtures for docker-backed deployments."""

from __future__ import annotations

from docker_availability import DOCKER_AVAILABLE, skip_without_docker

__all__ = ["DOCKER_AVAILABLE", "skip_without_docker"]
