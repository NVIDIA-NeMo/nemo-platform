# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the DuckDuckGo HTML parser used by /v1/web-search."""

from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.studio.api.v1.web_search.endpoints import (
    _decode_ddg_redirect,
    parse_duckduckgo_html,
    router,
)


def _ddg_redirect(target: str) -> str:
    return f"//duckduckgo.com/l/?uddg={quote(target, safe='')}"


def _make_html(items: list[tuple[str, str, str]]) -> str:
    """Build a minimal DDG-shaped HTML page from (title, url, snippet) tuples."""
    results_html = "".join(
        f"""
        <div class="result results_links results_links_deep web-result">
          <h2 class="result__title">
            <a class="result__a" href="{_ddg_redirect(url)}">{title}</a>
          </h2>
          <a class="result__snippet" href="{_ddg_redirect(url)}">{snippet}</a>
        </div>
        """
        for title, url, snippet in items
    )
    return f"<html><body><div class='results'>{results_html}</div></body></html>"


class TestParseDuckduckgoHtml:
    def test_extracts_title_url_and_snippet_from_results(self) -> None:
        html = _make_html(
            [
                ("NVIDIA Datacenter GPUs", "https://www.nvidia.com/data-center/", "GPU lineup overview."),
                ("Compare H100 vs H200", "https://example.com/h100-h200", "Spec comparison."),
            ]
        )

        items = parse_duckduckgo_html(html, max_results=5)

        assert [i.title for i in items] == ["NVIDIA Datacenter GPUs", "Compare H100 vs H200"]
        assert [i.url for i in items] == [
            "https://www.nvidia.com/data-center/",
            "https://example.com/h100-h200",
        ]
        assert items[0].snippet == "GPU lineup overview."

    def test_respects_max_results(self) -> None:
        html = _make_html([(f"Title {i}", f"https://example.com/{i}", "x") for i in range(10)])

        items = parse_duckduckgo_html(html, max_results=3)

        assert len(items) == 3
        assert [i.title for i in items] == ["Title 0", "Title 1", "Title 2"]

    def test_returns_empty_for_results_with_no_anchor(self) -> None:
        html = "<html><body><div class='result'><span>no anchor</span></div></body></html>"

        assert parse_duckduckgo_html(html, max_results=5) == []

    def test_returns_empty_for_garbage_html(self) -> None:
        assert parse_duckduckgo_html("<not-real-html>", max_results=5) == []


class TestDecodeDdgRedirect:
    def test_unwraps_redirect_url(self) -> None:
        href = _ddg_redirect("https://example.com/page?q=1")
        assert _decode_ddg_redirect(href) == "https://example.com/page?q=1"

    def test_passes_through_direct_url(self) -> None:
        assert _decode_ddg_redirect("https://example.com/direct") == "https://example.com/direct"

    def test_empty_href_returns_empty(self) -> None:
        assert _decode_ddg_redirect("") == ""


class TestWebSearchEndpoint:
    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        """A FastAPI TestClient with the web_search router mounted at /v1."""
        app = FastAPI()
        app.include_router(router, prefix="/v1")
        return TestClient(app)

    def test_returns_parsed_results(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        sample_html = _make_html(
            [
                ("Result A", "https://a.example", "snippet a"),
                ("Result B", "https://b.example", "snippet b"),
            ]
        )

        async def fake_fetch(query: str, client: httpx.AsyncClient) -> str:
            assert query == "nemo platform"
            return sample_html

        monkeypatch.setattr("nmp.studio.api.v1.web_search.endpoints._fetch_duckduckgo_html", fake_fetch)

        response = client.post("/v1/web-search", json={"query": "nemo platform", "max_results": 2})

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "nemo platform"
        assert [r["title"] for r in body["results"]] == ["Result A", "Result B"]
        assert body["note"] is None

    def test_rejects_empty_query(self, client: TestClient) -> None:
        response = client.post("/v1/web-search", json={"query": "", "max_results": 5})
        # Pydantic schema validation rejects min_length=1 before the handler runs.
        assert response.status_code == 422

    def test_maps_upstream_5xx_to_bad_gateway(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_fetch(query: str, client: httpx.AsyncClient) -> str:
            request = httpx.Request("POST", "https://html.duckduckgo.com/html/")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("upstream error", request=request, response=response)

        monkeypatch.setattr("nmp.studio.api.v1.web_search.endpoints._fetch_duckduckgo_html", fake_fetch)

        response = client.post("/v1/web-search", json={"query": "x", "max_results": 1})
        assert response.status_code == 502

    def test_maps_network_error_to_gateway_timeout(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_fetch(query: str, client: httpx.AsyncClient) -> str:
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr("nmp.studio.api.v1.web_search.endpoints._fetch_duckduckgo_html", fake_fetch)

        response = client.post("/v1/web-search", json={"query": "x", "max_results": 1})
        assert response.status_code == 504

    def test_sets_note_when_zero_results(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_fetch(query: str, client: httpx.AsyncClient) -> str:
            return "<html><body><p>no results here</p></body></html>"

        monkeypatch.setattr("nmp.studio.api.v1.web_search.endpoints._fetch_duckduckgo_html", fake_fetch)

        response = client.post("/v1/web-search", json={"query": "x", "max_results": 5})
        assert response.status_code == 200
        body = response.json()
        assert body["results"] == []
        assert "no parseable items" in (body["note"] or "")
