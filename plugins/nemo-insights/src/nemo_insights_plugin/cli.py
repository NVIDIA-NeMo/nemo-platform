# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights CLI and contributed subcommands."""

import asyncio
import json
import os
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import ClassVar

import httpx
import typer
from nemo_insights_plugin.analyst.run import ClientConstructionError, run_analyst
from nemo_insights_plugin.client import make_client
from nemo_insights_plugin.contracts.checks import CheckResult, advisories, format_report, required_failures
from nemo_insights_plugin.contracts.insights import InsightsFileError, validate_insights_file
from nemo_insights_plugin.contracts.profile import (
    DEFAULT_BASE_URL,
    EnvFileError,
    ProfileError,
    discover_profile,
    load_env_file,
    resolve_base_url,
)
from nemo_insights_plugin.preflight import (
    AnalysisProbes,
    check_environment,
    check_profile,
    read_agent_spec,
)
from nemo_insights_plugin.profile import AnalysisProfile, load_profile, pick_agent_spec
from nemo_platform import NeMoPlatformError
from nemo_platform_plugin.cli import NemoCLI
from pydantic_ai import AgentRunError

DEFAULT_WORKSPACE = "default"
_PREFLIGHT_PROBES: AnalysisProbes | None = None


@dataclass(frozen=True)
class _ResolvedAnalysis:
    agent: str
    agent_spec: str | None
    workspace: str
    base_url: str
    insights_output: Path | None
    profile_output: Path | None
    profile_dir: Path | None
    spec_checks: tuple[CheckResult, ...]


def _load_profile_or_error(profile_path: Path | None) -> tuple[AnalysisProfile | None, str | None]:
    """Load an explicit or discovered profile, preserving non-explicit failures."""
    found = profile_path or discover_profile()
    if found is None:
        return None, None
    try:
        profile = load_profile(found)
    except ProfileError as exc:
        if profile_path is not None:
            raise
        return None, str(exc)
    if profile_path is None:
        typer.echo(f"Using profile: {found} (agent: {profile.agent})", err=True)
    loaded = load_env_file(found.parent / ".env")
    if loaded:
        typer.echo(f"Loaded .env from {found.parent / '.env'} ({len(loaded)} vars)", err=True)
    return profile, None


def _preflight_or_exit(checks: list[CheckResult]) -> None:
    """Print blockers and stop before an analyst run."""
    if required_failures(checks):
        typer.echo(format_report(checks), err=True)
        raise typer.Exit(code=1)
    warnings = advisories(checks)
    if warnings:
        typer.echo(format_report(warnings), err=True)


def _one_line_error(exc: BaseException) -> str:
    """Collapse expected CLI failures to one readable terminal line."""
    return " ".join(str(exc).splitlines()).strip() or type(exc).__name__


def _resolve_analysis(
    *,
    agent: str | None,
    agent_spec: Path | None,
    workspace: str | None,
    base_url: str | None,
    profile_path: Path | None,
    insights_output: Path | None,
) -> _ResolvedAnalysis:
    profile, profile_error = _load_profile_or_error(profile_path)
    if profile_error is not None:
        if agent is None or workspace is None:
            raise ProfileError(profile_error)
        typer.echo(f"warning: ignoring discovered profile: {profile_error}", err=True)

    resolved_agent = agent or (profile.agent if profile is not None else None)
    if resolved_agent is None:
        raise ProfileError(
            "No --agent given and no optimizer.yaml profile found. Pass --agent or run from a directory with a profile."
        )
    resolved_workspace = workspace or (profile.workspace if profile is not None else DEFAULT_WORKSPACE)

    spec_path = agent_spec
    spec_error: str | None = None
    if spec_path is None and profile is not None:
        try:
            spec_path = pick_agent_spec(profile)
        except ProfileError as exc:
            spec_error = str(exc)
    spec_content, spec_checks = read_agent_spec(spec_path, spec_error)

    resolved_base_url = resolve_base_url(base_url)
    profile_output = None
    if insights_output is None and profile is not None:
        profile_output = profile.profile_dir / ".nemo-optimizer" / "insights.yaml"
    resolved_output = insights_output if insights_output is not None else profile_output
    validate_insights_file(resolved_output)

    return _ResolvedAnalysis(
        agent=resolved_agent,
        agent_spec=spec_content,
        workspace=resolved_workspace,
        base_url=resolved_base_url,
        insights_output=resolved_output,
        profile_output=profile_output,
        profile_dir=profile.profile_dir if profile is not None else None,
        spec_checks=tuple(spec_checks),
    )


