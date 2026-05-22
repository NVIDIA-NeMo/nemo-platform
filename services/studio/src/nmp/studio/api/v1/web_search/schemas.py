# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Schemas for the Studio web-search endpoint."""

from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    """Request body for /v1/web-search."""

    query: str = Field(..., min_length=1, max_length=512, description="Search query.")
    max_results: int = Field(5, ge=1, le=10, description="Maximum number of results to return (1-10).")


class WebSearchResultItem(BaseModel):
    """One DuckDuckGo result."""

    title: str
    url: str
    snippet: str = ""


class WebSearchResponse(BaseModel):
    """Response body for /v1/web-search."""

    query: str
    results: list[WebSearchResultItem]
    note: str | None = Field(
        default=None,
        description="Optional note about result quality (e.g., zero results, fallback).",
    )
