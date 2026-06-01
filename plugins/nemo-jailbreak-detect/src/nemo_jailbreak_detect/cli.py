# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI for the jailbreak-detection plugin — ``nemo jailbreak-detect ...``.

Thin HTTP wrappers over the plugin service's deployment CRUD endpoints.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx
import typer
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.cli_errors import print_http_request_error, print_http_status_error

_API = "/apis/jailbreak-detect/v2/workspaces/{workspace}/deployments"


def _request_json(method: str, url: str, *, json_body: dict | None = None) -> Any:
    try:
        response = httpx.request(method, url, json=json_body, timeout=30)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print_http_status_error(exc, action=f"{method} jailbreak-detect API")
        raise typer.Exit(code=1) from exc
    except httpx.RequestError as exc:
        print_http_request_error(exc, action=f"{method} jailbreak-detect API")
        raise typer.Exit(code=1) from exc

    if response.status_code == 204 or not response.content:
        return None
    return response.json()


class JailbreakDetectCLI(NemoCLI):
    """Exposes plugin commands as ``nemo jailbreak-detect ...``."""

    name = "jailbreak-detect"
    description = "Manage self-hosted jailbreak-detection model deployments."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help="Jailbreak-detection deployment commands.")

        @app.command()
        def deploy(
            workspace: str = typer.Option(..., help="Workspace name."),
            name: str = typer.Option(..., help="Deployment name (unique within workspace)."),
            image: Optional[str] = typer.Option(None, help="Override the model server image."),
            device: Optional[str] = typer.Option(None, help='Device, e.g. "cpu" or "cuda:0".'),
            port: Optional[int] = typer.Option(None, help="Host port to expose."),
            backend: Optional[str] = typer.Option(None, help='Deployment backend ("docker" or "jobs").'),
            base_url: str = typer.Option("http://localhost:8080", envvar="NMP_BASE_URL"),
        ) -> None:
            """Create a deployment (the controller starts the server)."""
            body: dict = {"name": name}
            for key, value in (("image", image), ("device", device), ("port", port), ("backend", backend)):
                if value is not None:
                    body[key] = value
            url = base_url.rstrip("/") + _API.format(workspace=workspace)
            typer.echo(json.dumps(_request_json("POST", url, json_body=body), indent=2))

        @app.command()
        def status(
            workspace: str = typer.Option(..., help="Workspace name."),
            name: Optional[str] = typer.Option(None, help="Deployment name; omit to list all."),
            base_url: str = typer.Option("http://localhost:8080", envvar="NMP_BASE_URL"),
        ) -> None:
            """Show deployment status."""
            url = base_url.rstrip("/") + _API.format(workspace=workspace)
            if name:
                url = f"{url}/{name}"
            typer.echo(json.dumps(_request_json("GET", url), indent=2))

        @app.command()
        def teardown(
            workspace: str = typer.Option(..., help="Workspace name."),
            name: str = typer.Option(..., help="Deployment name."),
            base_url: str = typer.Option("http://localhost:8080", envvar="NMP_BASE_URL"),
            yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
        ) -> None:
            """Mark a deployment for teardown."""
            if not yes:
                typer.confirm(f"Tear down deployment '{workspace}/{name}'?", abort=True)
            url = base_url.rstrip("/") + _API.format(workspace=workspace) + f"/{name}"
            typer.echo(json.dumps(_request_json("DELETE", url), indent=2))

        return app
