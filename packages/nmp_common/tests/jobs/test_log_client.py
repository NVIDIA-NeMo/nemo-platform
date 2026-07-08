# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for JobLogsClient SDK wrapper and PageCursor."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nemo_platform_plugin.client.errors import NotFoundError
from nmp.common.jobs.log_client import JobLogsClient
from nmp.common.jobs.schemas import (
    PageCursor,
    PaginationDirection,
    PlatformJobLogPage,
)

# =============================================================================
# PageCursor Tests
# =============================================================================


def test_encode_decode_forward():
    """Test encoding and decoding a forward pagination cursor."""
    cursor = PageCursor(start_id=5, direction=PaginationDirection.FORWARD)
    encoded = cursor.encode()
    decoded = PageCursor.decode(encoded)

    assert decoded.start_id == 5
    assert decoded.direction == PaginationDirection.FORWARD


def test_encode_decode_backward():
    """Test encoding and decoding a backward pagination cursor."""
    cursor = PageCursor(start_id=3, direction=PaginationDirection.BACKWARD)
    encoded = cursor.encode()
    decoded = PageCursor.decode(encoded)

    assert decoded.start_id == 3
    assert decoded.direction == PaginationDirection.BACKWARD


def test_decode_invalid_cursor():
    """Test decoding an invalid cursor raises ValueError."""
    with pytest.raises(ValueError, match="Invalid page cursor"):
        PageCursor.decode("invalid_cursor_string")


# =============================================================================
# JobLogsClient Tests
# =============================================================================


def _make_response_mock(log_page: PlatformJobLogPage) -> MagicMock:
    mock = MagicMock()
    mock.data.return_value = log_page
    return mock


@pytest.fixture
def mock_files_client():
    """Create a mock AsyncFilesClient for testing."""
    client = AsyncMock()
    return client


@pytest.fixture
def log_client(mock_files_client):
    """Create a JobLogsClient with a mock files client."""
    with patch("nmp.common.jobs.log_client.client_from_platform", return_value=mock_files_client):
        client = JobLogsClient(sdk=MagicMock())
    return client, mock_files_client


async def test_query_logs_success(log_client):
    """Test successful log query via FilesClient."""
    client, mock_files = log_client

    page = PlatformJobLogPage(
        data=[
            {
                "timestamp": "2024-01-01T12:00:00",
                "job": "job-123",
                "job_step": "step1",
                "job_task": "task1",
                "message": "Test log message",
            }
        ],
        total=1,
        next_page=None,
        prev_page=None,
    )
    mock_files.query_otlp_logs.return_value = _make_response_mock(page)

    result = await client.query_logs(
        fileset="logs",
        workspace="test-workspace",
        filters={"job": "job-123"},
        page_size=100,
    )

    assert isinstance(result, PlatformJobLogPage)
    assert len(result.data) == 1
    assert result.total == 1

    mock_files.query_otlp_logs.assert_called_once()
    call_kwargs = mock_files.query_otlp_logs.call_args.kwargs
    assert call_kwargs["name"] == "logs"
    assert call_kwargs["workspace"] == "test-workspace"


async def test_query_logs_with_pagination_cursor(log_client):
    """Test query_logs passes pagination cursor correctly."""
    client, mock_files = log_client

    mock_files.query_otlp_logs.return_value = _make_response_mock(
        PlatformJobLogPage(data=[], total=0, next_page=None, prev_page=None)
    )

    cursor = PageCursor(start_id=2, direction=PaginationDirection.FORWARD).encode()

    await client.query_logs(
        fileset="logs",
        workspace="test-workspace",
        page_cursor=cursor,
    )

    call_kwargs = mock_files.query_otlp_logs.call_args.kwargs
    assert call_kwargs["body"].page_cursor == cursor


async def test_query_logs_404_returns_empty_page(log_client):
    """Test that NotFoundError returns an empty page."""
    client, mock_files = log_client

    mock_files.query_otlp_logs.side_effect = NotFoundError(
        httpx.Response(status_code=404),
    )

    result = await client.query_logs(
        fileset="logs",
        workspace="test-workspace",
    )

    assert result.data == []
    assert result.total == 0
    assert result.next_page is None
    assert result.prev_page is None


async def test_query_logs_other_error_raises(log_client):
    """Test that other errors are raised to the caller."""
    client, mock_files = log_client

    mock_files.query_otlp_logs.side_effect = RuntimeError("Unexpected error")

    with pytest.raises(RuntimeError, match="Unexpected error"):
        await client.query_logs(
            fileset="logs",
            workspace="test-workspace",
        )


async def test_query_logs_empty_filters(log_client):
    """Test query_logs with no filters."""
    client, mock_files = log_client

    mock_files.query_otlp_logs.return_value = _make_response_mock(
        PlatformJobLogPage(data=[], total=0, next_page=None, prev_page=None)
    )

    await client.query_logs(
        fileset="logs",
        workspace="test-workspace",
        filters=None,
    )

    call_kwargs = mock_files.query_otlp_logs.call_args.kwargs
    assert call_kwargs["body"].filters == {}


def test_sdk_created_in_constructor():
    """Test that SDK is set in constructor."""
    sdk = MagicMock()
    with patch("nmp.common.jobs.log_client.client_from_platform") as mock_adapter:
        client = JobLogsClient(sdk=sdk)
    assert client._sdk is sdk
    mock_adapter.assert_called_once()
