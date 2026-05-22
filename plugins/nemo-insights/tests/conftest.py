# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared test fixtures: a FastAPI app wired to a mock NemoEntitiesClient.

Test helpers (``stamp``, ``list_response``) live in ``tests/_helpers.py`` —
keeping them out of conftest avoids the ``tests.conftest`` import-path problem
(pytest auto-loads conftest fixtures but does not make the module importable
as ``tests.conftest`` without an __init__).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_insights_plugin.service import InsightsPluginService
from nemo_platform_plugin.entity_client import get_entity_client


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def app(mock_entity_client: AsyncMock) -> FastAPI:
    service = InsightsPluginService()
    fastapi_app = FastAPI()
    for spec in service.get_routers():
        fastapi_app.include_router(spec.router, prefix=spec.prefix)
    fastapi_app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return fastapi_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
