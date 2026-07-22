# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for pagination utilities."""

import logging
from unittest.mock import Mock

import pytest
from nemo_platform.cli.core.pagination import (
    AllCursorPagesResponse,
    AllPagesResponse,
    PaginationType,
    _fetch_all_pages_cursor,
    _fetch_all_pages_page_number,
    fetch_all_pages,
)

# =============================================================================
# Helper to create mock SDK pagination response
# =============================================================================


def create_mock_page_response(data: list, page: int, total_pages: int, page_size: int = 10):
    """Create a mock SDK pagination response that supports iter_pages()."""
    mock_response = Mock()
    mock_response.data = data
    mock_response.pagination = Mock()
    mock_response.pagination.page = page
    mock_response.pagination.total_pages = total_pages
    mock_response.pagination.page_size = page_size
    mock_response.pagination.current_page_size = len(data)
    mock_response.pagination.total_results = total_pages * page_size  # approximate
    return mock_response


def create_mock_cursor_response(data: list, next_page: str | None = None):
    """Create a mock SDK cursor pagination response that supports iter_pages()."""
    mock_response = Mock()
    mock_response.data = data
    mock_response.next_page = next_page
    return mock_response


# =============================================================================
# AllPagesResponse Tests
# =============================================================================


def test_all_pages_response_model_dump():
    """Test AllPagesResponse.model_dump() serialization."""
    # Create a mock pydantic model
    mock_item = Mock()
    mock_item.model_dump = Mock(return_value={"id": 1, "name": "test"})

    response = AllPagesResponse(
        data=[mock_item, {"id": 2}],
        total_items=2,
        total_pages=1,
        page_size=10,
    )

    result = response.model_dump()

    assert result["data"][0] == {"id": 1, "name": "test"}
    assert result["data"][1] == {"id": 2}
    assert result["pagination"]["total_results"] == 2
    assert result["pagination"]["page_size"] == 10


def test_all_pages_response_defaults():
    """Test AllPagesResponse with default values."""
    response = AllPagesResponse(
        data=[{"id": 1}, {"id": 2}],
        total_items=2,
        total_pages=1,
    )

    assert response.sort is None
    assert response.pagination.page == 1
    assert response.pagination.total_pages == 1
    assert response.pagination.current_page_size == 2


# =============================================================================
# AllCursorPagesResponse Tests
# =============================================================================


def test_all_cursor_pages_response_model_dump():
    """Test AllCursorPagesResponse.model_dump() serialization."""
    mock_item = Mock()
    mock_item.model_dump = Mock(return_value={"log": "line1"})

    response = AllCursorPagesResponse(
        data=[mock_item, {"log": "line2"}],
        limit=100,
    )

    result = response.model_dump()

    assert result["data"][0] == {"log": "line1"}
    assert result["data"][1] == {"log": "line2"}
    assert result["next_page"] is None


def test_all_cursor_pages_response_defaults():
    """Test AllCursorPagesResponse with default values."""
    response = AllCursorPagesResponse(
        data=[{"log": "line1"}],
    )

    assert response.next_page is None
    assert response._limit is None


# =============================================================================
# PaginationType Enum Tests
# =============================================================================


def test_pagination_type_values():
    """Test PaginationType enum values."""
    assert PaginationType.PAGE_NUMBER.value == "page_number"
    assert PaginationType.CURSOR.value == "cursor"


def test_pagination_type_is_string():
    """Test that PaginationType can be used as a string."""
    assert str(PaginationType.PAGE_NUMBER) == "PaginationType.PAGE_NUMBER"
    # Can compare with string value
    assert PaginationType.PAGE_NUMBER == "page_number"
    assert PaginationType.CURSOR == "cursor"


# =============================================================================
# fetch_all_pages Tests (using SDK's iter_pages)
# =============================================================================


