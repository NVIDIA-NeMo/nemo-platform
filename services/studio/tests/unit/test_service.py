# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the StudioService."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.studio.config import StudioConfig
from nmp.studio.service import StudioService


class FakeTelemetryResponse:
    """Minimal upstream response used by telemetry proxy tests."""

    def __init__(self, status_code: int = 200, content: bytes = b"{}", headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "application/json"}


class FakeTelemetryClient:
    """Minimal async HTTP client used by telemetry proxy tests."""

    def __init__(self, response: FakeTelemetryResponse | None = None):
        self.response = response or FakeTelemetryResponse()
        self.calls: list[dict] = []

    async def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class TestStudioService:
    """Tests for the StudioService class."""

    def test_service_name(self):
        """Test that the service has the correct name."""
        service = StudioService()
        assert service.name == "studio"

    def test_service_title(self):
        """Test that the service has the correct title."""
        service = StudioService()
        assert service.title == "NeMo Studio UI"

    def test_service_description(self):
        """Test that the service has the correct description."""
        service = StudioService()
        assert service.description == "Serves the NeMo Studio web application and local coding-agent bridge"

    def test_get_routers_returns_coding_agent_router(self):
        """Test that the service exposes the local coding-agent API router."""
        service = StudioService()
        routers = service.get_routers()
        assert len(routers) == 1
        assert routers[0].tag == "Studio Coding Agents"

    def test_module_name(self):
        """Test that the service has the correct module name."""
        service = StudioService()
        assert service.module_name == "nmp.studio"


