# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration and fixtures for Intake tests using MockEntityClient."""

import pytest
from fastapi.testclient import TestClient
from nmp.intake.api.v2.experiments.endpoints import get_experiment_rollup_repository
from nmp.intake.service import IntakeService
from nmp.testing import create_test_client


@pytest.fixture
def client():
    """Create test client with mocked entity client."""
    with create_test_client(
        IntakeService,
        client_type=TestClient,
        dependency_overrides={get_experiment_rollup_repository: lambda: None},
    ) as tc:
        yield tc
