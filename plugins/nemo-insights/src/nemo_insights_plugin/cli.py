# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights plugin CLI — registered under ``nemo.cli`` as ``nemo insights``.

v1 ships:

* ``nemo insights analyze`` — placeholder that validates an AgentRegistration
  exists and prints a stub analyst prompt. The real analyst replaces this in a
  follow-up PR.
* ``nemo insights registrations {create,list,get,update,delete}`` — thin HTTP
  wrappers around the AgentRegistration endpoints for human inspection.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx
import typer
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.cli_errors import print_http_request_error, print_http_status_error


def _request_json(method: str, url: str, *, json_body: dict | None = None) -> Any:
    try:
        response = httpx.request(method, url, json=json_body, timeout=30)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print_http_status_error(exc, action=f"{method} insights API")
        raise typer.Exit(code=1) from exc
    except httpx.RequestError as exc:
        print_http_request_error(exc, action=f"{method} insights API")
        raise typer.Exit(code=1) from exc

    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _insights_url(base_url: str, workspace: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/apis/insights/v2/workspaces/{workspace}{path}"


class InsightsPluginCLI(NemoCLI):
    """Exposes plugin commands as ``nemo insights ...``."""

    name = "insights"
    description = "Insights plugin commands."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help="Insights plugin commands.")

        # ── analyze (placeholder) ─────────────────────────────────────────
        @app.command()
        def analyze(
            agent: str = typer.Option(..., help="AgentRegistration name to analyze."),
            workspace: str = typer.Option("default", help="Workspace name."),
            base_url: str = typer.Option("http://localhost:8000", envvar="NMP_BASE_URL"),
        ) -> None:
            """Placeholder for the analyst agent (M1 stub).

            Validates that an AgentRegistration exists for ``--agent`` and prints
            a stub analyst prompt. The real analyst will replace this once the
            NAT workflow lands in a follow-up PR.
            """
            url = _insights_url(base_url, workspace, f"/agent_registrations/{agent}")
            try:
                reg = _request_json("GET", url)
            except typer.Exit:
                raise
            typer.echo(f"# Analyst placeholder for agent '{agent}' in workspace '{workspace}'")
            typer.echo("")
            typer.echo(f"Repo URL:                {reg.get('repo_url', '')}")
            typer.echo(f"AGENT_DESCRIPTION.md:    {reg.get('agent_description_path', '')}")
            typer.echo(f"Eval command:            {reg.get('eval_command', '')}")
            typer.echo("")
            typer.echo(
                "The analyst agent runtime is not yet wired up. In a follow-up PR "
                "this command will: read recent traces from intake, cluster failure "
                "patterns, write Insights via the plugin API, and emit a structured "
                "experimentalist prompt. For now it only confirms the AgentRegistration."
            )

        # ── registrations subgroup ──────────────────────────────────────
        regs = typer.Typer(help="Manage AgentRegistration entities.")
        app.add_typer(regs, name="registrations")

        @regs.command("create")
        def create_registration(
            workspace: str = typer.Option(..., help="Workspace name."),
            name: str = typer.Option(..., help="Canonical agent name."),
            description: str = typer.Option("", help="Human-readable description."),
            repo_url: str = typer.Option("", help="URL of the AUT repo."),
            agent_description_path: str = typer.Option("AGENT_DESCRIPTION.md", help="Path within repo."),
            agent_description_content: Optional[str] = typer.Option(None, help="AGENT_DESCRIPTION.md content."),
            eval_command: str = typer.Option("", help="CLI command for running evals."),
            base_url: str = typer.Option("http://localhost:8000", envvar="NMP_BASE_URL"),
        ) -> None:
            """Register a new agent under test."""
            body: dict[str, Any] = {
                "name": name,
                "description": description,
                "repo_url": repo_url,
                "agent_description_path": agent_description_path,
                "eval_command": eval_command,
            }
            if agent_description_content is not None:
                body["agent_description_content"] = agent_description_content
            url = _insights_url(base_url, workspace, "/agent_registrations")
            typer.echo(json.dumps(_request_json("POST", url, json_body=body), indent=2))

        @regs.command("list")
        def list_registrations(
            workspace: str = typer.Option(..., help="Workspace name."),
            base_url: str = typer.Option("http://localhost:8000", envvar="NMP_BASE_URL"),
        ) -> None:
            url = _insights_url(base_url, workspace, "/agent_registrations")
            typer.echo(json.dumps(_request_json("GET", url), indent=2))

        @regs.command("get")
        def get_registration(
            workspace: str = typer.Option(..., help="Workspace name."),
            name: str = typer.Option(..., help="AgentRegistration name."),
            base_url: str = typer.Option("http://localhost:8000", envvar="NMP_BASE_URL"),
        ) -> None:
            url = _insights_url(base_url, workspace, f"/agent_registrations/{name}")
            typer.echo(json.dumps(_request_json("GET", url), indent=2))

        @regs.command("delete")
        def delete_registration(
            workspace: str = typer.Option(..., help="Workspace name."),
            name: str = typer.Option(..., help="AgentRegistration name."),
            base_url: str = typer.Option("http://localhost:8000", envvar="NMP_BASE_URL"),
            yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
        ) -> None:
            if not yes:
                typer.confirm(f"Delete AgentRegistration '{workspace}/{name}'?", abort=True)
            url = _insights_url(base_url, workspace, f"/agent_registrations/{name}")
            _request_json("DELETE", url)
            typer.echo(f"Deleted '{workspace}/{name}'.")

        return app
