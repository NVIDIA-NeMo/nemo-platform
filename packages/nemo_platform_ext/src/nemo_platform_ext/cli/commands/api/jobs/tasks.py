# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from typing import Annotated, Literal

import typer

from nemo_platform_ext.cli.core.api import build_kwargs
from nemo_platform_ext.cli.core.code_generator import handle_code_generation
from nemo_platform_ext.cli.core.context import CLIContext
from nemo_platform_ext.cli.core.errors import handle_errors
from nemo_platform_ext.cli.core.formatters import (
    Column,
    check_output_columns_with_format,
    format_output,
    validate_stream_output_format,
)
from nemo_platform_ext.cli.core.help_formatter import collect_warnings, create_typer_app
from nemo_platform_ext.cli.core.stdin_utils import read_data_input_with_flags, read_payload, validate_required_fields
from nemo_platform_ext.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
    StreamOutputOption,
)

app = create_typer_app(name="tasks", help="Manage tasks")


@app.command("create-or-update")
@collect_warnings
@handle_errors
def create_or_update_tasks(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str | None, typer.Option("--job", help="(required)")] = None,
    step: Annotated[str | None, typer.Option("--step", help="(required)")] = None,
    error_details: Annotated[str | None, typer.Option("--error-details", help="JSON string")] = None,
    error_stack: Annotated[str | None, typer.Option("--error-stack")] = None,
    status: Annotated[
        Literal[
            "created",
            "pending",
            "active",
            "cancelled",
            "cancelling",
            "error",
            "completed",
            "paused",
            "pausing",
            "resuming",
        ]
        | None,
        typer.Option(
            "--status",
            help="Enumeration of possible job statuses.This enum represents the various states a job can be in during its lifecycle, from creation to a terminal state.",
        ),
    ] = None,
    status_details: Annotated[str | None, typer.Option("--status-details", help="JSON string")] = None,
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
    """Update a job step task.

    [bold red]Required fields:[/] job, step

    [green]Examples:[/]
    nemo jobs tasks create-or-update <name> --input-file config.json
    nemo jobs tasks create-or-update <name> --input-data '{"job": "value", "step": "value"}'
    echo '{"json": "data"}' | nemo jobs tasks create-or-update <name> --input-file -
    nemo jobs tasks create-or-update <name> --<option> "value"
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
    if step is not None:
        input_payload["step"] = step
    if error_details is not None:
        input_payload["error_details"] = read_payload("error_details", error_details)
    if error_stack is not None:
        input_payload["error_stack"] = error_stack
    if status is not None:
        input_payload["status"] = status
    if status_details is not None:
        input_payload["status_details"] = read_payload("status_details", status_details)
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["job", "step"],
        "jobs tasks create-or-update",
        {
            "job": "(required)",
            "step": "(required)",
        },
    )

    all_kwargs = {"name": name, **input_payload}
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["jobs", "tasks"], "create_or_update", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.tasks.create_or_update(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("list")
@collect_warnings
@handle_errors
def list_tasks(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str, typer.Option("--job")] = ...,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    stream: StreamOutputOption = False,
) -> None:
    """List tasks for a job step."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)
    validate_stream_output_format(output_format, stream)

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
        job=job,
    )

    if handle_code_generation(["jobs", "tasks"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = (name,)
    items = client.jobs.tasks.list(*path_args, **kwargs)

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
def retrieve_tasks(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str, typer.Option("--job")] = ...,
    step: Annotated[str, typer.Option("--step")] = ...,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get a specific job step task."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
        job=job,
        step=step,
    )
    if handle_code_generation(["jobs", "tasks"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.tasks.retrieve(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
