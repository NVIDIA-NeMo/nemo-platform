# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from nemo_platform_ext.cli.core.api import build_kwargs
from nemo_platform_ext.cli.core.code_generator import handle_code_generation
from nemo_platform_ext.cli.core.context import CLIContext
from nemo_platform_ext.cli.core.errors import handle_errors
from nemo_platform_ext.cli.core.formatters import Column, check_output_columns_with_format, format_output
from nemo_platform_ext.cli.core.help_formatter import collect_warnings, create_typer_app
from nemo_platform_ext.cli.core.stdin_utils import read_data_input_with_flags, validate_required_fields
from nemo_platform_ext.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
    StreamOutputOption,
)

app = create_typer_app(name="results", help="Manage results")


@app.command("create")
@collect_warnings
@handle_errors
def create_results(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str | None, typer.Option("--job", help="(required)")] = None,
    artifact_storage_type: Annotated[
        Literal["fileset"] | None, typer.Option("--artifact-storage-type", help="(required)")
    ] = None,
    artifact_url: Annotated[str | None, typer.Option("--artifact-url", help="(required)")] = None,
    input_file: Annotated[
        str | None,
        typer.Option("--input-file", help="Path to JSON file (use '-' for stdin)", rich_help_panel="Input Options"),
    ] = None,
    input_data: Annotated[
        str | None,
        typer.Option("--input-data", help="Input data for the request (JSON or YAML)", rich_help_panel="Input Options"),
    ] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Create a new result for a job.

    [bold red]Required fields:[/] job, artifact_storage_type, artifact_url

    [green]Examples:[/]
    nemo jobs results create <name> --input-file config.json
    nemo jobs results create <name> --input-data '{"job": "value", "artifact_storage_type": "value", "artifact_url": "value"}'
    echo '{"json": "data"}' | nemo jobs results create <name> --input-file -
    nemo jobs results create <name> --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if workspace is not None:
        input_payload["workspace"] = workspace
    if job is not None:
        input_payload["job"] = job
    if artifact_storage_type is not None:
        input_payload["artifact_storage_type"] = artifact_storage_type
    if artifact_url is not None:
        input_payload["artifact_url"] = artifact_url
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["job", "artifact_storage_type", "artifact_url"],
        "jobs results create",
        {
            "job": "(required)",
            "artifact_storage_type": "(required)",
            "artifact_url": "(required)",
        },
    )

    all_kwargs = {"name": name, **input_payload}
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["jobs", "results"], "create", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.results.create(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("download")
@handle_errors
def download_results(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str, typer.Option("--job")] = ...,
    output_file: Annotated[Path, typer.Option("--output-file", "-o", help="Output file path")] = ...,
) -> None:
    """Download a job result file."""
    state: CLIContext = ctx.obj
    client = state.get_client()

    kwargs = build_kwargs(
        workspace=workspace,
        job=job,
    )
    result = client.jobs.results.download(name, **kwargs)

    result.write_to_file(output_file)
    typer.echo(f"✓ Downloaded to {output_file!r}")


@app.command("list")
@collect_warnings
@handle_errors
def list_results(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    sort: Annotated[
        Literal["created_at", "-created_at", "updated_at", "-updated_at"] | None,
        typer.Option("--sort", help="The field to sort by."),
    ] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    stream: StreamOutputOption = False,
) -> None:
    """List results for a job."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    check_output_columns_with_format(columns, output_format)

    default_columns = [
        Column("name", None),
        Column("workspace", None),
        Column("created_at", None),
    ]
    if columns is None or str(columns).strip() == "default":
        columns = default_columns

    kwargs = build_kwargs(
        workspace=workspace,
        sort=sort,
    )

    if handle_code_generation(["jobs", "results"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = (name,)
    items = client.jobs.results.list(*path_args, **kwargs)

    format_output(
        items,
        is_list=True,
        output_format=output_format,
        output_columns=columns,
        no_truncate=state.get_no_truncate(no_truncate),
        timestamp_format=state.get_timestamp_format(),
        stream=stream,
    )


@app.command("get")
@collect_warnings
@handle_errors
def retrieve_results(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str, typer.Option("--job")] = ...,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get a specific job result."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
        job=job,
    )
    if handle_code_generation(["jobs", "results"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.results.retrieve(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