def test_fetch_all_pages_page_number_single_page():
    """Test fetch_all_pages with page-number pagination (single page)."""
    # Create mock response with iter_pages that yields just itself
    page1 = create_mock_page_response([{"id": 1}, {"id": 2}], page=1, total_pages=1)
    page1.iter_pages = Mock(return_value=iter([page1]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(mock_list, show_progress=False)

    assert isinstance(result, AllPagesResponse)
    assert len(result.data) == 2
    assert result.data[0] == {"id": 1}
    assert result.data[1] == {"id": 2}
    mock_list.assert_called_once()


def test_fetch_all_pages_page_number_multiple_pages():
    """Test fetch_all_pages with page-number pagination (multiple pages)."""
    page1 = create_mock_page_response([{"id": 1}, {"id": 2}], page=1, total_pages=3)
    page2 = create_mock_page_response([{"id": 3}, {"id": 4}], page=2, total_pages=3)
    page3 = create_mock_page_response([{"id": 5}], page=3, total_pages=3)

    # iter_pages yields all pages including the first
    page1.iter_pages = Mock(return_value=iter([page1, page2, page3]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(mock_list, show_progress=False)

    assert isinstance(result, AllPagesResponse)
    assert len(result.data) == 5
    assert result.data[0] == {"id": 1}
    assert result.data[4] == {"id": 5}


def test_fetch_all_pages_cursor_single_page():
    """Test fetch_all_pages with cursor pagination (single page)."""
    page1 = create_mock_cursor_response([{"log": "line1"}, {"log": "line2"}], next_page=None)
    page1.iter_pages = Mock(return_value=iter([page1]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(
        mock_list,
        show_progress=False,
        pagination_type=PaginationType.CURSOR,
    )

    assert isinstance(result, AllCursorPagesResponse)
    assert len(result.data) == 2
    assert result.data[0] == {"log": "line1"}
    assert result.next_page is None


def test_fetch_all_pages_cursor_multiple_pages():
    """Test fetch_all_pages with cursor pagination (multiple pages)."""
    page1 = create_mock_cursor_response([{"log": "line1"}], next_page="cursor_1")
    page2 = create_mock_cursor_response([{"log": "line2"}], next_page="cursor_2")
    page3 = create_mock_cursor_response([{"log": "line3"}], next_page=None)

    page1.iter_pages = Mock(return_value=iter([page1, page2, page3]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(
        mock_list,
        show_progress=False,
        pagination_type=PaginationType.CURSOR,
    )

    assert isinstance(result, AllCursorPagesResponse)
    assert len(result.data) == 3


def test_page_number_progress_reports_current_page():
    page1 = create_mock_page_response([{"id": 1}], page=1, total_pages=2)
    page2 = create_mock_page_response([{"id": 2}], page=2, total_pages=2)
    page1.iter_pages = Mock(return_value=iter([page1, page2]))
    progress = Mock()

    _fetch_all_pages_page_number(Mock(return_value=page1), progress, "task", (), {})

    assert progress.update.call_args_list[-2].kwargs["description"] == "Fetching pages... (page 1/2)"
    assert progress.update.call_args_list[-1].kwargs["description"] == "Fetching pages... (page 2/2)"


def test_cursor_progress_reports_current_page():
    page1 = create_mock_cursor_response([{"id": 1}], next_page="next")
    page2 = create_mock_cursor_response([{"id": 2}], next_page=None)
    page1.iter_pages = Mock(return_value=iter([page1, page2]))
    progress = Mock()

    _fetch_all_pages_cursor(Mock(return_value=page1), progress, "task", (), {})

    assert progress.update.call_args_list[-2].kwargs["description"] == "Fetching pages... (page 1)"
    assert progress.update.call_args_list[-1].kwargs["description"] == "Fetching pages... (page 2)"


def test_fetch_all_pages_with_path_args():
    """Test fetch_all_pages passes path_args correctly."""
    page1 = create_mock_page_response([{"id": 1}], page=1, total_pages=1)
    page1.iter_pages = Mock(return_value=iter([page1]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(
        mock_list,
        path_args=("job_123",),
        show_progress=False,
    )

    assert isinstance(result, AllPagesResponse)
    mock_list.assert_called_once_with("job_123")


def test_fetch_all_pages_with_body_args():
    """Test fetch_all_pages passes body_args correctly."""
    page1 = create_mock_page_response([{"id": 1}], page=1, total_pages=1)
    page1.iter_pages = Mock(return_value=iter([page1]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(
        mock_list,
        body_args={"filter": {"namespace": "test"}, "page_size": 20},
        show_progress=False,
    )

    assert isinstance(result, AllPagesResponse)
    mock_list.assert_called_once_with(filter={"namespace": "test"}, page_size=20)


def test_fetch_all_pages_with_path_and_body_args():
    """Test fetch_all_pages with both path and body arguments."""
    page1 = create_mock_cursor_response([{"log": "line1"}], next_page=None)
    page1.iter_pages = Mock(return_value=iter([page1]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(
        mock_list,
        path_args=("job_123",),
        body_args={"limit": 100},
        show_progress=False,
        pagination_type=PaginationType.CURSOR,
    )

    assert isinstance(result, AllCursorPagesResponse)
    mock_list.assert_called_once_with("job_123", limit=100)


def test_fetch_all_pages_cursor_preserves_limit():
    """Test that cursor pagination preserves the limit in response."""
    page1 = create_mock_cursor_response([{"log": "line1"}], next_page=None)
    page1.iter_pages = Mock(return_value=iter([page1]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(
        mock_list,
        body_args={"limit": 50},
        show_progress=False,
        pagination_type=PaginationType.CURSOR,
    )

    assert isinstance(result, AllCursorPagesResponse)
    assert result._limit == 50


def test_fetch_all_pages_empty_response():
    """Test fetch_all_pages with empty response."""
    page1 = create_mock_page_response([], page=1, total_pages=1)
    page1.iter_pages = Mock(return_value=iter([page1]))

    mock_list = Mock(return_value=page1)

    result = fetch_all_pages(mock_list, show_progress=False)

    assert isinstance(result, AllPagesResponse)
    assert len(result.data) == 0


def test_fetch_all_pages_restores_root_logging_level():
    """Fetching all pages must not permanently mutate process-wide logging."""
    page1 = create_mock_page_response([{"id": 1}], page=1, total_pages=1)
    page1.iter_pages = Mock(return_value=iter([page1]))
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.WARNING)

    try:
        fetch_all_pages(Mock(return_value=page1), show_progress=False)
        assert root_logger.level == logging.WARNING
    finally:
        root_logger.setLevel(previous_level)


def test_fetch_all_pages_restores_root_logging_level_after_iteration_error():
    """Logging is restored even when the SDK page iterator fails."""
    page1 = create_mock_page_response([{"id": 1}], page=1, total_pages=2)

    def broken_pages():
        yield page1
        raise RuntimeError("page fetch failed")

    page1.iter_pages = broken_pages
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.WARNING)

    try:
        with pytest.raises(RuntimeError, match="page fetch failed"):
            fetch_all_pages(Mock(return_value=page1), show_progress=False)
        assert root_logger.level == logging.WARNING
    finally:
        root_logger.setLevel(previous_level)
