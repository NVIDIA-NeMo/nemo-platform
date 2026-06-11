# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI overrides for the Unsloth contributor.

After the platform's :func:`_add_run_command` / :func:`_add_submit_command`
register the default verbs on the contributor's Typer group, this module
swaps in:

- ``submit`` → positional ``JOB_JSON`` argument plus ``--workspace``,
  ``--profile``, ``--cluster``, ``--base-url``, ``-o`` overrides. Loads
  the JSON, validates against :class:`UnslothJobInput`, then delegates
  to the original ``submit`` callback with ``--spec`` set to the
  validated JSON string.
- ``run`` → hard-fails with a "submit-only" message pointing at the new
  verb (Unsloth migrated from local BYO-venv runs to container submit
  in 2026).
- ``explain`` → unchanged (the original schema dump is useful as-is).
"""

import json
from collections.abc import Callable
from pathlib import Path

import typer

from nemo_unsloth_plugin.schema import UnslothJobInput

_JOB_JSON_HELP = "Path to Unsloth job JSON (UnslothJobInput schema)."


def load_job_json(path: Path) -> str:
    """Load and validate job JSON; return canonical JSON string for ``--spec``."""
    data = json.loads(path.read_text())
    validated = UnslothJobInput.model_validate(data)
    return validated.model_dump_json()


def apply_unsloth_job_cli_overrides(group: typer.Typer) -> None:
    """Flat ``unsloth`` CLI: ``submit JOB.json``; ``run`` is disabled.

    Order matters: drop the original verbs first, then re-register the
    overrides. Typer iterates ``registered_commands`` in insertion order
    so leaving stale entries behind would route users back to the
    auto-generated shapes.
    """
    _replace_job_run_disabled(group)
    _replace_job_submit(group)


def _pluck_callback(group: typer.Typer, verb: str) -> Callable[..., None]:
    command = next((c for c in group.registered_commands if c.name == verb), None)
    if command is None or command.callback is None:
        raise RuntimeError(f"missing {verb!r} callback to override")
    return command.callback


def _drop_command(group: typer.Typer, name: str) -> None:
    group.registered_commands = [c for c in group.registered_commands if c.name != name]


def _replace_job_run_disabled(group: typer.Typer) -> None:
    """Replace ``run`` with a hard-fail explainer.

    Unsloth is submit-only (container-execution); local run attempts
    would either return ``NotImplementedError`` from :class:`NemoJob.run`
    or require the unsloth/torch stack in the CLI interpreter. Surface
    the intended workflow up front instead.
    """
    _drop_command(group, "run")

    @group.command("run")
    def run(
        _typer_ctx: typer.Context,
        _job_json: Path | None = typer.Argument(
            None,
            metavar="JOB_JSON",
            help=_JOB_JSON_HELP,
        ),
    ) -> None:
        typer.secho(
            "Unsloth does not support local run. Submit to the platform API instead:\n"
            "  nemo customization unsloth submit <job.json> -w <workspace>",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def _replace_job_submit(group: typer.Typer) -> None:
    """Replace ``submit`` with a ``JOB_JSON`` positional + standard submit flags."""
    original = _pluck_callback(group, "submit")

    @group.command("submit")
    def submit(
        typer_ctx: typer.Context,
        job_json: Path = typer.Argument(..., metavar="JOB_JSON", help=_JOB_JSON_HELP),
        workspace: str = typer.Option("default", "--workspace", "-w", help="Target workspace."),
        profile: str | None = typer.Option(None, "--profile"),
        cluster: str | None = typer.Option(None, "--cluster"),
        base_url: str | None = typer.Option(
            None,
            "--base-url",
            help=(
                "Override platform API host. If omitted: --cluster, then CLI context, "
                "then $NMP_BASE_URL, then http://localhost:8080."
            ),
        ),
        options: list[str] = typer.Option([], "-o", help="Backend option override, 'backend.key=value'."),
        options_file: Path | None = typer.Option(None, "--options-file"),
    ) -> None:
        spec_json = load_job_json(job_json)
        original(
            typer_ctx,
            spec=spec_json,
            spec_file=None,
            options=options,
            options_file=options_file,
            profile=profile,
            cluster=cluster,
            base_url=base_url,
            workspace=workspace,
            config=None,
            config_file=None,
        )
