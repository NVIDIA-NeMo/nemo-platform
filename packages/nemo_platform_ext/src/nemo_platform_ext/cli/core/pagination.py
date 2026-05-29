# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pagination utilities for the NeMo CLI."""

from __future__ import annotations

import logging
import typing
from enum import Enum
from typing import Any, Callable

from rich.progress import Progress, SpinnerColumn, TextColumn

from nemo_platform_ext.cli.core.help_formatter import add_warning

if typing.TYPE_CHECKING:
    from nemo_platform.pagination import SyncDefaultPagination, SyncLogsPagination

logger = logging.getLogger(__name__)


class PaginationType(str, Enum):
    """Types of pagination supported by the API."""

    PAGE_NUMBER = "page_number"  # Uses page/page_size params (default_pagination)
    CURSOR = "cursor"  # Uses limit/page_cursor params (logs_pagination)
    NOT_PAGINATED = "not_paginated"  # List operation without pagination support


class AllPagesResponse:
    """
    A response object that mimics a single-page response but contains all items.

    This ensures --all-pages returns the same structure as a single page response.
    Used for page-number based pagination which has total_pages and total_results.
    """

    def __init__(self, data: list[Any], total_items: int, total_pages: int, page_size: int | None = None):
        self.data = data
        self.sort = None

        # Create pagination info for all items
        self.pagination = type(
            "obj",
            (object,),
            {
                "page": 1,
                "page_size": page_size or len(data),
                "current_page_size": len(data),
                "total_pages": 1,  # All data is now in one "page"
                "total_results": total_items,
            },
        )()

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        """Make this compatible with Pydantic's model_dump."""
        # Convert data items to dicts if they're Pydantic models
        serialized_data = []
        for item in self.data:
            if hasattr(item, "model_dump"):
                serialized_data.append(item.model_dump(mode=mode))
            elif isinstance(item, dict):
                serialized_data.append(item)
            else:
                serialized_data.append(item)

        return {
            "data": serialized_data,
            "sort": self.sort,
            "pagination": {
                "page": self.pagination.page,
                "page_size": self.pagination.page_size,
                "current_page_size": self.pagination.current_page_size,
                "total_pages": self.pagination.total_pages,
                "total_results": self.pagination.total_results,
            },
        }


class AllCursorPagesResponse:
    """
    A response object for cursor-based pagination results.

    Cursor-based pagination doesn't have total_pages or total_results,
    so this response only contains the collected data and item count.
    """

    def __init__(self, data: list[Any], limit: int | None = None):
        self.data = data
        self.next_page = None  # All pages fetched, no next page

        # Store the original limit for reference
        self._limit = limit

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        """Make this compatible with Pydantic's model_dump."""
        # Convert data items to dicts if they're Pydantic models
        serialized_data = []
        for item in self.data:
            if hasattr(item, "model_dump"):
                serialized_data.append(item.model_dump(mode=mode))
            elif isinstance(item, dict):
                serialized_data.append(item)
            else:
                serialized_data.append(item)

        return {
            "data": serialized_data,
            "next_page": self.next_page,
        }


def _fetch_all_pages_page_number(
    list_method: Callable[..., SyncDefaultPagination[Any]],
    progress: Progress,
    task: Any,
    path_args: tuple[Any, ...],
    body_args: dict[str, Any],
) -> AllPagesResponse:
    """
    Fetch all pages using page-number based pagination.

    This is used for endpoints with `default_pagination` in the stainless config.
    """
    all_items: list[Any] = []
    total_pages_count = 0
    total_results = 0
    original_page_size = None

    # Fetch the first page
    try:
        response = list_method(*path_args, **body_args)
    except Exception as e:
        progress.stop()
        raise e

    if (total_pages := response.pagination.total_pages) is not None:
        progress.update(task, total=total_pages)
        total_pages_count = total_pages

    # TODO: quiet logging context manager
    logging.getLogger().setLevel(logging.CRITICAL)
    for page in response.iter_pages():
        page_num = page.pagination.page

        for item in page.data:
            all_items.append(item)

        progress.update(
            task, completed=page_num, description=f"Fetching pages... (page {page_num + 1}/{total_pages_count})"
        )

    return AllPagesResponse(
        data=all_items,
        total_items=total_results or len(all_items),
        total_pages=total_pages_count,
        page_size=original_page_size,
    )


def _fetch_all_pages_cursor(
    list_method: Callable[..., SyncLogsPagination],
    progress: Progress,
    task: Any,
    path_args: tuple[Any, ...],
    body_args: dict[str, Any],
) -> AllCursorPagesResponse:
    """
    Fetch all pages using cursor-based pagination.

    This is used for endpoints with `logs_pagination` in the stainless config.
    """
    all_items: list[Any] = []
    page_num = 1

    # Fetch the first page
    try:
        response = list_method(*path_args, **body_args)
    except Exception as e:
        progress.stop()
        raise e

    # TODO: quiet logging context manager
    logging.getLogger().setLevel(logging.CRITICAL)
    for page in response.iter_pages():
        page_num += 1

        for item in page.data:
            all_items.append(item)

        progress.update(task, completed=page_num, description=f"Fetching pages... (page {page_num + 1})")

    return AllCursorPagesResponse(
        data=all_items,
        limit=body_args.get("limit", None),
    )


def fetch_all_pages(
    list_method: Callable[..., Any],
    path_args: tuple[Any, ...] = (),
    body_args: dict[str, Any] | None = None,
    show_progress: bool = True,
    pagination_type: PaginationType = PaginationType.PAGE_NUMBER,
) -> AllPagesResponse | AllCursorPagesResponse:
    """
    Fetch all pages from a paginated endpoint.

    Args:
        list_method: The SDK list method to call (e.g., client.namespaces.list)
        path_args: Positional arguments to pass to the list method (e.g., job_id)
        body_args: Keyword arguments to pass to the list method (e.g., filter, search)
        show_progress: Whether to show a progress indicator
        pagination_type: Type of pagination - PAGE_NUMBER (default) or CURSOR

    Returns:
        AllPagesResponse for page-number pagination, AllCursorPagesResponse for cursor pagination
    """
    if body_args is None:
        body_args = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        disable=not show_progress,
    ) as progress:
        task = progress.add_task("Fetching pages...", total=None)

        if pagination_type == PaginationType.CURSOR:
            return _fetch_all_pages_cursor(list_method, progress, task, path_args, body_args)
        else:
            return _fetch_all_pages_page_number(list_method, progress, task, path_args, body_args)


def warn_if_more_pages(
    response: Any,
    pagination_type: PaginationType,
) -> None:
    """
    Warn the user if there are more pages available.

    Args:
        response: The response object from the list method
        pagination_type: Type of pagination - PAGE_NUMBER (default) or CURSOR
    """
    if pagination_type == PaginationType.NOT_PAGINATED:
        return  # No pagination, no warning needed
    elif pagination_type == PaginationType.CURSOR:
        if getattr(response, "next_page", None):
            add_warning("More pages of results are available! Use --all-pages to fetch all results.")
    elif hasattr(response, "pagination") and getattr(response.pagination, "total_pages", 1) > 1:
        add_warning("More pages of results are available! Use --all-pages to fetch all results.")
