# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``nemo iron-swarm ...`` commands — registered under ``nemo.cli``.

iron-swarm is never imported: it runs in its own venv, invoked by subprocess. Commands delegate
to the sibling modules (:mod:`checks`, :mod:`provisioning`, :mod:`credentials`, :mod:`client`);
each command's docstring is its ``--help`` text.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from nemo_iron_swarm_plugin.cli import checks, credentials, provisioning
from nemo_iron_swarm_plugin.cli.client import base_url, make_sdk
from nemo_iron_swarm_plugin.config import IronSwarmConfig, missing_secrets
from nemo_iron_swarm_plugin.filesets import upload_project_dir
from nemo_iron_swarm_plugin.jobs.defenses import defense_ids, select_defense_ids
from nemo_platform_plugin.cli import NemoCLI


@dataclass(frozen=True)
class _CommandContext:
    """Resolved preamble every SDK-backed command needs."""

    config: IronSwarmConfig
    sdk: Any
    base_url: str
    workspace: str


def _command_context(workspace: str | None, *, preflight: bool = True) -> _CommandContext:
    """Shared command preamble: config, host preflight, SDK client, resolved workspace.

    Making *preflight* an explicit argument keeps the "which commands gate on host readiness"
    policy one decision instead of one per command.
    """
    config = IronSwarmConfig.get()
    if preflight:
        checks.require_preflight(config)
    url = base_url()
    return _CommandContext(
        config=config,
        sdk=make_sdk(url),
        base_url=url,
        workspace=workspace or config.default_workspace,
    )


def _parse_env_pairs(pairs: list[str]) -> dict[str, str]:
    """Parse repeated ``KEY=VALUE`` flags into a dict, failing loudly on a malformed pair."""
    env: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            typer.secho(f"Error: --env expects KEY=VALUE, got {pair!r}.", fg="red")
            raise typer.Exit(code=1)
        env[key] = value
    return env


def _project_init_body(
    ctx: _CommandContext,
    project_dir: Path,
    *,
    name: str | None,
    workflow: str | None,
    port: int | None,
    egress: list[str],
    secrets: list[str],
    assume_yes: bool,
) -> dict[str, object]:
    """Run iron-swarm's own ``init`` on a local project, then upload it and return the create body.

    Delegating to the local binary keeps iron-swarm the single owner of both the detection and the
    questions it asks — the operator answers them at their terminal, which the server-side path
    (``init --yes`` behind an HTTP request) structurally cannot offer. The platform then stores the
    manifest iron-swarm produced instead of rebuilding it.
    """
    if not project_dir.is_dir():
        typer.secho(f"Error: {project_dir} is not a directory.", fg="red")
        raise typer.Exit(code=1)

    manifest_name = name or project_dir.resolve().name
    with tempfile.TemporaryDirectory() as tmp:
        rendered = Path(tmp) / "iron-swarm.yaml"
        # `--project-dir .` with cwd set mirrors the server, so the stored manifest is path-independent.
        cmd = [
            str(ctx.config.iron_swarm_bin),
            "init",
            "--force",
            "--project-dir",
            ".",
            "--name",
            manifest_name,
            "-o",
            str(rendered),
        ]
        if assume_yes:
            cmd.append("--yes")
        if workflow:
            cmd += ["--workflow", workflow]
        if port:
            cmd += ["--port", str(port)]
        if secrets:
            cmd += ["--secrets", ",".join(secrets)]
        for host in egress:
            cmd += ["--egress", host]
        provisioning.run_subprocess(
            cmd, "build the manifest with `iron-swarm init`", cwd=str(project_dir), timeout=None
        )
        if not rendered.is_file():
            typer.secho("Error: `iron-swarm init` produced no manifest.", fg="red")
            raise typer.Exit(code=1)
        manifest_yaml = rendered.read_text(encoding="utf-8")

    try:
        fileset = upload_project_dir(ctx.sdk, project_dir, workspace=ctx.workspace)
    except Exception as exc:
        typer.secho(f"Error: could not upload {project_dir} — {exc}", fg="red")
        raise typer.Exit(code=1) from exc
    typer.echo(f"Uploaded {project_dir} as {fileset}")

    return {
        "name": manifest_name,
        "source_type": "project",
        "project_fileset": fileset,
        "manifest_yaml": manifest_yaml,
    }


