# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``nemo iron-swarm ...`` commands — registered under ``nemo.cli``.

iron-swarm is never imported: it runs in its own venv, invoked by subprocess. Commands delegate
to the sibling modules (:mod:`checks`, :mod:`provisioning`, :mod:`credentials`, :mod:`client`);
each command's docstring is its ``--help`` text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
import yaml
from nemo_iron_swarm_plugin.agent_resolver import AgentResolutionError, resolve_agent_to_manifest
from nemo_iron_swarm_plugin.cli import checks, credentials, provisioning
from nemo_iron_swarm_plugin.cli.client import base_url, make_sdk
from nemo_iron_swarm_plugin.config import IronSwarmConfig, missing_secrets
from nemo_iron_swarm_plugin.entities import IRON_SWARM_MANIFEST_TYPE, IronSwarmManifest
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
            agent: str = typer.Option(
                ..., "--agent", help="Deployed NeMo Platform agent to target (name or workspace/name)."
            ),
            name: str | None = typer.Option(
                None, "--name", help="Saved-manifest name (the id later phases reference). Defaults to the agent name."
            ),
            workspace: str | None = typer.Option(None, "--workspace", help="Agent workspace."),
            output: str = typer.Option("iron-swarm.yaml", "--output", "-o", help="Manifest path."),
            project_dir: str | None = typer.Option(
                None, "--project-dir", help="NAT project dir (required only for agents with custom components)."
            ),
        ) -> None:
            """Scaffold an iron-swarm manifest from a deployed agent and save it as a reusable manifest."""
            ctx = _command_context(workspace)
            sdk = ctx.sdk
            ws = ctx.workspace
            out_path = Path(output)
            manifest_dir = out_path.parent
            try:
                resolved = resolve_agent_to_manifest(
                    agent,
                    sdk=sdk,
                    base_url=ctx.base_url,
                    default_workspace=ws,
                    manifest_dir=manifest_dir,
                    project_dir=project_dir,
                )
            except AgentResolutionError as exc:
                typer.secho(f"Error: {exc}", fg="red")
                raise typer.Exit(code=1) from exc

            manifest_yaml = yaml.safe_dump(resolved.manifest, sort_keys=False)
            out_path.write_text(manifest_yaml, encoding="utf-8")
            for warning in resolved.warnings:
                typer.secho(f"  ! {warning}", fg="yellow")
            typer.secho(f"Wrote {out_path}", fg="green")
            typer.echo(
                f"  agent     {resolved.workspace}/{resolved.agent_name}\n"
                f"  victim    port {resolved.port}\n"
                f"  workflow  {resolved.workflow_path}\n"
                f"  secrets   {', '.join(resolved.secrets)}"
            )

            # Persist the manifest as a saved entity so `synth-benign` and `run` can reference it by name
            # and share the cached benign suite (mirrors Studio's POST /manifests).
            entity = IronSwarmManifest.from_agent_resolution(
                name=name or resolved.agent_name,
                workspace=ws,
                agent_ref=f"{resolved.workspace}/{resolved.agent_name}",
                manifest_yaml=manifest_yaml,
                port=resolved.port,
                secrets=resolved.secrets,
                warnings=resolved.warnings,
            )
            try:
                sdk.entities.create(
                    IRON_SWARM_MANIFEST_TYPE, workspace=ws, data=entity._get_data_fields(), name=entity.name
                )
            except Exception as exc:
                typer.secho(
                    f"  ! could not save manifest '{entity.name}' ({exc}); "
                    f"the local {out_path} still works with `run --config`.",
                    fg="yellow",
                )
                raise typer.Exit(code=1) from exc
            typer.secho(f"Saved manifest '{entity.name}'", fg="green")
            typer.echo(f"\nNext: nemo iron-swarm synth-benign --manifest-id {entity.name}")

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
