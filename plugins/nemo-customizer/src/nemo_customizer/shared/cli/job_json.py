# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI overrides: ``submit JOB.json`` and optional submit-only ``run`` disable."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import typer
from pydantic import BaseModel


def make_load_job_json(input_schema: type[BaseModel]) -> Callable[[Path], str]:
    """Return a loader that validates job JSON against ``input_schema``."""

    def load_job_json(path: Path) -> str:
        data = json.loads(path.read_text())
        validated = input_schema.model_validate(data)
        return validated.model_dump_json()

    return load_job_json


def apply_job_json_cli_overrides(
    group: typer.Typer,
    backend_name: str,
    input_schema: type[BaseModel],
    job_json_help: str,
    disable_local_run: bool = True,
) -> None:
    """Reshape contributor CLI: positional ``JOB_JSON`` on submit; optional run disable.

    Order matters: drop the original verbs first, then re-register overrides.
    """
    if disable_local_run:
        _replace_job_run_disabled(group, backend_name=backend_name, job_json_help=job_json_help)
    _replace_job_submit(
        group,
        backend_name=backend_name,
        input_schema=input_schema,
        job_json_help=job_json_help,
    )


def _pluck_callback(group: typer.Typer, verb: str) -> Callable[..., None]:
    command = next((c for c in group.registered_commands if c.name == verb), None)
    if command is None or command.callback is None:
        raise RuntimeError(f"missing {verb!r} callback to override")
    return command.callback


def _drop_command(group: typer.Typer, name: str) -> None:
    group.registered_commands = [c for c in group.registered_commands if c.name != name]


def _replace_job_run_disabled(group: typer.Typer, backend_name: str, job_json_help: str) -> None:
    _drop_command(group, "run")

    @group.command("run")
    def run(
        _typer_ctx: typer.Context,
        _job_json: Path | None = typer.Argument(
            None,
            metavar="JOB_JSON",
            help=job_json_help,
        ),
    ) -> None:
        typer.secho(
            f"{backend_name.title()} does not support local run. Submit to the platform API instead:\n"
            f"  nemo customization {backend_name} submit <job.json> -w <workspace>",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def _replace_job_submit(
    group: typer.Typer,
    backend_name: str,
    input_schema: type[BaseModel],
    job_json_help: str,
) -> None:
    del backend_name  # reserved for future backend-specific submit flags
    original = _pluck_callback(group, "submit")
    _drop_command(group, "submit")
    load_job_json = make_load_job_json(input_schema)

    @group.command("submit")
    def submit(
        typer_ctx: typer.Context,
        job_json: Path = typer.Argument(..., metavar="JOB_JSON", help=job_json_help),
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
