# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DuckDuckGo-backed web-search endpoint for Studio.

Calls the static `html.duckduckgo.com/html/` endpoint and parses results from the
returned HTML. No JavaScript, no headless browser, no LLM round-trip. If DDG ever
starts soft-blocking this endpoint, swap `_search_duckduckgo` for a Playwright-backed
implementation; the request/response contract stays identical.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, status
from nmp.studio.api.v1.web_search.schemas import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResultItem,
)

logger = logging.getLogger(__name__)

router = APIRouter()

API_TAG = "Web Search"

_DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_REQUEST_TIMEOUT_SECONDS = 10.0


def _decode_ddg_redirect(href: str) -> str:
    """DDG result links go through `/l/?uddg=<encoded>`. Unwrap to the real URL.

    Returns the original href unchanged if it doesn't look like a DDG redirect.
    """
    if not href:
        return href
    if href.startswith("//"):
        href = f"https:{href}"
    try:
        parsed = urlparse(href)
    except ValueError:
        return href
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            return unquote(target)
    return href


def parse_duckduckgo_html(html: str, max_results: int) -> list[WebSearchResultItem]:
    """Parse the DDG HTML results page into structured items.

    Pure function — kept separate from the endpoint so it can be unit-tested
    against fixtures without going over the network.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[WebSearchResultItem] = []
    for result in soup.select("div.result"):
        title_anchor = result.select_one("a.result__a")
        if title_anchor is None:
            continue
        title = title_anchor.get_text(" ", strip=True)
        raw_href = title_anchor.get("href", "")
        href = raw_href if isinstance(raw_href, str) else ""
        url = _decode_ddg_redirect(href)
        if not url:
            continue
        snippet_node = result.select_one(".result__snippet")
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        items.append(WebSearchResultItem(title=title, url=url, snippet=snippet))
        if len(items) >= max_results:
            break
    return items


async def _fetch_duckduckgo_html(query: str, client: httpx.AsyncClient) -> str:
    response = await client.post(
        _DDG_HTML_ENDPOINT,
        data={"q": query, "kl": "us-en"},
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=_REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


@router.post(
    "/web-search",
    response_model=WebSearchResponse,
    tags=[API_TAG],
    summary="Search the web via DuckDuckGo",
    description=(
        "Runs a query against the DuckDuckGo static HTML endpoint and returns a list "
        "of structured result objects (title, url, snippet). Used by the AssistantChat "
        "`web_search` tool when a model emits a search tool call."
    ),
)
async def web_search(payload: WebSearchRequest) -> WebSearchResponse:
    """Run a DuckDuckGo search and return structured results."""
    query = payload.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`query` must be non-empty.",
        )

    try:
        async with httpx.AsyncClient() as client:
            html = await _fetch_duckduckgo_html(query, client)
    except httpx.HTTPStatusError as exc:
        logger.warning("DuckDuckGo returned %s for query %r", exc.response.status_code, query)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DuckDuckGo returned status {exc.response.status_code}.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("DuckDuckGo request failed for query %r: %s", query, exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream search request failed.",
        ) from exc

    results = parse_duckduckgo_html(html, payload.max_results)
    note: str | None = None
    if not results:
        note = "DuckDuckGo returned a results page but no parseable items were found. The HTML layout may have changed."
    return WebSearchResponse(query=query, results=results, note=note)
