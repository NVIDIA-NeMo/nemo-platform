# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``nemo iron-swarm doctor | setup | init | refresh | status`` — host provisioning and target lifecycle.

iron-swarm is never imported: it runs in its own venv, invoked by subprocess.
"""

from __future__ import annotations

from pathlib import Path

import typer
from nemo_iron_swarm_plugin.cli import checks, credentials, provisioning
from nemo_iron_swarm_plugin.cli._shared import (
    command_context,
    models_from_flags,
    parse_env_pairs,
    preflight_models,
)
from nemo_iron_swarm_plugin.config import IronSwarmConfig


def register(app: typer.Typer) -> None:
    """Attach the provisioning and target-lifecycle commands to *app*."""

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
                f"\nStill needed: {', '.join(failed)}. Follow the hints above, then re-run `nemo iron-swarm doctor`.",
                fg="yellow",
            )
            raise typer.Exit(code=1)
        typer.secho("\nSetup complete. Next: nemo iron-swarm init --agent <name>", fg="green")

    @app.command()
    def init(
        agent: str = typer.Option(
            ..., "--agent", help="Registered NeMo Platform agent to war-game (name or workspace/name)."
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
        secrets: list[str] = typer.Option(None, "--secrets", help="Override the derived secret names (repeatable)."),
        env: list[str] = typer.Option(
            None,
            "--env",
            help="Non-secret env var for the victim as KEY=VALUE, repeatable. Credentials belong in "
            "--secrets, which names them and resolves values from the platform Secrets store.",
        ),
        port: int | None = typer.Option(None, "--port", help="Victim port (default: the agent's deployment port)."),
        attack_model: str | None = typer.Option(
            None, "--attack-model", help="Default model for garak's red-team + detector."
        ),
        attack_base_url: str | None = typer.Option(
            None, "--attack-base-url", help="Custom OpenAI-compatible endpoint for the attack model."
        ),
        attack_key_secret: str | None = typer.Option(
            None, "--attack-key-secret", help="Secrets-store name holding the attack endpoint's API key."
        ),
        analysis_model: str | None = typer.Option(
            None, "--analysis-model", help="Default model for the defenders and the benign validator."
        ),
        analysis_base_url: str | None = typer.Option(
            None, "--analysis-base-url", help="Custom OpenAI-compatible endpoint for the analysis model."
        ),
        analysis_key_secret: str | None = typer.Option(
            None, "--analysis-key-secret", help="Secrets-store name holding the analysis endpoint's API key."
        ),
        safety_model: str | None = typer.Option(
            None,
            "--safety-model",
            help="Default model the generated guardrail uses to screen traffic. Unset reuses the agent's own.",
        ),
        assume_yes: bool = typer.Option(
            False, "--yes", "-y", help="Accept iron-swarm's detected answers instead of being prompted."
        ),
    ) -> None:
        """Save a reusable war-game target from a registered agent.

        Resolution happens server-side — the same path Studio takes — so the manifest a CLI user
        gets and the one Studio gets are produced by one code path.
        """
        ctx = command_context(workspace)
        body: dict[str, object] = {"name": name or str(agent).split("/")[-1], "agent": agent}
        if port:
            body["port"] = port
        if egress:
            body["egress"] = list(egress)
        if secrets:
            body["secrets"] = list(secrets)
        if env:
            body["env"] = parse_env_pairs(list(env))
        # No merge here, unlike `manifest set`: nothing is stored yet, so these are the initial selection.
        models = models_from_flags(
            attack_model=attack_model,
            attack_base_url=attack_base_url,
            attack_key_secret=attack_key_secret,
            analysis_model=analysis_model,
            analysis_base_url=analysis_base_url,
            analysis_key_secret=analysis_key_secret,
            safety_model=safety_model,
        )
        if models:
            preflight_models(ctx, models)
            body["models"] = models
        try:
            manifest = ctx.sdk.iron_swarm.manifests.create(workspace=ctx.workspace, **body)
        except Exception as exc:
            typer.secho(f"Error: could not create manifest — {exc}", fg="red")
            raise typer.Exit(code=1) from exc

        for warning in manifest.get("warnings") or []:
            typer.secho(f"  ! {warning}", fg="yellow")
        manifest_name = str(manifest.get("name") or body["name"])
        typer.secho(f"Saved manifest '{manifest_name}'", fg="green")
        source = manifest.get("agent") or "?"
        image = manifest.get("dockerfile") or "(generic, built from the project)"
        typer.echo(
            f"  source    {source}\n"
            f"  image     {image}\n"
            f"  workflow  {manifest.get('workflow') or '(none)'}\n"
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
        ctx = command_context(workspace, preflight=False)
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

    @app.command()
    def status(
        workspace: str | None = typer.Option(None, "--workspace", help="Workspace to read runs from."),
        limit: int = typer.Option(5, "--limit", help="How many recent runs to show."),
    ) -> None:
        """Show recent Iron Swarm runs."""
        # No preflight: reading run records doesn't need Docker/OpenShell/the venvs.
        ctx = command_context(workspace, preflight=False)
        ws = ctx.workspace
        runs = ctx.sdk.iron_swarm.runs.list(workspace=ws, limit=limit)
        if not runs:
            typer.echo(f"No Iron Swarm runs in workspace '{ws}'.")
            return
        for record in runs:
            mark = typer.style("✓", fg="green") if record.get("status") == "completed" else typer.style("✗", fg="red")
            typer.echo(
                f"  {mark} {record.get('created_at', '?')}  {record.get('agent', '?')}  "
                f"{record.get('status', '?')} (exit {record.get('returncode', '?')})  [{record.get('name', '')}]"
            )
