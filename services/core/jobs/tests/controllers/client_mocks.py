# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Builders for mock typed-client responses used by controller tests.

The Jobs controllers call the typed ``JobsClient`` and chain ``.data()`` (single
resource) or ``.items()`` (paginated). These helpers wrap plain values in mock
responses that mimic ``NemoResponse`` / ``NemoPaginatedResponse`` so tests can set
``mock_jobs_client.<method>.return_value`` without threading the client's real
response objects through.
"""

from typing import Any
from unittest.mock import MagicMock


def data_response(value: Any) -> MagicMock:
    """Build a mock typed-client response whose ``.data()`` returns ``value``."""
    resp = MagicMock()
    resp.data.return_value = value
    return resp


def paginated_response(items: Any) -> MagicMock:
    """Build a mock paginated response: ``.items()`` iterates, ``.data()`` returns the list."""
    resp = MagicMock()
    materialized = list(items)
    resp.items.return_value = iter(materialized)
    resp.data.return_value = materialized
    return resp
