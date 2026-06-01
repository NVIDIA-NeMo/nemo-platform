# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agents CLI — ``nemo agents`` command group.

Registered under the ``nemo.cli`` entry-point group.  The platform
discovers this class and mounts it as ``nemo agents <command>``.

**Local commands (no platform required):**

These wrap NAT's runtime directly and work without a running NeMo Platform
instance.

- ``invoke``   — single invocation (wraps ``nat run``)
- ``run``      — start a persistent local FastAPI server (wraps ``nat serve``)

The ``evaluate`` and ``optimize`` commands are auto-generated from the
``EvaluateAgentJob`` and ``OptimizeAgentJob`` registered under the
``nemo.jobs`` entry-point group — the platform injects them into this CLI
group at startup.

**Agent Resources commands (require a running cluster):**

- ``create``       — register an agent config on the platform
- ``list``         — list agents
- ``get``          — get an agent by name
- ``delete``       — delete an agent
- ``deploy``       — create a deployment for an agent (waits for ``running`` by default)
- ``undeploy``     — stop and remove a deployment
- ``logs``         — print or tail the subprocess log file for a deployment
- ``deployments``  — sub-group: list / get / delete deployments
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Optional, cast

import httpx
import typer
import yaml
from nemo_agents_plugin.leaderboard.cli import register_leaderboard_commands
from nemo_agents_plugin.usage.cli import register_usage_commands
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.cli_errors import print_http_request_error, print_http_status_error

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:8080"
_DEFAULT_WORKSPACE = "default"


class AgentsCLI(NemoCLI):
    """CLI commands for the Agents plugin."""

    name: ClassVar[str] = "agents"
    description: ClassVar[str] = "Agent lifecycle management — local execution and platform-managed deployments."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(
            name="agents",
            help=self.description,
            no_args_is_help=False,
        )

        @app.callback(invoke_without_command=True)
        def agents_callback(ctx: typer.Context) -> None:
            if ctx.invoked_subcommand is None:
                typer.echo(ctx.get_help())
                raise typer.Exit(0)

        _register_local_commands(app)
        _register_platform_commands(app)
        _register_improvement_commands(app)
        register_leaderboard_commands(app)
        register_usage_commands(app)
        return app


# ---------------------------------------------------------------------------
# Local commands — no platform required
# ---------------------------------------------------------------------------


