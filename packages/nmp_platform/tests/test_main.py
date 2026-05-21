# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for platform main module."""

from typing import List

import pytest
from fastapi import APIRouter
from nmp.common.service import RouterConfig, Service
from nmp.platform.main import load_service


class MockService(Service):
    """Mock service for testing."""

    def __init__(self):
        super().__init__(name="mock", module_name="nmp.mock")

    def get_routers(self) -> List[RouterConfig]:
        return [RouterConfig(APIRouter(), tag="Mock", description="Mock")]


class TestLoadService:
    """Tests for load_service function."""

    def test_load_service_invalid_path_format(self):
        """Test load_service raises with invalid path format."""
        with pytest.raises(ValueError, match="must be in format"):
            load_service("test", "invalid_path")

    def test_load_service_module_not_found(self):
        """Test load_service raises ImportError for missing module."""
        with pytest.raises(ImportError):
            load_service("test", "nonexistent.module:service")

    def test_load_service_attribute_not_found(self):
        """Test load_service raises AttributeError for missing attribute."""
        with pytest.raises(AttributeError):
            load_service("test", "nmp.platform.main:nonexistent")

    def test_load_service_not_service_instance(self):
        """Test load_service raises TypeError for non-Service."""
        with pytest.raises(TypeError, match="must be an instance of Service"):
            load_service("test", "nmp.platform.main:logger")

    def test_load_service_success(self):
        """Test load_service successfully loads a service."""
        # Use the hello-world service for testing
        service = load_service("hello-world", "nmp.hello_world.main:service")

        assert isinstance(service, Service)
        assert service.name == "hello-world"


class TestStartupFailureExitCode:
    """Tests for deprecated service startup behavior."""

    def test_service_startup_exits_with_code_1_and_guidance(self, tmp_path):
        """Service startup should fail fast and direct callers to `nemo services run`."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "nmp.platform.main", "run", "--services", "files"],
            capture_output=True,
            timeout=30,
        )

        stderr = result.stderr.decode()
        assert result.returncode == 2
        assert "invalid choice" in stderr
        assert "choose from 'task'" in stderr or "choose from task" in stderr
