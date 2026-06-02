# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Studio service implementation for serving the NeMo Studio UI."""

import logging
from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import List

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse
from nmp.common.http_clients import shared_async_http_client
from nmp.common.service import RouterConfig, Service
from nmp.studio import coding_agents
from nmp.studio.config import StudioConfig
from nmp.studio.static_files import SPAStaticFiles
from starlette.responses import Response

logger = logging.getLogger(__name__)

TELEMETRY_ALLOWED_HEADERS = "Accept,Accept-Language,Content-Encoding,Content-Language,Content-Type"
TELEMETRY_ALLOWED_METHODS = "POST, OPTIONS"
TELEMETRY_MAX_AGE_SECONDS = "1728000"
TELEMETRY_FORWARD_HEADERS = {
    "accept",
    "content-encoding",
    "content-type",
}
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class StudioService(Service[StudioConfig]):
    """Studio service for serving the NeMo Studio UI static assets.

    This service mounts the built Vite application at /studio and serves
    the static files with SPA routing support.

    Configuration is managed through StudioConfig, which provides:
    - static_files_path: Path to the built UI assets
    - env_replacements: Runtime values to inject into the UI bundle (cached)
    """

    dependencies: list[str] = []

    def __init__(self):
        """Initialize the studio service."""
        super().__init__(name="studio", module_name="nmp.studio")

    @property
    def title(self) -> str:
        """Service title for OpenAPI docs."""
        return "NeMo Studio UI"

    @property
    def description(self) -> str:
        """Service description for OpenAPI docs."""
        return "Serves the NeMo Studio web application and local coding-agent bridge"

    def get_routers(self) -> List[RouterConfig]:
        """Return routers for the studio service.

        Studio exposes API routes for local-only UI integrations in addition to
        serving static files.
        """
        return [
            RouterConfig(
                coding_agents.router,
                tag="Studio Coding Agents",
                description="Local coding-agent bridge endpoints",
            )
        ]

    def configure_app(self, app: FastAPI) -> None:
        """Configure the platform app with static file mounting.

        This method is called by the platform to allow the service to add
        custom routes, middleware, or mounts to the platform's FastAPI app.

        Args:
            app: The platform's FastAPI application
        """
        self._mount_telemetry_proxy(app)
        self._mount_coding_agent_mcp(app)
        self._mount_static_files(app)

    def _mount_coding_agent_mcp(self, app: FastAPI) -> None:
        """Mount the auth-bypassed MCP callback before the /studio static app."""
        coding_agents.mount_public_mcp_route(app)

    def _get_config(self) -> StudioConfig:
        """Get the studio config, creating a default if none is set.

        Returns:
            StudioConfig instance (from service_config or a new default)
        """
        if self.service_config is not None:
            return self.service_config
        return StudioConfig()

    def _mount_telemetry_proxy(self, app: FastAPI) -> None:
        """Mount OTLP/HTTP telemetry proxy routes that replace the old nginx behavior."""

        async def proxy_telemetry(request: Request, telemetry_path: str = "") -> Response:
            return await self._proxy_telemetry(request, telemetry_path)

        for route in ("/telemetry", "/telemetry/{telemetry_path:path}"):
            app.add_api_route(route, proxy_telemetry, methods=["POST", "OPTIONS"], include_in_schema=False)

        for route in ("/studio/telemetry", "/studio/telemetry/{telemetry_path:path}"):
            app.add_api_route(route, proxy_telemetry, methods=["POST", "OPTIONS"], include_in_schema=False)

    async def _proxy_telemetry(self, request: Request, telemetry_path: str = "") -> Response:
        """Proxy browser OTLP/HTTP telemetry to the configured collector."""
        config = self._get_config()
        if not self._is_telemetry_enabled(config):
            return Response(status_code=404)

        origin = request.headers.get("origin", "")
        same_origin = self._same_origin(request)
        if not config.otel.is_origin_allowed(origin, same_origin=same_origin):
            return Response(status_code=403)

        cors_headers = self._telemetry_cors_headers(origin)
        if request.method == "OPTIONS":
            return Response(
                status_code=204, headers={**cors_headers, "Access-Control-Max-Age": TELEMETRY_MAX_AGE_SECONDS}
            )

        collector_url = self._collector_url(config)
        if not collector_url:
            logger.error("Studio telemetry proxy requested, but studio.otel.collector_url is not configured")
            return Response(status_code=500, headers=cors_headers)

        target_url = self._build_telemetry_target_url(collector_url, telemetry_path, request.url.query)
        try:
            upstream_response = await shared_async_http_client().request(
                method=request.method,
                url=target_url,
                content=await request.body(),
                headers=self._forward_headers(request),
            )
        except Exception as e:
            logger.warning(f"Failed to proxy Studio telemetry request: {e}")
            return Response(status_code=502, headers=cors_headers)

        response_headers = self._response_headers(upstream_response.headers)
        response_headers.update(cors_headers)
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
        )

    def _is_telemetry_enabled(self, config: StudioConfig) -> bool:
        """Return the configured telemetry enabled flag, including legacy nested config."""
        legacy_value = config._resolve_config_path("studio.telemetry.enabled")
        if legacy_value is not None:
            return legacy_value.lower() == "true"
        return config.telemetry_enabled

    def _collector_url(self, config: StudioConfig) -> str:
        """Return the configured internal collector URL."""
        if config.otel.collector_url:
            return config.otel.collector_url
        return config._resolve_config_path("studio.otel.collector_url") or ""

    def _same_origin(self, request: Request) -> str | None:
        """Return the externally visible request origin when it can be inferred."""
        host = request.headers.get("host")
        if not host:
            return None
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
        return f"{scheme}://{host}"

    @staticmethod
    def _telemetry_cors_headers(origin: str) -> dict[str, str]:
        """CORS headers matching the previous nginx telemetry endpoint."""
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Headers": TELEMETRY_ALLOWED_HEADERS,
            "Access-Control-Allow-Methods": TELEMETRY_ALLOWED_METHODS,
            "Access-Control-Allow-Credentials": "true",
        }

    @staticmethod
    def _build_telemetry_target_url(collector_url: str, telemetry_path: str, query: str) -> str:
        """Build the upstream collector URL after stripping the telemetry route prefix."""
        target_path = f"/{telemetry_path.lstrip('/')}" if telemetry_path else "/"
        target_url = f"{collector_url.rstrip('/')}{target_path}"
        if query:
            target_url = f"{target_url}?{query}"
        return target_url

    @staticmethod
    def _forward_headers(request: Request) -> dict[str, str]:
        """Forward the OTLP headers the collector needs, plus proxy client IP headers."""
        headers = {key: value for key, value in request.headers.items() if key.lower() in TELEMETRY_FORWARD_HEADERS}
        if request.client and request.client.host:
            headers["X-Real-IP"] = request.client.host
            forwarded_for = request.headers.get("x-forwarded-for")
            headers["X-Forwarded-For"] = (
                f"{forwarded_for}, {request.client.host}" if forwarded_for else request.client.host
            )
        return headers

    @staticmethod
    def _response_headers(headers: Mapping[str, str]) -> dict[str, str]:
        """Forward safe response headers from the collector."""
        return {
            key: value
            for key, value in headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() in {"content-type", "content-encoding"}
        }

    def _mount_static_files(self, app: FastAPI) -> None:
        """Mount static files on the given FastAPI app.

        Args:
            app: FastAPI application to mount static files on
        """
        static_path = self._get_static_files_path()
        if self._static_assets_ready(static_path):
            # Get env replacements from config (single source of truth, cached)
            env_replacements = self._get_config().env_replacements
            app.mount(
                "/studio",
                SPAStaticFiles(
                    directory=str(static_path),
                    html=True,
                    env_replacements=env_replacements,
                ),
                name="studio-static",
            )
            logger.info(f"Mounted Studio UI static files from {static_path} at /studio")
        else:
            logger.warning(f"Static files not ready at {static_path}. The Studio UI will not be available.")
            self._mount_missing_static_files_notice(app, static_path)

    def _mount_missing_static_files_notice(self, app: FastAPI, static_path: Path) -> None:
        @app.get("/studio", include_in_schema=False)
        @app.get("/studio/", include_in_schema=False)
        @app.get("/studio/{path:path}", include_in_schema=False)
        async def studio_static_files_missing(path: str = "") -> HTMLResponse:
            return self._missing_static_files_response(static_path, path)

    @staticmethod
    def _missing_static_files_response(static_path: Path, requested_path: str = "") -> HTMLResponse:
        route = "/studio" if requested_path == "" else f"/studio/{requested_path}"
        html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>NeMo Studio assets are not built</title>
  </head>
  <body>
    <main>
      <h1>NeMo Studio assets are not built</h1>
      <p>The platform is running, but Studio cannot be served because the built web assets were not found.</p>
      <p>Requested path: <code>{escape(route)}</code></p>
      <p>Expected assets at: <code>{escape(str(static_path))}</code></p>
      <p>Install Node.js matching <code>web/package.json</code> with pnpm, rebuild Studio, and restart services:</p>
      <pre>pnpm env use --global 22.18.0