def _register_local_commands(app: typer.Typer) -> None:
    """Register local NAT-wrapper commands onto *app*."""

    @app.command(rich_help_panel="Local commands")
    def invoke(
        agent_config: Optional[Path] = typer.Option(
            None,
            "--agent-config",
            "-c",
            help="Path to a NAT workflow YAML config file for local execution.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
        input: Optional[str] = typer.Option(
            None,
            "--input",
            "-i",
            help="Input query string for local invocation.",
        ),
        input_file: Optional[Path] = typer.Option(
            None,
            "--input-file",
            help="JSON file containing a list of input queries for batch invocation.",
            exists=True,
        ),
        agent: Optional[str] = typer.Option(
            None,
            "--agent",
            "-a",
            help="Name of a platform-deployed agent to invoke (platform required).",
        ),
        agent_deployment: Optional[str] = typer.Option(
            None,
            "--agent-deployment",
            "-d",
            help="Name of a specific deployment to invoke (platform required).",
        ),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """Invoke an agent — locally (with --agent-config) or via the platform (with --agent or --agent-deployment)."""
        if agent_config:
            _local_invoke(agent_config, input, input_file, workspace=workspace, base_url=base_url)
        elif agent or agent_deployment:
            _platform_invoke(base_url, workspace, agent, agent_deployment, input, input_file)
        else:
            typer.echo(
                "Error: provide --agent-config for local execution or --agent/--agent-deployment for platform invocation.",
                err=True,
            )
            raise typer.Exit(code=1)

    @app.command(rich_help_panel="Local commands")
    def run(
        agent_config: Path = typer.Option(
            ...,
            "--agent-config",
            "-c",
            help="Path to a NAT workflow YAML config file.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
        host: str = typer.Option("0.0.0.0", "--host"),
        port: int = typer.Option(8080, "--port", "-p"),
    ) -> None:
        """Run an agent locally as a persistent FastAPI server (wraps ``nat start fastapi``)."""
        import subprocess

        cmd = ["nat", "start", "fastapi", "--config_file", agent_config.name, "--host", host, "--port", str(port)]
        typer.echo(f"Starting agent server: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, cwd=agent_config.parent)
        except subprocess.CalledProcessError as exc:
            typer.echo(f"Agent server exited with code {exc.returncode}.", err=True)
            raise typer.Exit(code=exc.returncode)
        except FileNotFoundError:
            typer.echo("Error: 'nat' command not found.  Install nvidia-nat-core.", err=True)
            raise typer.Exit(code=1)


# Note: ``evaluate`` and ``optimize`` commands are auto-generated from the
# ``EvaluateAgentJob`` and ``OptimizeAgentJob`` registered under the
# ``nemo.jobs`` entry-point group.  The platform's CLI loader injects them
# into this group at startup (see ``nemo_platform_ext.cli.app``).


# ---------------------------------------------------------------------------
# Agent Resources commands — require a running cluster
# ---------------------------------------------------------------------------


def _register_platform_commands(app: typer.Typer) -> None:
    """Register Agent Resources commands (require a running cluster) onto *app*."""

    @app.command(rich_help_panel="Agent Resources (requires running cluster)")
    def create(
        name: str = typer.Option(..., "--name", "-n", help="Agent name."),
        agent_config: Path = typer.Option(
            ...,
            "--agent-config",
            "-c",
            help="Path to a NAT workflow YAML config file.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
        description: str = typer.Option("", "--description"),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """Register an agent on the platform."""
        from nemo_agents_plugin.utils import inject_default_model

        config_dict = _load_yaml(agent_config)
        # Resolve ${NEMO_DEFAULT_MODEL} client-side — agents service has no
        # user context at deploy time.
        config_dict = inject_default_model(config_dict)
        if _contains_default_model_placeholder(config_dict):
            typer.echo(
                "Error: agent config references ${NEMO_DEFAULT_MODEL} but no "
                "default model is selected. Run `nemo setup` to pick one, or "
                "replace the placeholder in the config with an explicit model name.",
                err=True,
            )
            raise typer.Exit(code=1)
        payload = {"name": name, "description": description, "config": config_dict}
        resp = _api_request("POST", base_url, f"/apis/agents/v2/workspaces/{workspace}/agents", json_body=payload)
        typer.echo(json.dumps(resp, indent=2))

    @app.command(name="list", rich_help_panel="Agent Resources (requires running cluster)")
    def list_agents(
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """List agents on the platform."""
        resp = _api_request("GET", base_url, f"/apis/agents/v2/workspaces/{workspace}/agents")
        typer.echo(json.dumps(resp, indent=2))

    @app.command(rich_help_panel="Agent Resources (requires running cluster)")
    def get(
        name: str = typer.Argument(..., help="Agent name."),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """Get an agent by name."""
        resp = _api_request("GET", base_url, f"/apis/agents/v2/workspaces/{workspace}/agents/{name}")
        typer.echo(json.dumps(resp, indent=2))

    @app.command(rich_help_panel="Agent Resources (requires running cluster)")
    def delete(
        name: str = typer.Argument(..., help="Agent name."),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    ) -> None:
        """Delete an agent from the platform."""
        if not yes:
            typer.confirm(f"Delete agent '{name}'?", abort=True)
        _api_request("DELETE", base_url, f"/apis/agents/v2/workspaces/{workspace}/agents/{name}")
        typer.echo(f"Agent '{name}' deleted.")

    @app.command(rich_help_panel="Agent Resources (requires running cluster)")
    def deploy(
        agent: str = typer.Option(..., "--agent", "-a", help="Name of the agent to deploy."),
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Deployment name (auto-generated if omitted)."),
        wait: bool = typer.Option(
            True,
            "--wait/--no-wait",
            help=(
                "Wait for the deployment to reach a terminal status (running or failed) "
                "before returning.  Exits 0 only on running; exits 1 with the failure "
                "reason if the subprocess dies during startup or the health check times "
                "out.  Pass --no-wait for fire-and-forget behaviour (the original "
                "default — returns the pending deployment immediately as JSON)."
            ),
        ),
        timeout: int = typer.Option(
            300,
            "--timeout",
            "-t",
            help="Maximum seconds to wait for a terminal status (only with --wait).",
        ),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """Deploy an agent on the platform.

        Blocks until the deployment is ``running`` (exit 0) or ``failed`` /
        timed out (exit 1) by default, so the exit code reflects the actual
        outcome of the spawn instead of merely the API call.  Use
        ``--no-wait`` to keep the previous fire-and-forget behaviour for
        scripted pipelines that prefer to poll separately via ``nemo agents
        deployments wait``.
        """
        payload: dict = {"agent": agent}
        if name:
            payload["name"] = name
        resp = _api_request("POST", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments", json_body=payload)
        if not wait:
            typer.echo(json.dumps(resp, indent=2))
            return

        # The API returns the pending entity; wait for it to settle before exiting.
        deployment_name = resp.get("name") if isinstance(resp, dict) else None
        if not deployment_name:
            # Defensive: should never happen if the API contract holds.
            typer.echo(json.dumps(resp, indent=2))
            typer.echo(
                "Warning: deployment created but its name was missing from the response; "
                "skipping --wait. Use `nemo agents deployments list` to find it.",
                err=True,
            )
            return

        success = _wait_for_deployment(base_url, workspace, deployment_name, timeout=timeout)
        raise typer.Exit(code=0 if success else 1)

    @app.command(rich_help_panel="Agent Resources (requires running cluster)")
    def logs(
        name: Optional[str] = typer.Argument(
            None,
            help=(
                "Deployment name to print logs for. If omitted, pass --agent to look up "
                "the most recent deployment for that agent."
            ),
        ),
        agent: Optional[str] = typer.Option(
            None,
            "--agent",
            "-a",
            help=(
                "Resolve the most recent deployment for this agent (by ``created_at``), "
                "including failed ones — handy for post-mortem on a deploy that just died."
            ),
        ),
        follow: bool = typer.Option(
            False, "--follow", "-f", help="Tail the log file and stream new output as it is written."
        ),
        tail: Optional[int] = typer.Option(
            None,
            "--tail",
            "-n",
            help="Print only the last N lines before exiting (or before following). Default: print full log.",
        ),
        path_only: bool = typer.Option(
            False,
            "--path",
            help="Print only the absolute log file path and exit (useful for scripting).",
        ),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """Show logs for an agent deployment.

        Reads the subprocess log file written by the local in-memory runner
        backend.  The log file location is the same convention the backend
        uses internally: ``nmp_user_data_dir() / 'agents' / 'system' /
        <deployment-name>.log`` by default.  This command is therefore only
        meaningful when the CLI runs on the same host as the platform — once
        a remote backend lands, log retrieval should move to a server-side
        endpoint.

        With ``--follow`` (``-f``), this command behaves like ``tail -f`` and
        streams new output until interrupted with Ctrl-C.
        """
        if tail is not None and tail <= 0:
            typer.echo("Error: --tail must be a positive integer.", err=True)
            raise typer.Exit(code=1)

        if not name and not agent:
            typer.echo("Error: provide a deployment name or --agent.", err=True)
            raise typer.Exit(code=1)

        if agent and not name:
            candidates = [
                d
                for d in _unwrap_list(
                    _api_request("GET", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments")
                )
                if d.get("agent") == agent and d.get("status") not in ("deleting",)
            ]
            if not candidates:
                typer.echo(f"Error: no deployment found for agent '{agent}'.", err=True)
                raise typer.Exit(code=1)
            # Pick the most recent by creation time so failed-and-immediately-
            # superseded deployments don't shadow the user's intent.  The
            # API serialises ``created_at`` as an ISO-8601 string; parse it
            # explicitly so the ordering is chronological even if Pydantic's
            # serialiser ever stops emitting zero-padded components.
            candidates.sort(key=_deployment_created_at_key)
            name = candidates[-1]["name"]

        # ``name`` is guaranteed non-None by the checks above; cast() narrows
        # the type without runtime overhead and survives ``python -O``.
        log_path = _agent_log_path_for(cast(str, name))
        if path_only:
            typer.echo(str(log_path))
            return

        if not log_path.exists():
            typer.echo(
                f"Error: log file does not exist on disk: {log_path}\n"
                "(The deployment may not have been spawned yet, the platform may be "
                "running on a different host, or the file was cleaned up.)",
                err=True,
            )
            raise typer.Exit(code=1)

        _print_log(log_path, tail=tail, follow=follow)

    @app.command(rich_help_panel="Agent Resources (requires running cluster)")
    def undeploy(
        name: Optional[str] = typer.Argument(None, help="Deployment name to remove."),
        agent: Optional[str] = typer.Option(
            None, "--agent", "--all", "-a", help="Remove all deployments for this agent."
        ),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    ) -> None:
        """Stop and remove a deployment (or all deployments for an agent)."""
        if name:
            if not yes:
                typer.confirm(f"Undeploy '{name}'?", abort=True)
            _api_request("DELETE", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments/{name}")
            typer.echo(f"Deployment '{name}' marked for deletion.")
        elif agent:
            deps = _unwrap_list(_api_request("GET", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments"))
            removed = [d for d in deps if d.get("agent") == agent]
            if not yes:
                typer.confirm(f"Undeploy {len(removed)} deployment(s) for agent '{agent}'?", abort=True)
            for d in removed:
                _api_request("DELETE", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments/{d['name']}")
            typer.echo(f"Marked {len(removed)} deployment(s) for agent '{agent}' for deletion.")
        else:
            typer.echo("Error: provide a deployment name or --agent.", err=True)
            raise typer.Exit(code=1)

    # deployments sub-group
    deps_app = typer.Typer(name="deployments", help="Manage agent deployments.", no_args_is_help=True)
    app.add_typer(deps_app, rich_help_panel="Agent Resources (requires running cluster)")

    @deps_app.command(name="list")
    def deployments_list(
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """List deployments."""
        resp = _api_request("GET", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments")
        typer.echo(json.dumps(resp, indent=2))

    @deps_app.command(name="get")
    def deployments_get(
        name: str = typer.Argument(..., help="Deployment name."),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """Get a deployment by name."""
        resp = _api_request("GET", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments/{name}")
        typer.echo(json.dumps(resp, indent=2))

    @deps_app.command(name="delete")
    def deployments_delete(
        name: str = typer.Argument(..., help="Deployment name."),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    ) -> None:
        """Delete a deployment by name."""
        if not yes:
            typer.confirm(f"Delete deployment '{name}'?", abort=True)
        _api_request("DELETE", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments/{name}")
        typer.echo(f"Deployment '{name}' marked for deletion.")

    @deps_app.command(name="wait")
    def deployments_wait(
        name: Optional[str] = typer.Argument(None, help="Deployment name to wait for."),
        agent: Optional[str] = typer.Option(
            None,
            "--agent",
            "-a",
            help="Wait for the latest active deployment of this agent (alternative to passing a name directly).",
        ),
        timeout: int = typer.Option(300, "--timeout", "-t", help="Maximum seconds to wait."),
        interval: float = typer.Option(2.0, "--interval", help="Poll interval in seconds."),
        workspace: str = typer.Option(_DEFAULT_WORKSPACE, "--workspace", "-w"),
        base_url: str = typer.Option(_DEFAULT_BASE_URL, "--base-url", envvar="NEMO_BASE_URL"),
    ) -> None:
        """Wait for a deployment to reach 'running' or 'failed' status.

        Polls the deployment until it is running (exit 0) or failed / timed out (exit 1).
        Prints a status line each time the status changes.

        Provide either a deployment name directly or --agent to resolve the
        latest active deployment for that agent automatically.
        """
        if not name and not agent:
            typer.echo("Error: provide a deployment name or --agent.", err=True)
            raise typer.Exit(code=1)

        if agent and not name:
            active = [
                d
                for d in _unwrap_list(
                    _api_request("GET", base_url, f"/apis/agents/v2/workspaces/{workspace}/deployments")
                )
                if d.get("agent") == agent and d.get("status") not in ("failed", "deleting")
            ]
            if not active:
                typer.echo(f"Error: no active deployment found for agent '{agent}'.", err=True)
                raise typer.Exit(code=1)
            name = active[-1]["name"]

        assert name  # guaranteed by the checks above
        success = _wait_for_deployment(base_url, workspace, name, timeout=timeout, interval=interval)
        raise typer.Exit(code=0 if success else 1)


# ---------------------------------------------------------------------------
# Deployment wait helper
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = {"running", "failed"}


def _wait_for_deployment(
    base_url: str,
    workspace: str,
    name: str,
    *,
    timeout: int = 300,
    interval: float = 2.0,
) -> bool:
    """Poll a deployment until it reaches a terminal status.

    Args:
        base_url: Platform base URL.
        workspace: Workspace the deployment belongs to.
        name: Deployment name.
        timeout: Maximum seconds to wait before giving up.
        interval: Seconds between polls.

    Returns:
        ``True`` if the deployment reached ``running``, ``False`` if it
        reached ``failed`` or the timeout expired.
    """
    path = f"/apis/agents/v2/workspaces/{workspace}/deployments/{name}"
    start = time.monotonic()
    last_status = ""

    typer.echo(f"Waiting for deployment '{name}' (timeout={timeout}s)...")

    while time.monotonic() - start < timeout:
        dep = _api_request("GET", base_url, path)
        status = dep.get("status", "")
        elapsed = int(time.monotonic() - start)

        if status != last_status:
            line = f"  [{elapsed:>4}s] status: {status}"
            if status == "failed" and dep.get("error"):
                line += f" — {dep['error']}"
            typer.echo(line)
            last_status = status

        if status == "running":
            typer.echo(f"Deployment '{name}' is running at {dep.get('endpoint', '?')}")
            return True

        if status == "failed":
            typer.echo(f"Deployment '{name}' failed.", err=True)
            return False

        time.sleep(interval)

    elapsed = int(time.monotonic() - start)
    typer.echo(f"Timeout after {elapsed}s. Last status: {last_status}", err=True)
    return False


# ---------------------------------------------------------------------------
# Log printing / tailing helper
# ---------------------------------------------------------------------------


def _agent_log_path_for(deployment_name: str) -> Path:
    """Return the absolute log-file path the runner backend uses for a deployment.

    Imports the convention from the runner module so the CLI and the running
    platform agree on layout without round-tripping a host-bound path
    through the public API surface.  Correct only for the in-memory backend
    on the same host as the CLI invoker.
    """
    from nemo_agents_plugin.runner.in_memory import log_path_for_deployment

    return log_path_for_deployment(deployment_name)


def _deployment_created_at_key(dep: dict[str, Any]) -> datetime:
    """Sort key for deployments — parses the API's ISO-8601 ``created_at``.

    Falls back to ``datetime.min`` when the field is missing or unparseable
    so a malformed entry sorts to the start (and the most recent valid
    deployment wins ``[-1]``).  ``datetime.fromisoformat`` accepts the
    Pydantic default serialisation (``2026-05-18T17:36:26.639200``).
    """
    raw = dep.get("created_at")
    if not isinstance(raw, str):
        return datetime.min
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.min


def _print_log(log_path: Path, *, tail: Optional[int] = None, follow: bool = False) -> None:
    """Print *log_path* to stdout, optionally tailing the last N lines or following.

    Implemented in pure Python (rather than shelling out to ``tail``) so the
    behaviour is identical on every host the platform may run on.  In
    ``follow`` mode the same file handle is reused across the read and the
    poll loop, so lines written between the two would not be lost.  The
    poll interval is 0.5s — plenty responsive for log review.
    """
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            if tail is not None and tail > 0:
                # Read whole file and emit only the trailing N lines.  Files
                # are typically small (single-process subprocess logs); a
                # streaming "real tail" would be premature optimisation.
                lines = fh.readlines()
                for line in lines[-tail:]:
                    typer.echo(line, nl=False)
            else:
                for line in fh:
                    typer.echo(line, nl=False)

            if not follow:
                return

            # Continue from EOF on the same handle so writes between the
            # initial read and the poll loop aren't dropped.
            fh.seek(0, os.SEEK_END)
            try:
                while True:
                    chunk = fh.read()
                    if chunk:
                        typer.echo(chunk, nl=False)
                    else:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                return
    except BrokenPipeError:
        # Consumer (e.g. ``| head -20``) closed the pipe early.  Exit
        # quietly instead of raising a traceback at the user.
        return


# ---------------------------------------------------------------------------
# Local execution helpers
# ---------------------------------------------------------------------------


def _local_invoke(
    agent_config: Path,
    input: Optional[str],
    input_file: Optional[Path],
    workspace: str = _DEFAULT_WORKSPACE,
    base_url: str = _DEFAULT_BASE_URL,
) -> None:
    """Invoke a NAT workflow locally via ``nat run`` and print the result.

    Injects the Inference Gateway URL into any LLMs that do not already have
    ``base_url`` set before spawning the subprocess, so agent configs that omit
    ``base_url`` route through the IGW automatically.

    Delegates to the ``nat run`` subprocess so this command works against the
    NAT CLI provided by the plugin's ``nvidia-nat-core`` dependency.
    """
    import subprocess

    from nemo_agents_plugin.utils import temp_injected_config

    if input_file:
        queries = json.loads(input_file.read_text(encoding="utf-8"))
        if not isinstance(queries, list):
            queries = [queries]
    elif input:
        queries = [input]
    else:
        typer.echo("Error: provide --input or --input-file.", err=True)
        raise typer.Exit(code=1)

    with temp_injected_config(agent_config, workspace, base_url=base_url) as injected_path:
        for query in queries:
            cmd = ["nat", "run", "--config_file", injected_path.name, "--input", query]
            try:
                subprocess.run(cmd, check=True, cwd=injected_path.parent)
            except subprocess.CalledProcessError as exc:
                typer.echo(f"Error: nat run exited with code {exc.returncode}.", err=True)
                raise typer.Exit(code=exc.returncode)
            except FileNotFoundError:
                typer.echo("Error: 'nat' command not found.  Install nvidia-nat-core.", err=True)
                raise typer.Exit(code=1)


def _platform_invoke(
    base_url: str,
    workspace: str,
    agent: Optional[str],
    deployment: Optional[str],
    input: Optional[str],
    input_file: Optional[Path],
) -> None:
    """Invoke an agent through the platform gateway."""
    if input_file:
        queries = json.loads(input_file.read_text(encoding="utf-8"))
        if not isinstance(queries, list):
            queries = [queries]
    elif input:
        queries = [input]
    else:
        typer.echo("Error: provide --input or --input-file.", err=True)
        raise typer.Exit(code=1)

    if agent:
        path = f"/apis/agents/v2/workspaces/{workspace}/agents/{agent}/-/v1/chat/completions"
    else:
        path = f"/apis/agents/v2/workspaces/{workspace}/deployments/{deployment}/-/v1/chat/completions"

    url = base_url.rstrip("/") + path
    for query in queries:
        payload = {"messages": [{"role": "user", "content": query}], "stream": False}
        try:
            timeout = float(os.environ.get("NEMO_AGENTS_INVOKE_TIMEOUT", "300"))
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                typer.echo(json.dumps(resp.json(), indent=2))
        except httpx.HTTPStatusError as exc:
            print_http_status_error(exc, action="invoke agent")
            raise typer.Exit(code=1)
        except httpx.RequestError as exc:
            print_http_request_error(exc, action="invoke agent")
            raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Platform API helpers
# ---------------------------------------------------------------------------


def _unwrap_list(resp: Any) -> list[dict[str, Any]]:
    """Extract the item list from a paginated or raw API response."""
    items = resp.get("data", resp) if isinstance(resp, dict) else resp
    return [d for d in items if isinstance(d, dict)]


def _api_request(method: str, base_url: str, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
    url = base_url.rstrip("/") + path
    request_kwargs: dict[str, Any] = {}
    if json_body is not None:
        request_kwargs["json"] = json_body
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.request(method, url, **request_kwargs)
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
    except httpx.HTTPStatusError as exc:
        print_http_status_error(exc, action=f"{method} agent API")
        raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        print_http_request_error(exc, action=f"{method} agent API")
        raise typer.Exit(code=1)


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# Mirrors ``nemo_agents_plugin.utils._ENV_VAR_PATTERN`` semantics: matches
# ``${NEMO_DEFAULT_MODEL}`` and bare ``$NEMO_DEFAULT_MODEL`` (with an
# identifier-boundary lookahead so ``$NEMO_DEFAULT_MODELX`` is not matched).
_DEFAULT_MODEL_PLACEHOLDER = re.compile(r"\$(?:\{NEMO_DEFAULT_MODEL\}|NEMO_DEFAULT_MODEL(?![A-Za-z0-9_]))")


def _contains_default_model_placeholder(value: Any) -> bool:
    """Return True if *value* still contains an unresolved ``NEMO_DEFAULT_MODEL`` reference."""
    if isinstance(value, str):
        # Honor ``$$`` escape the same way ``expand_env_vars`` does.
        protected = value.replace("$$", "\0DOLLAR\0")
        return _DEFAULT_MODEL_PLACEHOLDER.search(protected) is not None
    if isinstance(value, dict):
        return any(_contains_default_model_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_default_model_placeholder(v) for v in value)
    return False


# ---------------------------------------------------------------------------
# Improvement workflow commands — friendly flag-based wrappers around the
# evaluate-suite / analyze / optimize-skills NemoJobs.
#
# The auto-injected NemoJob forms (`evaluate-suite run --spec '{json}'`,
# etc.) are still available for platform dispatch.
# ---------------------------------------------------------------------------


def _load_config_file(path: Path | None) -> dict[str, Any]:
    """Load a YAML/JSON config file via the standard nemo-platform-plugin loader."""
    if path is None:
        return {}
    from nemo_platform_plugin.jobs._cli_options import load_spec_file

    return load_spec_file(path)


def _merge_with_overrides(file_data: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge file data + CLI overrides (CLI wins, but only when explicitly set)."""
    merged = dict(file_data)
    for k, v in overrides.items():
        if v is not None:
            merged[k] = v
    return merged


def _run_with_clean_errors(job_run, spec: dict[str, Any]) -> Any:
    """Execute a NemoJob's run() and surface PreflightError as a clean CLI error."""
    from nemo_agents_plugin.improvement.preflight import PreflightError

    try:
        return job_run(spec)
    except PreflightError as exc:
        typer.echo(f"\n[Preflight failed]\n{exc}", err=True)
        raise typer.Exit(code=1) from exc


def _register_improvement_commands(app: typer.Typer) -> None:
    """Register friendly flag-based commands for the agent-improvement workflow.

    All three commands accept ``--config <path.yml>`` (YAML or JSON) so users
    don't have to repeat 10+ flags every invocation. CLI flags override file
    values. File schema mirrors the underlying NemoJob's Pydantic config.

    Convention for this plugin: long-running interactive workflows (the loop,
    its eval-suite driver, and its analyzer) get individual flags plus an
    optional ``--config`` YAML; one-shot platform jobs (``evaluate`` /
    ``optimize`` registered in ``_register_platform_commands``) keep the
    auto-generated ``--spec '{...}'`` JSON form. New commands should pick the
    style that matches their usage shape, not split the difference.
    """

    @app.command(rich_help_panel="Improvement workflow")
    def evaluate_suite(
        config: Optional[Path] = typer.Option(
            None,
            "--config",
            "-c",
            help="YAML or JSON config file with all parameters.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
        evals: Optional[Path] = typer.Option(None, "--evals", help="Directory of eval tasks."),
        agent: Optional[Path] = typer.Option(None, "--agent", help="Agent root (defaults to cwd)."),
        runner: Optional[str] = typer.Option(None, "--runner", help="auto | harbor | nat"),
        prefer: Optional[str] = typer.Option(
            None, "--prefer", help="Tiebreaker when both markers present: harbor | nat"
        ),
        concurrency: Optional[int] = typer.Option(None, "--jobs", "-j", help="Parallel eval concurrency."),
        skip_build: Optional[bool] = typer.Option(None, "--skip-build", help="Skip docker build (Harbor only)."),
        output: Optional[Path] = typer.Option(
            None, "--output", "-o", help="Output dir (default: ./runs/batch-<timestamp>)."
        ),
        filter_glob: Optional[str] = typer.Option(None, "--filter", help="Glob filter on eval names."),
        repeats: Optional[int] = typer.Option(None, "--repeats", help="Trials per eval (median aggregation when >1)."),
    ) -> None:
        """Run an eval suite against an agent (Harbor or NAT runner)."""
        from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteJob

        overrides: dict[str, Any] = {
            "evals": str(evals.resolve()) if evals else None,
            "agent": str(agent.resolve()) if agent else None,
            "runner": runner,
            "prefer": prefer,
            "concurrency": concurrency,
            "skip_build": skip_build,
            "output": str(output.resolve()) if output else None,
            "filter_glob": filter_glob,
            "repeats": repeats,
        }
        spec = _merge_with_overrides(_load_config_file(config), overrides)
        if "evals" not in spec:
            typer.echo("Error: --evals is required (or set 'evals' in --config).", err=True)
            raise typer.Exit(code=1)
        if "agent" not in spec:
            spec["agent"] = str(Path.cwd())
        result = _run_with_clean_errors(EvaluateSuiteJob().run, spec)
        typer.echo(json.dumps(result, indent=2))

    @app.command(rich_help_panel="Improvement workflow")
    def analyze(
        config: Optional[Path] = typer.Option(
            None, "--config", "-c", help="YAML or JSON config file.", exists=True, file_okay=True, dir_okay=False
        ),
        batch: Optional[Path] = typer.Option(None, "--batch", help="Path to a batch directory."),
        output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format: md | json"),
        mechanical_only: Optional[bool] = typer.Option(None, "--mechanical-only", help="Skip the LLM analysis pass."),
    ) -> None:
        """Analyze a batch of eval-suite results (clusters, regressions, hypotheses)."""
        from nemo_agents_plugin.jobs.analyze_batch import AnalyzeBatchJob

        overrides: dict[str, Any] = {
            "batch": str(batch.resolve()) if batch else None,
            "format": output_format,
            "mechanical_only": mechanical_only,
        }
        spec = _merge_with_overrides(_load_config_file(config), overrides)
        if "batch" not in spec:
            typer.echo("Error: --batch is required (or set 'batch' in --config).", err=True)
            raise typer.Exit(code=1)
        result = _run_with_clean_errors(AnalyzeBatchJob().run, spec)
        if isinstance(result, dict) and "report" in result:
            print(result["report"])
        else:
            typer.echo(json.dumps(result, indent=2))

    @app.command(name="optimize-skills", rich_help_panel="Improvement workflow")
    def optimize_skills(
        config: Optional[Path] = typer.Option(
            None,
            "--config",
            "-c",
            help="YAML or JSON config file with all parameters.",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
        evals: Optional[Path] = typer.Option(None, "--evals", help="Directory of eval tasks."),
        agent: Optional[Path] = typer.Option(None, "--agent", help="Agent root (defaults to cwd)."),
        skills_path: Optional[str] = typer.Option(
            None, "--skills-path", help="Relative path inside agent where skills live."
        ),
        filter_glob: Optional[str] = typer.Option(None, "--filter", help="Glob filter on eval names."),
        iterations: Optional[int] = typer.Option(None, "--iterations", "-n", help="Max loop iterations."),
        concurrency: Optional[int] = typer.Option(None, "--jobs", "-j", help="Parallel eval concurrency."),
        repeats: Optional[int] = typer.Option(None, "--repeats", help="Trials per eval (median aggregation when >1)."),
        state: Optional[Path] = typer.Option(
            None, "--state", help="Path to loop_state.json (default: <agent>/loop_state.json)."
        ),
        initial_batch: Optional[Path] = typer.Option(None, "--initial-batch", help="Existing batch dir to seed from."),
        full_verification: Optional[bool] = typer.Option(
            None, "--full-verification", help="Re-run ALL evals on each verification."
        ),
        open_pr: Optional[bool] = typer.Option(
            None, "--open-pr", help="Auto-open a GitLab MR via glab on improvement."
        ),
        analyze_only: Optional[bool] = typer.Option(
            None,
            "--analyze-only",
            help=(
                "Consume --initial-batch, generate suggestions, exit. "
                "Skips apply, verification, and MR creation. Works with any AUT."
            ),
        ),
    ) -> None:
        """Optimize agent skills against eval failures via a coding agent (Claude)."""
        from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsJob

        overrides: dict[str, Any] = {
            "evals": str(evals.resolve()) if evals else None,
            "agent": str(agent.resolve()) if agent else None,
            "skills_path": skills_path,
            "filter_glob": filter_glob,
            "iterations": iterations,
            "concurrency": concurrency,
            "repeats": repeats,
            "state": str(state.resolve()) if state else None,
            "initial_batch": str(initial_batch.resolve()) if initial_batch else None,
            "full_verification": full_verification,
            "open_pr": open_pr,
            "analyze_only": analyze_only,
        }
        spec = _merge_with_overrides(_load_config_file(config), overrides)
        if spec.get("analyze_only") and not spec.get("initial_batch"):
            typer.echo(
                "Error: --analyze-only requires --initial-batch pointing at an existing batch directory.",
                err=True,
            )
            raise typer.Exit(code=1)
        if "evals" not in spec:
            typer.echo("Error: --evals is required (or set 'evals' in --config).", err=True)
            raise typer.Exit(code=1)
        if "agent" not in spec:
            spec["agent"] = str(Path.cwd())
        result = _run_with_clean_errors(OptimizeSkillsJob().run, spec)
        typer.echo(json.dumps(result, indent=2))
