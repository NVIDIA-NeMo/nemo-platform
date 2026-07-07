# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the SPAStaticFiles handler."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.studio.static_files import DEFAULT_CSP, SPAStaticFiles


@pytest.fixture()
def static_dir(tmp_path: Path) -> Path:
    """Minimal static directory with index.html and an asset."""
    index = tmp_path / "index.html"
    index.write_text("<html><body>hello</body></html>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "main.js").write_text("console.log('hi')", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def client(static_dir: Path) -> TestClient:
    app = FastAPI()
    app.mount(
        "/studio",
        SPAStaticFiles(directory=str(static_dir), html=True, csp_header=DEFAULT_CSP),
        name="studio-static",
    )
    return TestClient(app, raise_server_exceptions=True)


class TestCSPHeader:
    """CSP must be present on every HTML response, with or without preprocessing."""

    def test_root_path_has_csp(self, client: TestClient):
        response = client.get("/studio/")
        assert response.status_code == 200
        assert "Content-Security-Policy" in response.headers

    def test_index_html_direct_has_csp(self, client: TestClient):
        response = client.get("/studio/index.html")
        assert response.status_code == 200
        assert "Content-Security-Policy" in response.headers

    def test_csp_value_matches_default(self, client: TestClient):
        response = client.get("/studio/")
        assert response.headers["Content-Security-Policy"] == DEFAULT_CSP

    def test_js_asset_has_no_csp(self, client: TestClient):
        response = client.get("/studio/assets/main.js")
        assert response.status_code == 200
        assert "Content-Security-Policy" not in response.headers

    def test_inline_importmap_hash_added_to_script_src(self, tmp_path: Path):
        """Inline <script type="importmap"> content must be authorized via sha256 in CSP."""
        import base64
        import hashlib

        importmap_content = '{"imports":{"react":"/vendor/react.js"}}'
        index = tmp_path / "index.html"
        index.write_text(
            f'<html><head><script type="importmap">{importmap_content}</script></head></html>',
            encoding="utf-8",
        )
        app = FastAPI()
        app.mount(
            "/studio",
            SPAStaticFiles(directory=str(tmp_path), html=True, csp_header=DEFAULT_CSP),
            name="studio-static",
        )
        c = TestClient(app)
        response = c.get("/studio/")
        csp = response.headers["Content-Security-Policy"]
        expected_hash = base64.b64encode(hashlib.sha256(importmap_content.encode()).digest()).decode()
        assert f"'sha256-{expected_hash}'" in csp
        assert "script-src 'self' 'sha256-" in csp

    def test_no_csp_when_disabled(self, static_dir: Path):
        app = FastAPI()
        app.mount(
            "/studio",
            SPAStaticFiles(directory=str(static_dir), html=True, csp_header=None),
            name="studio-static",
        )
        c = TestClient(app)
        response = c.get("/studio/")
        assert response.status_code == 200
        assert "Content-Security-Policy" not in response.headers


class TestHasFileExtension:
    """Tests for the _has_file_extension method."""

    def test_nested_path_with_extension(self):
        assert SPAStaticFiles._has_file_extension("assets/main.12345.js") is True

    def test_nested_path_without_extension(self):
        assert SPAStaticFiles._has_file_extension("workspaces/123/models") is False

    def test_path_with_trailing_slash(self):
        assert SPAStaticFiles._has_file_extension("dashboard/") is False

    def test_hidden_file_has_extension(self):
        # .gitignore should be considered as having an extension
        assert SPAStaticFiles._has_file_extension(".gitignore") is True

    def test_empty_path(self):
        assert SPAStaticFiles._has_file_extension("") is False

    def test_root_path(self):
        assert SPAStaticFiles._has_file_extension("/") is False