class IronSwarmCLI(NemoCLI):
    """Exposes plugin commands as ``nemo iron-swarm ...``."""

    name = "iron-swarm"
    description = "Red-team and harden deployed NAT agents with Iron Swarm."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True, add_completion=False)

        # ── doctor ────────────────────────────────────────────────────
        @app.command()
        def doctor() -> None:
            """Read-only preflight: iron-swarm venv, garak venv, Docker daemon, OpenShell gateway."""
            config = IronSwarmConfig.get()
            typer.echo("Iron Swarm preflight:")
            results = checks.run_checks(config)
            checks.print_checks(results)
            if all(check.ok for check in results):
                typer.secho("\nAll checks passed.", fg="green")
                return
            typer.secho("\nSome checks failed — run `nemo iron-swarm setup`.", fg="yellow")
            raise typer.Exit(code=1)

        # ── setup ─────────────────────────────────────────────────────
        @app.command()
        def setup(
            force: bool = typer.Option(False, "--force", "-f", help="Recreate the venv even if it already exists."),
        ) -> None:
            """Provision iron-swarm's venv, the garak venv, and the inference credential, then check prereqs.

            iron-swarm's setup registers the OpenShell gateway (best-effort). Docker and the
            OpenShell CLI/service install stay instructed — they need sudo/brew and are unreliable
            under a sandbox.
            """
            config = IronSwarmConfig.get()
            provisioning.provision_venv(config, force=force)
            provisioning.run_iron_swarm_setup(config, force=force)
            credentials.provision_operator_env(config, force=force)

            typer.echo("\nChecking host prerequisites:")
            results = checks.run_checks(config)
            checks.print_checks(results)
            failed = [check.label for check in results if not check.ok]
            if failed:
                typer.secho(
                    f"\nStill needed: {', '.join(failed)}. Follow the hints above, then re-run "
                    "`nemo iron-swarm doctor`.",
                    fg="yellow",
                )
                raise typer.Exit(code=1)
            typer.secho("\nSetup complete. Next: nemo iron-swarm init --agent <name>", fg="green")

        # ── init ──────────────────────────────────────────────────────
        @app.command()
        def init(
            agent: str | None = typer.Option(
                None, "--agent", help="Deployed NeMo Platform agent to target (name or workspace/name)."
            ),
            name: str | None = typer.Option(
                None, "--name", help="Saved-manifest name (the id later phases reference). Defaults to the agent name."
            ),
            workspace: str | None = typer.Option(None, "--workspace", help="Agent workspace."),
            output: str = typer.Option("iron-swarm.yaml", "--output", "-o", help="Where to write the rendered YAML."),
            egress: list[str] = typer.Option(
                None,
                "--egress",
                help="Host[:port] the victim may reach, repeatable. A bare host opens 443 only — add "
                "'host:80' for plain HTTP. Config-only agents need this; their tool hosts can't be discovered.",
            ),
            secrets: list[str] = typer.Option(
                None, "--secrets", help="Override the derived secret names (repeatable)."
            ),
            env: list[str] = typer.Option(
                None,
                "--env",
                help="Non-secret env var for the victim as KEY=VALUE, repeatable. Credentials belong in "
                "--secrets, which names them and resolves values from the platform Secrets store.",
            ),
            project_dir: str | None = typer.Option(
                None, "--project-dir", help="Local NAT project to upload and war-game (alternative to --agent)."
            ),
            workflow: str | None = typer.Option(
                None, "--workflow", help="Workflow path within the project (project source; default: detected)."
            ),
            port: int | None = typer.Option(None, "--port", help="Victim port (project source; default: detected)."),
            assume_yes: bool = typer.Option(
                False, "--yes", "-y", help="Accept iron-swarm's detected answers instead of being prompted."
            ),
        ) -> None:
            """Save a reusable war-game target: a deployed agent (--agent) or a NAT project (--project-dir).

            --agent resolves server-side, the path Studio also takes. --project-dir runs iron-swarm's
            own interactive init here, so you answer its questions, then uploads the project and
            stores the manifest it produced.
            """
            if bool(agent) == bool(project_dir):
                typer.secho("Error: pass exactly one of --agent or --project-dir.", fg="red")
                raise typer.Exit(code=1)

            ctx = _command_context(workspace)
            body: dict[str, object]
            if project_dir:
                body = _project_init_body(
                    ctx,
                    Path(project_dir),
                    name=name,
                    workflow=workflow,
                    port=port,
                    egress=list(egress or []),
                    secrets=list(secrets or []),
                    assume_yes=assume_yes,
                )
            else:
                body = {"name": name or str(agent).split("/")[-1], "source_type": "agent", "agent": agent}
                if port:
                    body["port"] = port
            if egress:
                body["egress"] = list(egress)
            if secrets:
                body["secrets"] = list(secrets)
            if env:
                body["env"] = _parse_env_pairs(list(env))
            try:
                manifest = ctx.sdk.iron_swarm.manifests.create(workspace=ctx.workspace, **body)
            except Exception as exc:
                typer.secho(f"Error: could not create manifest — {exc}", fg="red")
                raise typer.Exit(code=1) from exc

            for warning in manifest.get("warnings") or []:
                typer.secho(f"  ! {warning}", fg="yellow")
            manifest_name = str(manifest.get("name") or body["name"])
            typer.secho(f"Saved manifest '{manifest_name}'", fg="green")
            source = manifest.get("agent") or manifest.get("project_fileset") or "?"
            typer.echo(
                f"  source    {source}\n"
                f"  victim    port {manifest.get('port', '?')}\n"
                f"  secrets   {', '.join(manifest.get('secrets') or [])}\n"
                f"  egress    {', '.join(manifest.get('egress') or []) or '(none — outbound calls are blocked)'}"
            )

            # Runnable, not just readable: `run --config` takes this file. Prefer
            # `run --manifest-id`, which uses the stored manifest and its frozen target fileset.
            if manifest.get("manifest_yaml"):
                out_path = Path(output)
                out_path.write_text(
                    f"# Rendered from manifest '{manifest_name}'.\n"
                    f"# Runnable with `run --config {output}`; `run --manifest-id {manifest_name}` "
                    f"uses the stored manifest instead.\n"
                    f"{manifest['manifest_yaml']}",
                    encoding="utf-8",
                )
                typer.echo(f"  rendered  {out_path}")
            typer.echo(f"\nNext: nemo iron-swarm synth-benign --manifest-id {manifest_name}")

        # ── run ───────────────────────────────────────────────────────
        @app.command()
        def run(
            config_file: str | None = typer.Option(
                None, "--config", "-c", help="Local manifest produced by `init` (default: iron-swarm.yaml)."
            ),
            manifest_id: str | None = typer.Option(
                None, "--manifest-id", help="Saved manifest to run (reuses its cached benign suite)."
            ),
            env_file: str | None = typer.Option(None, "--env-file", help="Dotenv with the agent's secrets."),
            workspace: str | None = typer.Option(None, "--workspace", help="Workspace for the run."),
            benign_suite: str | None = typer.Option(
                None,
                "--benign-suite",
                help="Benign-suite CSV (tool,payload,label,rationale,persona) to use as-is, overriding the cache.",
            ),
        ) -> None:
            """Run the attack/defend/validate war-game against a local manifest or a saved manifest."""
            ctx = _command_context(workspace)
            if config_file and manifest_id:
                typer.secho("Pass either --config or --manifest-id, not both.", fg="red")
                raise typer.Exit(code=1)
            if benign_suite and not Path(benign_suite).is_file():
                typer.secho(f"Benign suite CSV {benign_suite} not found.", fg="red")
                raise typer.Exit(code=1)

            # The saved-manifest path materializes server-side and checks victim secrets in the job; the
            # local-file path validates the manifest exists and its secrets are satisfiable up front.
            if not manifest_id:
                config_file = config_file or "iron-swarm.yaml"
                if not Path(config_file).exists():
                    typer.secho(
                        f"Manifest {config_file} not found — run `nemo iron-swarm init --agent <name>` first.",
                        fg="red",
                    )
                    raise typer.Exit(code=1)
                env_files = [ctx.config.operator_env_file] + ([Path(env_file)] if env_file else [])
                missing = missing_secrets(Path(config_file), env_files=env_files)
                if missing:
                    typer.secho(
                        f"Missing required secrets: {', '.join(missing)}. Provide them via --env-file "
                        "or export them, then re-run.",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

            result = ctx.sdk.iron_swarm.run(
                config=config_file,
                manifest_id=manifest_id,
                env_file=env_file,
                workspace=ctx.workspace,
                benign_suite=benign_suite,
            )
            typer.echo(json.dumps(result, indent=2, default=str))
            raise typer.Exit(code=0 if result.get("status") == "completed" else 1)

        # ── synth-benign ──────────────────────────────────────────────
        @app.command(name="synth-benign")
        def synth_benign(
            manifest_id: str = typer.Option(..., "--manifest-id", help="Saved manifest to synthesize a suite for."),
            env_file: str | None = typer.Option(None, "--env-file", help="Dotenv with the agent's secrets."),
            yes: bool = typer.Option(
                False, "--yes", "-y", help="Run the interview but auto-accept each recommended default (no prompts)."
            ),
            no_interactive: bool = typer.Option(
                False, "--no-interactive", help="Skip the interview entirely (leaner, rules-only suite; use in CI)."
            ),
            workspace: str | None = typer.Option(None, "--workspace", help="Workspace of the manifest."),
        ) -> None:
            """Synthesize the benign request suite for a saved manifest and cache it on the manifest.

            Brings the victim sandbox up, runs iron-swarm's interview/review (interactive by default), then
            tears it down — the reviewed suite is stored on the manifest so a later `run --manifest-id` reuses it.
            """
            ctx = _command_context(workspace)
            if yes and no_interactive:
                typer.secho("Pass either --yes or --no-interactive, not both.", fg="red")
                raise typer.Exit(code=1)
            interview = "skip" if no_interactive else "auto" if yes else "interactive"

            result = ctx.sdk.iron_swarm.synth_benign(
                manifest_id=manifest_id,
                env_file=env_file,
                interview=interview,
                workspace=ctx.workspace,
            )
            if result.get("status") == "completed":
                typer.secho(
                    f"Cached {result.get('suite_size', 0)} benign requests on manifest '{manifest_id}'.", fg="green"
                )
                typer.echo(f"\nNext: nemo iron-swarm run --manifest-id {manifest_id}")
                raise typer.Exit(code=0)
            typer.echo(json.dumps(result, indent=2, default=str))
            raise typer.Exit(code=1)

        # ── sanity-check ──────────────────────────────────────────────
        @app.command(name="sanity-check")
        def sanity_check(
            manifest_id: str = typer.Option(..., "--manifest-id", help="Saved manifest to validate against."),
            mitigations_file: str = typer.Option(
                ..., "--mitigations", help="Path to the run's mitigations.json (its 'defenses' list is selected from)."
            ),
            replay_hitlog: str = typer.Option(
                ...,
                "--replay-hitlog",
                help="Fileset ref of the recorded garak hitlog to replay (run's hitlog_fileset).",
            ),
            keep: list[str] = typer.Option(
                None,
                "--keep",
                help="Defense id to keep (repeatable). Default: keep all. Mutually exclusive with --exclude.",
            ),
            exclude: list[str] = typer.Option(None, "--exclude", help="Defense id to drop (repeatable)."),
            env_file: str | None = typer.Option(None, "--env-file", help="Dotenv with the agent's secrets."),
            workspace: str | None = typer.Option(None, "--workspace", help="Workspace for the run."),
        ) -> None:
            """Freeze a chosen subset of a run's recommended defenses and replay the recorded attacks + benign.

            Runs the war-game cycle one last time with the mitigation-generating defenders disabled and the
            chosen defenses frozen as the victim baseline — a sanity check that reports which attacks the
            selection blocks and which benign requests it wrongly blocks (false positives). Get the
            ``mitigations.json`` and the hitlog fileset ref from a completed run (`nemo iron-swarm status`).
            """
            ctx = _command_context(workspace)
            if keep and exclude:
                typer.secho("Pass either --keep or --exclude, not both.", fg="red")
                raise typer.Exit(code=1)
            path = Path(mitigations_file)
            if not path.exists():
                typer.secho(f"Mitigations file {mitigations_file} not found.", fg="red")
                raise typer.Exit(code=1)
            mitigations = json.loads(path.read_text(encoding="utf-8"))
            selected = select_defense_ids(defense_ids(mitigations), keep=keep or None, exclude=exclude or None)
            typer.echo(f"Sanity-checking {len(selected)} defense(s): {', '.join(selected) or '(none)'}")

            result = ctx.sdk.iron_swarm.sanity_check(
                manifest_id=manifest_id,
                mitigations=mitigations,
                selected_defense_ids=selected,
                replay_hitlog_fileset=replay_hitlog,
                env_file=env_file,
                workspace=ctx.workspace,
            )
            typer.echo(json.dumps(result, indent=2, default=str))

        # ── refresh ───────────────────────────────────────────────────
        @app.command()
        def refresh(
            manifest_id: str = typer.Option(..., "--manifest-id", help="Saved manifest to re-resolve."),
            workspace: str | None = typer.Option(None, "--workspace", help="Workspace of the manifest."),
        ) -> None:
            """Re-resolve a saved manifest against its agent as it is now.

            A manifest is a frozen target, so editing the agent — new model, new tool, redeploy —
            does not change it on its own. Run this to take those changes deliberately. Your egress,
            secrets, models, defenders and cached benign suite are kept.
            """
            ctx = _command_context(workspace, preflight=False)
            try:
                manifest = ctx.sdk.iron_swarm.manifests.refresh(manifest_id, workspace=ctx.workspace)
            except Exception as exc:
                typer.secho(f"Error: could not refresh manifest '{manifest_id}' — {exc}", fg="red")
                raise typer.Exit(code=1) from exc

            for warning in manifest.get("warnings") or []:
                typer.secho(f"  ! {warning}", fg="yellow")
            typer.secho(f"Refreshed manifest '{manifest_id}' from {manifest.get('agent', '?')}", fg="green")
            typer.echo(
                f"  victim    port {manifest.get('port', '?')}\n"
                f"  secrets   {', '.join(manifest.get('secrets') or [])}\n"
                f"  egress    {', '.join(manifest.get('egress') or []) or '(none — outbound calls are blocked)'}"
            )

        # ── status ────────────────────────────────────────────────────
        @app.command()
        def status(
            workspace: str | None = typer.Option(None, "--workspace", help="Workspace to read runs from."),
            limit: int = typer.Option(5, "--limit", help="How many recent runs to show."),
        ) -> None:
            """Show recent Iron Swarm runs."""
            # No preflight: reading run records doesn't need Docker/OpenShell/the venvs.
            ctx = _command_context(workspace, preflight=False)
            ws = ctx.workspace
            runs = ctx.sdk.iron_swarm.runs.list(workspace=ws, limit=limit)
            if not runs:
                typer.echo(f"No Iron Swarm runs in workspace '{ws}'.")
                return
            for record in runs:
                mark = (
                    typer.style("✓", fg="green") if record.get("status") == "completed" else typer.style("✗", fg="red")
                )
                typer.echo(
                    f"  {mark} {record.get('created_at', '?')}  {record.get('agent', '?')}  "
                    f"{record.get('status', '?')} (exit {record.get('returncode', '?')})  [{record.get('name', '')}]"
                )

        return app