async def _run_analysis(analysis: _ResolvedAnalysis, *, verbose: bool) -> str:
    checks = list(analysis.spec_checks)
    checks.extend(
        await check_environment(
            agent=analysis.agent,
            workspace=analysis.workspace,
            base_url=analysis.base_url,
            profile_dir=analysis.profile_dir,
            probes=_PREFLIGHT_PROBES,
        )
    )
    _preflight_or_exit(checks)

    if analysis.profile_output is not None:
        analysis.profile_output.parent.mkdir(parents=True, exist_ok=True)
        typer.echo(f"Insights file: {analysis.profile_output}", err=True)
    try:
        return await run_analyst(
            agent=analysis.agent,
            agent_spec=analysis.agent_spec,
            workspace=analysis.workspace,
            base_url=analysis.base_url,
            insights_output=analysis.insights_output,
            verbose=verbose,
        )
    except AgentRunError as exc:
        detail = _one_line_error(exc).rstrip(".")
        typer.echo(
            f"Error: analyst run failed: {detail}. "
            "Check inference model access and credentials, "
            "then retry or adjust usage limits.",
            err=True,
        )
        raise typer.Exit(1) from None
    except (ClientConstructionError, NeMoPlatformError, httpx.HTTPError, OSError) as exc:
        detail = _one_line_error(exc).rstrip(".")
        typer.echo(
            f"Error: analysis failed: {detail}. Check --base-url/NMP_BASE_URL, "
            "authentication, workspace, and Intake availability.",
            err=True,
        )
        raise typer.Exit(1) from None


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
            agent: str | None = typer.Option(
                None,
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
            workspace: str | None = typer.Option(
                None,
                "--workspace",
                help="Workspace the analyst should operate in.",
            ),
            base_url: str | None = typer.Option(
                None,
                "--base-url",
                help="Base URL of the running NMP instance the analyst's tools should call.",
            ),
            profile_path: Path | None = typer.Option(
                None,
                "--profile",
                help="Path to optimizer.yaml. Default: discovered by walking up from cwd.",
                exists=True,
                dir_okay=False,
                readable=True,
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
            try:
                analysis = _resolve_analysis(
                    agent=agent,
                    agent_spec=agent_spec,
                    workspace=workspace,
                    base_url=base_url,
                    profile_path=profile_path,
                    insights_output=insights_output,
                )
                output = asyncio.run(_run_analysis(analysis, verbose=verbose))
            except (ProfileError, EnvFileError, InsightsFileError, OSError, UnicodeError) as exc:
                typer.echo(f"Error: {_one_line_error(exc)}", err=True)
                raise typer.Exit(1) from None
            typer.echo(output)

        @app.command("doctor")
        def doctor(
            profile_path: Path | None = typer.Option(
                None,
                "--profile",
                help="Path to optimizer.yaml. Default: discovered by walking up from cwd.",
                exists=True,
                dir_okay=False,
                readable=True,
            ),
            base_url: str | None = typer.Option(
                None,
                "--base-url",
                help="Base URL of the running NMP instance to check.",
            ),
        ) -> None:
            """Check whether the current profile is ready for analysis."""
            try:
                try:
                    profile, profile_error = _load_profile_or_error(profile_path)
                except ProfileError as exc:
                    profile, profile_error = None, str(exc)
                spec_path: Path | None = None
                spec_error: str | None = None
                if profile is not None:
                    try:
                        spec_path = pick_agent_spec(profile)
                    except ProfileError as exc:
                        spec_error = str(exc)
                _, spec_results = read_agent_spec(spec_path, spec_error)

                async def _flow() -> list[CheckResult]:
                    results = check_profile(profile, profile_error)
                    results.extend(spec_results)
                    if profile is not None:
                        results.extend(
                            await check_environment(
                                agent=profile.agent,
                                workspace=profile.workspace,
                                base_url=resolve_base_url(base_url),
                                profile_dir=profile.profile_dir,
                                probes=_PREFLIGHT_PROBES,
                            )
                        )
                    return results

                results = asyncio.run(_flow())
            except (EnvFileError, OSError, UnicodeError) as exc:
                typer.echo(f"Error: {_one_line_error(exc)}", err=True)
                raise typer.Exit(1) from None
            typer.echo(format_report(results))
            if required_failures(results):
                raise typer.Exit(code=1)

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