make bootstrap-studio
nemo services restart</pre>
    </main>
  </body>
</html>
"""
        return HTMLResponse(
            content=html,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Cache-Control": "no-store"},
        )

    def _get_static_files_path(self) -> Path:
        """Get the path to the static files directory.

        Returns:
            The configured static_files_path from StudioConfig, falling back to the
            packaged `static/` directory or source checkout `web/packages/studio/dist`.
        """
        configured = self._get_config().static_files_path
        if configured is not None:
            return configured

        packaged_static = self._packaged_static_files_path()
        if self._static_assets_ready(packaged_static):
            return packaged_static

        source_static = self._source_static_files_path()
        if source_static is not None:
            return source_static

        return packaged_static

    @staticmethod
    def _packaged_static_files_path() -> Path:
        """Return the package-local Studio static asset directory."""
        return Path(__file__).parent / "static"

    @staticmethod
    def _static_assets_ready(path: Path) -> bool:
        """Return True when a path looks like a built Studio UI bundle."""
        return (path / "index.html").is_file()

    @staticmethod
    def _source_static_files_path() -> Path | None:
        """Find source-built Studio UI assets in editable/source checkouts."""
        for start in (Path.cwd(), Path(__file__).resolve()):
            current = start if start.is_dir() else start.parent
            for candidate in (current, *current.parents):
                studio_package = candidate / "web" / "packages" / "studio"
                if (studio_package / "package.json").is_file():
                    return studio_package / "dist"
        return None