class TestTelemetryProxy:
    """Tests for the Studio OTLP/HTTP telemetry proxy."""

    def _client(
        self,
        config: StudioConfig,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeTelemetryClient | None = None,
    ) -> tuple[TestClient, FakeTelemetryClient]:
        app = FastAPI()
        telemetry_client = fake_client or FakeTelemetryClient()
        monkeypatch.setattr("nmp.studio.service.shared_async_http_client", lambda: telemetry_client)
        StudioService().with_config(config).configure_app(app)
        return TestClient(app), telemetry_client

    def test_post_strips_studio_telemetry_prefix_and_proxies_request(self, monkeypatch: pytest.MonkeyPatch):
        """Test that /studio/telemetry/* proxies to the collector without the route prefix."""
        origin = "http://studio.test"
        client, telemetry_client = self._client(
            StudioConfig(
                telemetry_enabled=True,
                otel={"collector_url": "http://collector:4318", "allowed_origins": [origin]},
            ),
            monkeypatch,
        )

        response = client.post(
            "/studio/telemetry/v1/traces?timeout=1",
            content=b"payload",
            headers={"origin": origin, "content-type": "application/x-protobuf"},
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert len(telemetry_client.calls) == 1
        call = telemetry_client.calls[0]
        assert call["method"] == "POST"
        assert call["url"] == "http://collector:4318/v1/traces?timeout=1"
        assert call["content"] == b"payload"
        assert "origin" not in call["headers"]
        assert call["headers"]["content-type"] == "application/x-protobuf"
        assert call["headers"]["X-Real-IP"] == "testclient"
        assert call["headers"]["X-Forwarded-For"] == "testclient"

    def test_post_only_forwards_whitelisted_telemetry_headers(self, monkeypatch: pytest.MonkeyPatch):
        """Test that browser credentials and metadata are not forwarded to the collector."""
        origin = "http://studio.test"
        client, telemetry_client = self._client(
            StudioConfig(
                telemetry_enabled=True,
                otel={"collector_url": "http://collector:4318", "allowed_origins": [origin]},
            ),
            monkeypatch,
        )

        response = client.post(
            "/studio/telemetry/v1/logs",
            content=b"payload",
            headers={
                "origin": origin,
                "accept": "application/json",
                "authorization": "Bearer app-token",
                "content-encoding": "gzip",
                "content-type": "application/json",
                "cookie": "session=abc",
                "referer": "http://studio.test/workspaces",
                "traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
                "x-auth-token": "token",
                "x-csrf-token": "csrf",
                "x-session-id": "session",
            },
        )

        assert response.status_code == 200
        assert telemetry_client.calls[0]["headers"] == {
            "accept": "application/json",
            "content-encoding": "gzip",
            "content-type": "application/json",
            "X-Real-IP": "testclient",
            "X-Forwarded-For": "testclient",
        }

    def test_post_strips_root_telemetry_prefix_and_proxies_request(self, monkeypatch: pytest.MonkeyPatch):
        """Test that /telemetry/* keeps parity with the old nginx route."""
        origin = "http://studio.test"
        client, telemetry_client = self._client(
            StudioConfig(
                telemetry_enabled=True,
                otel={"collector_url": "http://collector:4318", "allowed_origins": [origin]},
            ),
            monkeypatch,
        )

        response = client.post("/telemetry/v1/logs", headers={"origin": origin})

        assert response.status_code == 200
        assert telemetry_client.calls[0]["url"] == "http://collector:4318/v1/logs"

    def test_options_returns_preflight_response_without_proxying(self, monkeypatch: pytest.MonkeyPatch):
        """Test that CORS preflight requests are handled locally."""
        origin = "http://studio.test"
        client, telemetry_client = self._client(
            StudioConfig(
                telemetry_enabled=True,
                otel={"collector_url": "http://collector:4318", "allowed_origins": [origin]},
            ),
            monkeypatch,
        )

        response = client.options("/studio/telemetry/v1/traces", headers={"origin": origin})

        assert response.status_code == 204
        assert response.headers["access-control-allow-headers"] == (
            "Accept,Accept-Language,Content-Encoding,Content-Language,Content-Type"
        )
        assert response.headers["access-control-allow-methods"] == "POST, OPTIONS"
        assert response.headers["access-control-max-age"] == "1728000"
        assert telemetry_client.calls == []

    def test_disabled_telemetry_returns_404(self, monkeypatch: pytest.MonkeyPatch):
        """Test that disabled telemetry preserves the old nginx 404 behavior."""
        client, telemetry_client = self._client(
            StudioConfig(telemetry_enabled=False, otel={"collector_url": "http://collector:4318"}),
            monkeypatch,
        )

        response = client.post("/studio/telemetry/v1/traces", headers={"origin": "http://testserver"})

        assert response.status_code == 404
        assert telemetry_client.calls == []

    def test_disallowed_origin_returns_403(self, monkeypatch: pytest.MonkeyPatch):
        """Test that disallowed origins preserve the old nginx 403 behavior."""
        client, telemetry_client = self._client(
            StudioConfig(
                telemetry_enabled=True,
                otel={"collector_url": "http://collector:4318", "allowed_origins": ["http://studio.test"]},
            ),
            monkeypatch,
        )

        response = client.post("/studio/telemetry/v1/traces", headers={"origin": "http://not-allowed.test"})

        assert response.status_code == 403
        assert telemetry_client.calls == []

    def test_same_origin_request_is_allowed(self, monkeypatch: pytest.MonkeyPatch):
        """Test that same-origin Studio deployments work without hard-coded host config."""
        client, telemetry_client = self._client(
            StudioConfig(
                telemetry_enabled=True,
                otel={"collector_url": "http://collector:4318", "allowed_origins": []},
            ),
            monkeypatch,
        )

        response = client.post("/studio/telemetry/v1/traces", headers={"origin": "http://testserver"})

        assert response.status_code == 200
        assert telemetry_client.calls[0]["url"] == "http://collector:4318/v1/traces"


class TestStaticFilesPath:
    """Tests for static_files_path configuration."""

    def test_default_static_files_path(self, monkeypatch: pytest.MonkeyPatch):
        """Test that the default path is the packaged static dir."""
        import nmp.studio

        expected = Path(nmp.studio.__file__).parent / "static"
        service = StudioService()
        monkeypatch.setattr(service, "_source_static_files_path", lambda: None)
        path = service._get_static_files_path()
        assert path == expected

    def test_configured_static_files_path_is_used(self, tmp_path: Path):
        """Test that a configured static_files_path is used."""
        # Create a temporary directory with a dummy file
        static_dir = tmp_path / "custom-static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html></html>")

        # Create service with custom config
        config = StudioConfig(static_files_path=static_dir)
        service = StudioService().with_config(config)

        path = service._get_static_files_path()
        assert path == static_dir

    def test_static_files_path_config_default(self):
        """Test that StudioConfig has no configured static_files_path by default."""
        config = StudioConfig()
        assert config.static_files_path is None

    def test_static_files_path_can_be_set_by_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that env config can point Studio at source-built assets."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        monkeypatch.setenv("NMP_STUDIO_STATIC_FILES_PATH", str(static_dir))

        config = StudioConfig()

        assert config.static_files_path == static_dir

    def test_packaged_static_path_takes_precedence_over_source_dist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that packaged assets are preferred when they are available."""
        packaged_static = tmp_path / "package-static"
        packaged_static.mkdir()
        (packaged_static / "index.html").write_text("<html></html>")
        source_dist = tmp_path / "repo" / "web" / "packages" / "studio" / "dist"

        service = StudioService()
        monkeypatch.setattr(service, "_packaged_static_files_path", lambda: packaged_static)
        monkeypatch.setattr(service, "_source_static_files_path", lambda: source_dist)

        path = service._get_static_files_path()
        assert path == packaged_static

    def test_source_dist_used_when_packaged_static_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that source-built assets are used when package assets are absent."""
        source_root = tmp_path / "repo"
        studio_dir = source_root / "web" / "packages" / "studio"
        studio_dir.mkdir(parents=True)
        (studio_dir / "package.json").write_text('{"name":"nemo-studio-ui"}')

        packaged_static = tmp_path / "package-static"

        service = StudioService()
        monkeypatch.chdir(source_root)
        monkeypatch.setattr(service, "_packaged_static_files_path", lambda: packaged_static)

        path = service._get_static_files_path()
        assert path == studio_dir / "dist"

    def test_missing_static_files_route_explains_recovery(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that missing Studio assets return recovery instructions instead of a bare 404."""
        missing_static = tmp_path / "missing-static"
        service = StudioService()
        monkeypatch.setattr(service, "_get_static_files_path", lambda: missing_static)
        app = FastAPI()

        service.configure_app(app)

        client = TestClient(app)
        response = client.get("/studio/")

        assert response.status_code == 503
        assert "make bootstrap-studio" in response.text
        assert "source ~/.nvm/nvm.sh" in response.text
        assert "nvm install 22" in response.text
        assert "pnpm env use --global 22.18.0" in response.text
        assert "Node.js and pnpm engines" in response.text
        assert "web/package.json" in response.text
        assert "nemo services restart" in response.text
        assert str(missing_static) in response.text

    def test_missing_static_files_route_handles_main_studio_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that the main Studio path returns build tips when assets are missing."""
        missing_static = tmp_path / "missing-static"
        service = StudioService()
        monkeypatch.setattr(service, "_get_static_files_path", lambda: missing_static)
        app = FastAPI()

        service.configure_app(app)

        client = TestClient(app)
        response = client.get("/studio")

        assert response.status_code == 503
        assert "Requested path: <code>/studio</code>" in response.text
        assert "Build tips" in response.text
        assert "make bootstrap-studio" in response.text
        assert "nemo services restart" in response.text

    def test_static_dir_without_index_route_explains_recovery(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that an incomplete Studio build also returns recovery instructions."""
        incomplete_static = tmp_path / "static"
        incomplete_static.mkdir()
        service = StudioService()
        monkeypatch.setattr(service, "_get_static_files_path", lambda: incomplete_static)
        app = FastAPI()

        service.configure_app(app)

        client = TestClient(app)
        response = client.get("/studio/")

        assert response.status_code == 503
        assert "make bootstrap-studio" in response.text
        assert "pnpm env use --global 22.18.0" in response.text
        assert str(incomplete_static) in response.text

    def test_missing_static_files_route_handles_nested_studio_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that nested Studio paths also return the recovery page when assets are missing."""
        missing_static = tmp_path / "missing-static"
        service = StudioService()
        monkeypatch.setattr(service, "_get_static_files_path", lambda: missing_static)
        app = FastAPI()

        service.configure_app(app)

        client = TestClient(app)
        response = client.get("/studio/agents")

        assert response.status_code == 503
        assert "/studio/agents" in response.text


class TestStudioConfigEnvReplacements:
    """Tests for StudioConfig.env_replacements property."""

    def test_env_replacements_returns_dict(self):
        """Test that env_replacements returns a dict."""
        config = StudioConfig()
        replacements = config.env_replacements
        assert isinstance(replacements, dict)

    def test_env_replacements_uses_defaults_when_no_global_settings(self, monkeypatch: pytest.MonkeyPatch):
        """Test that defaults from ENV_MAPPINGS are used when config paths can't be resolved."""
        # Mock get_global_settings_from_env to return empty dict
        from nmp.common import config as common_config
        from nmp.studio.env_mappings import ENV_MAPPINGS

        monkeypatch.setattr(common_config.Configuration, "get_global_settings_from_env", lambda: {})

        # Create a fresh config after mocking
        config = StudioConfig()
        replacements = config.env_replacements

        # Check that mappings with defaults have their default values
        for mapping in ENV_MAPPINGS:
            if mapping.default:
                assert mapping.marker in replacements
                assert replacements[mapping.marker] == mapping.default

    def test_env_replacements_resolves_config_paths(self, monkeypatch: pytest.MonkeyPatch):
        """Test that config paths are correctly resolved from global settings."""
        # Mock get_global_settings_from_env to return known values
        mock_settings = {
            "studio": {
                "platform_base_url": "http://test.example.com",
                "telemetry_enabled": "true",
            },
        }
        from nmp.common import config as common_config

        monkeypatch.setattr(common_config.Configuration, "get_global_settings_from_env", lambda: mock_settings)

        # Create a fresh config after mocking
        config = StudioConfig()
        replacements = config.env_replacements

        # Verify the studio.platform_base_url was resolved
        assert "STUDIO_UI_VITE_PLATFORM_BASE_URL" in replacements
        assert replacements["STUDIO_UI_VITE_PLATFORM_BASE_URL"] == "http://test.example.com"

        # Verify the studio.telemetry_enabled was resolved
        assert "STUDIO_UI_VITE_TELEMETRY_ENABLED" in replacements
        assert replacements["STUDIO_UI_VITE_TELEMETRY_ENABLED"] == "true"

    def test_env_replacements_empty_global_setting_falls_back_to_config_field(self, monkeypatch: pytest.MonkeyPatch):
        """Test that empty global settings do not block StudioConfig field fallback."""
        mock_settings = {"studio": {"platform_base_url": ""}}
        from nmp.common import config as common_config

        monkeypatch.setattr(common_config.Configuration, "get_global_settings_from_env", lambda: mock_settings)

        config = StudioConfig(platform_base_url="http://fallback.example.com")
        replacements = config.env_replacements

        assert replacements["STUDIO_UI_VITE_PLATFORM_BASE_URL"] == "http://fallback.example.com"

    def test_env_replacements_is_cached(self, monkeypatch: pytest.MonkeyPatch):
        """Test that env_replacements is cached and not recomputed."""
        call_count = 0

        def mock_get_settings():
            nonlocal call_count
            call_count += 1
            return {"platform": {"base_url": "http://test.example.com"}}

        from nmp.common import config as common_config

        monkeypatch.setattr(common_config.Configuration, "get_global_settings_from_env", mock_get_settings)

        config = StudioConfig()

        # Access env_replacements multiple times
        _ = config.env_replacements
        _ = config.env_replacements
        _ = config.env_replacements

        # Should only have called get_global_settings_from_env once (during first access)
        assert call_count == 1

    def test_platform_base_url_falls_back_to_platform_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """When studio.platform_base_url is blank, platform.base_url is used."""
        mock_settings = {
            "platform": {"base_url": "http://0.0.0.0:8080"},
            "studio": {},
        }
        from nmp.common import config as common_config

        monkeypatch.setattr(common_config.Configuration, "get_global_settings_from_env", lambda: mock_settings)

        config = StudioConfig()
        replacements = config.env_replacements

        assert replacements["STUDIO_UI_VITE_PLATFORM_BASE_URL"] == "http://0.0.0.0:8080"

    def test_platform_base_url_studio_value_takes_precedence(self, monkeypatch: pytest.MonkeyPatch):
        """An explicit studio.platform_base_url wins over the platform-level fallback."""
        mock_settings = {
            "platform": {"base_url": "http://0.0.0.0:8080"},
            "studio": {"platform_base_url": "https://studio.example.com"},
        }
        from nmp.common import config as common_config

        monkeypatch.setattr(common_config.Configuration, "get_global_settings_from_env", lambda: mock_settings)

        config = StudioConfig()
        replacements = config.env_replacements

        assert replacements["STUDIO_UI_VITE_PLATFORM_BASE_URL"] == "https://studio.example.com"

    def test_resolve_config_path_nested(self):
        """Test that _resolve_config_path handles nested paths."""
        config = StudioConfig()

        # Set a known value for global_settings
        config.__dict__["global_settings"] = {"level1": {"level2": {"level3": "deep_value"}}}

        result = config._resolve_config_path("level1.level2.level3")
        assert result == "deep_value"

    def test_resolve_config_path_returns_none_for_missing(self):
        """Test that _resolve_config_path returns None for missing paths."""
        config = StudioConfig()

        # Set empty global settings
        config.__dict__["global_settings"] = {}

        result = config._resolve_config_path("nonexistent.path")
        assert result is None
