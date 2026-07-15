# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights CLI and contributed subcommands."""

import asyncio
import json
import os
from importlib.metadata import entry_points
from pathlib import Path
from typing import ClassVar

import typer
from nemo_insights_plugin.analyst.run import run_analyst
from nemo_insights_plugin.client import make_client
from nemo_platform_plugin.cli import NemoCLI

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_WORKSPACE = "default"


class InsightsCLI(NemoCLI):
    """``nemo insights ...`` subcommands."""

    name: ClassVar[str] = "insights"
    description: ClassVar[str] = "Analyze agent telemetry and act on insights."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            """Force subcommand dispatch even when only one verb is registered."""

        analysis_app = typer.Typer(
            help="Manage periodic agent analysis opt-in state.",
            no_args_is_help=True,
        )
        app.add_typer(analysis_app, name="analysis")

        @app.command("analyze")
        def analyze(
            agent: str = typer.Option(
                ...,
                "--agent",
                help="Name of the agent (agent under test) the analyst should focus on.",
            ),
            agent_spec: Path | None = typer.Option(
                None,
                "--agent-spec",
                help="Path to a markdown file describing the agent under test (its spec).",
                exists=True,
                readable=True,
            ),
            workspace: str = typer.Option(
                DEFAULT_WORKSPACE,
                "--workspace",
                help="Workspace the analyst should operate in.",
            ),
            base_url: str = typer.Option(
                os.environ.get("NMP_BASE_URL", DEFAULT_BASE_URL),
                "--base-url",
                help="Base URL of the running NMP instance the analyst's tools should call.",
                envvar="NMP_BASE_URL",
            ),
            insights_output: Path | None = typer.Option(
                None,
                "--insights-file-output",
                help=(
                    "Read and write insights from this local YAML file instead "
                    "of the Insights plugin API. Lets the analyst run against a "
                    "deployment that hosts observability data but not this "
                    "plugin; each run merges into the file. Trace/feedback reads "
                    "still hit --base-url."
                ),
            ),
            verbose: bool = typer.Option(
                False,
                "--verbose",
                "-v",
                help=(
                    "Stream the analyst's tool calls and reasoning to stderr "
                    "while it runs. Off by default so that stdout stays clean "
                    "for piping the final answer."
                ),
            ),
        ) -> None:
            """Run the analyst agent against a running NMP instance.

            Builds the analyst agent with ``--agent`` (and optional
            ``--agent-spec``) formatted into its instructions and tools scoped
            to ``--agent`` / ``--workspace`` / ``--base-url``, runs it, and
            prints whatever the agent returns.
            """
            output = asyncio.run(
                run_analyst(
                    agent=agent,
                    agent_spec=agent_spec.read_text() if agent_spec else None,
                    workspace=workspace,
                    base_url=base_url,
                    insights_output=insights_output,
                    verbose=verbose,
                )
            )
            typer.echo(output)

        @analysis_app.command("enable")
        def enable_analysis(
            agent: str = typer.Option(
                ...,
                "--agent",
                help="Name of the agent to opt in to periodic analysis.",
            ),
            workspace: str = typer.Option(
                DEFAULT_WORKSPACE,
                "--workspace",
                help="Workspace the agent belongs to.",
            ),
            base_url: str = typer.Option(
                os.environ.get("NMP_BASE_URL", DEFAULT_BASE_URL),
                "--base-url",
                help="Base URL of the running NMP instance.",
                envvar="NMP_BASE_URL",
            ),
        ) -> None:
            """Enable periodic analysis for an agent."""
            typer.echo(
                asyncio.run(
                    _analysis_config_command(
                        action="enable",
                        agent=agent,
                        workspace=workspace,
                        base_url=base_url,
                    )
                )
            )

        @analysis_app.command("disable")
        def disable_analysis(
            agent: str = typer.Option(
                ...,
                "--agent",
                help="Name of the agent to opt out of periodic analysis.",
            ),
            workspace: str = typer.Option(
                DEFAULT_WORKSPACE,
                "--workspace",
                help="Workspace the agent belongs to.",
            ),
            base_url: str = typer.Option(
                os.environ.get("NMP_BASE_URL", DEFAULT_BASE_URL),
                "--base-url",
                help="Base URL of the running NMP instance.",
                envvar="NMP_BASE_URL",
            ),
        ) -> None:
            """Disable periodic analysis for an agent."""
            typer.echo(
                asyncio.run(
                    _analysis_config_command(
                        action="disable",
                        agent=agent,
                        workspace=workspace,
                        base_url=base_url,
                    )
                )
            )

        @analysis_app.command("status")
        def analysis_status(
            agent: str | None = typer.Option(
                None,
                "--agent",
                help="Optional agent name. Omit to list all analysis configs.",
            ),
            workspace: str = typer.Option(
                DEFAULT_WORKSPACE,
                "--workspace",
                help="Workspace to inspect.",
            ),
            base_url: str = typer.Option(
                os.environ.get("NMP_BASE_URL", DEFAULT_BASE_URL),
                "--base-url",
                help="Base URL of the running NMP instance.",
                envvar="NMP_BASE_URL",
            ),
        ) -> None:
            """Show periodic analysis opt-in state."""
            typer.echo(
                asyncio.run(
                    _analysis_config_command(
                        action="status",
                        agent=agent,
                        workspace=workspace,
                        base_url=base_url,
                    )
                )
            )

        for entry_point in sorted(entry_points(group="nemo.insights.commands"), key=lambda item: item.name):
            app.add_typer(entry_point.load()(), name=entry_point.name)
        return app


async def _analysis_config_command(
    *,
    action: str,
    agent: str | None,
    workspace: str,
    base_url: str,
) -> str:
    """Run one analysis-config CLI action and return JSON for stdout."""
    client = make_client(base_url)
    try:
        if action == "enable":
            if agent is None:
                raise ValueError("agent is required for enable")
            result = await client.insights.analysis_configs.enable(workspace=workspace, agent=agent)
            return _json(result.model_dump(mode="json"))
        if action == "disable":
            if agent is None:
                raise ValueError("agent is required for disable")
            result = await client.insights.analysis_configs.disable(workspace=workspace, agent=agent)
            return _json(result.model_dump(mode="json"))
        if action == "status":
            if agent:
                result = await client.insights.analysis_configs.get(workspace=workspace, agent=agent)
                return _json(result.model_dump(mode="json"))
            page = await client.insights.analysis_configs.list_configs(workspace=workspace, page_size=100)
            return _json(page.model_dump(mode="json"))
        raise ValueError(f"Unknown analysis config action: {action}")
    finally:
        await client.close()


def _json(payload: object) -> str:
    """Serialize a CLI payload with stable indentation."""
    return json.dumps(payload, indent=2)
