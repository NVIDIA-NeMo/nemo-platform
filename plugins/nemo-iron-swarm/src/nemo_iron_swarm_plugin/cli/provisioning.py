# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Provision the two userspace venvs `nemo iron-swarm setup` needs.

iron-swarm's own venv (installed via uv), and the separate garak venv its agent_breaker spawns
(delegated to iron-swarm's own ``setup``, which owns the garak version pin).
"""

from __future__ import annotations

import os
import shutil
import subprocess

import typer
from nemo_iron_swarm_plugin.cli.checks import redact_index_url
from nemo_iron_swarm_plugin.config import GARAK_PYTHON_ENVVAR, IronSwarmConfig

# `uv pip install` pulls torch-sized wheels; generous enough for a cold cache on a slow link, but
# bounded so a hung download fails with a message instead of blocking setup forever.
SUBPROCESS_TIMEOUT_SECONDS = 900


def run_subprocess(
    cmd: list[str],
    action: str,
    env: dict[str, str] | None = None,
    *,
    cwd: str | None = None,
    timeout: int | None = SUBPROCESS_TIMEOUT_SECONDS,
) -> None:
    """Run *cmd* with its output streamed to the terminal, exiting with *action* context on failure.

    Output is inherited rather than captured: these are multi-minute installs, and swallowing uv's
    progress makes setup look hung. It also means both stdout and stderr reach the operator — uv
    reports some failures on stdout. Inherited stdio also lets an interactive child prompt the
    operator, which is why *timeout* accepts ``None`` (a person deciding is not a hung command).
    """
    try:
        proc = subprocess.run(cmd, check=False, env=env, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        typer.secho(f"Timed out after {timeout}s trying to {action} — the command made no progress.", fg="red")
        raise typer.Exit(code=1) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        typer.secho(f"Failed to {action}: {exc}", fg="red")
        raise typer.Exit(code=1) from exc
    if proc.returncode != 0:
        typer.secho(f"Failed to {action} (exit {proc.returncode}) — see the output above.", fg="red")
        raise typer.Exit(code=1)


def provision_venv(config: IronSwarmConfig, *, force: bool) -> None:
    """Create iron-swarm's dedicated venv and install iron-swarm into it via uv."""
    if shutil.which("uv") is None:
        typer.secho("uv not found — install it (https://docs.astral.sh/uv/) then re-run setup.", fg="red")
        raise typer.Exit(code=1)

    if config.iron_swarm_bin.exists() and not force:
        typer.echo(f"iron-swarm venv already present at {config.venv_path} (use --force to recreate).")
        return

    config.venv_path.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Creating iron-swarm venv at {config.venv_path} ...")
    run_subprocess(["uv", "venv", "--python", "3.12", str(config.venv_path)], "create venv")

    typer.echo(f"Installing {config.iron_swarm_spec} into the venv ...")
    install_cmd = ["uv", "pip", "install", "--python", str(config.venv_path / "bin" / "python")]
    # Both flags are passed on this command only, so the platform's own environment is never resolved
    # against the extra index. Credentials are deliberately not handled here — uv picks them up from
    # ~/.netrc or UV_INDEX_<NAME>_* in the inherited environment.
    if config.index_url:
        typer.echo(f"  using extra index {redact_index_url(config.index_url)}")
        install_cmd += ["--index", config.index_url]
    if config.index_strategy:
        install_cmd += ["--index-strategy", config.index_strategy]
    run_subprocess([*install_cmd, config.iron_swarm_spec], "install iron-swarm")
    if not config.iron_swarm_bin.exists():
        typer.secho(
            f"Install finished but {config.iron_swarm_bin} is missing — check the package spec "
            f"({config.iron_swarm_spec}).",
            fg="red",
        )
        raise typer.Exit(code=1)
    typer.secho(f"iron-swarm installed: {config.iron_swarm_bin}", fg="green")


def run_iron_swarm_setup(config: IronSwarmConfig, *, force: bool) -> None:
    """Run ``iron-swarm setup`` (idempotent): provisions the garak venv and registers the gateway.

    Not gated on the garak venv, so the OpenShell gateway is re-ensured on every setup (iron-swarm
    fast-returns the existing venv). Needs iron-swarm installed first (``provision_venv``). The
    plugin points garak provisioning at its managed location via ``IRON_SWARM_GARAK_PYTHON``.
    """
    cmd = [str(config.iron_swarm_bin), "setup"]
    if force:
        cmd.append("--force")
    typer.echo("Running `iron-swarm setup` (garak venv + OpenShell gateway) ...")
    run_subprocess(cmd, "run iron-swarm setup", {**os.environ, GARAK_PYTHON_ENVVAR: str(config.garak_python)})
    if not config.garak_python.exists():
        typer.secho(f"iron-swarm setup finished but {config.garak_python} is missing.", fg="red")
        raise typer.Exit(code=1)
    typer.secho(f"garak venv ready: {config.garak_venv_path}", fg="green")
