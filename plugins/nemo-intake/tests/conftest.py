# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration and fixtures for Intake tests using MockEntityClient."""

import pytest
from fastapi.testclient import TestClient
from nemo_intake_plugin.api.v2.experiments.endpoints import get_experiment_rollup_repository
from nemo_intake_plugin.service import IntakeService
from nmp.common.service import Service
from nmp.platform_runner.plugin_adapter import NemoServiceAdapter
from nmp.testing import create_test_client


class _IntakeTestService(NemoServiceAdapter):
    def __init__(self) -> None:
        super().__init__(IntakeService())


@pytest.fixture(scope="session")
def intake_service_factory() -> type[Service]:
    """Create Intake through the same adapter used by plugin discovery."""

    return _IntakeTestService


@pytest.fixture
def client(intake_service_factory: type[Service]):
    """Create test client with mocked entity client."""
    with create_test_client(
        intake_service_factory,
        client_type=TestClient,
        dependency_overrides={get_experiment_rollup_repository: lambda: None},
    ) as tc:
        yield tc
