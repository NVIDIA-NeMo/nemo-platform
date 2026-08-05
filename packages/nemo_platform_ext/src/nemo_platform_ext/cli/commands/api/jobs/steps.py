# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from typing import Annotated, Literal

import typer

from nemo_platform_ext.cli.core.api import build_kwargs, merge_filter_dict
from nemo_platform_ext.cli.core.code_generator import handle_code_generation
from nemo_platform_ext.cli.core.context import CLIContext
from nemo_platform_ext.cli.core.errors import handle_errors
from nemo_platform_ext.cli.core.formatters import Column, check_output_columns_with_format, format_output
from nemo_platform_ext.cli.core.help_formatter import collect_warnings, create_typer_app
from nemo_platform_ext.cli.core.pagination import PaginationType, fetch_all_pages, warn_if_more_pages
from nemo_platform_ext.cli.core.stdin_utils import read_data_input_with_flags, read_payload, validate_required_fields
from nemo_platform_ext.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
    StreamOutputOption,
)

app = create_typer_app(name="steps", help="Manage steps")


@app.command("list")
@collect_warnings
@handle_errors
def list_steps(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    filter: Annotated[
        str | None,
        typer.Option(
            "--filter",
            metavar="FILTER_JSON",
            help="Use --filter with JSON for complex/nested queries, or --filter.FIELD options for simple fields. Both can be combined, with field options taking precedence.\nJSON-only fields:\n  status: ['created' | 'pending' | 'active' | 'cancelled' | 'cancelling' | 'error' | 'completed' | 'paused' | 'pausing' | 'resuming']\n\nFilter steps by job, status, and source.",
            rich_help_panel="Filter Options",
        ),
    ] = None,
    filter_job: Annotated[str | None, typer.Option("--filter.job", rich_help_panel="Filter Options")] = None,
    filter_source: Annotated[str | None, typer.Option("--filter.source", rich_help_panel="Filter Options")] = None,
    page: Annotated[int | None, typer.Option("--page", help="Page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Page size.")] = None,
    sort: Annotated[
        Literal["created_at", "-created_at", "updated_at", "-updated_at"] | None,
        typer.Option(
            "--sort", help="The field to sort by. To sort in decreasing order, use `-` in front of the field name."
        ),
    ] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    stream: StreamOutputOption = False,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """List job steps with pagination and filtering."""
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
        filter=merge_filter_dict(filter, job=filter_job, source=filter_source),
        page=page,
        page_size=page_size,
        sort=sort,
    )

    if handle_code_generation(["jobs", "steps"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = (name,)
    pagination_type = PaginationType.PAGE_NUMBER
    if all_pages:
        items = fetch_all_pages(
            client.jobs.steps.list,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.jobs.steps.list(*path_args, **kwargs)

    format_output(
        items,
        is_list=True,
        output_format=output_format,
        output_columns=columns,
        no_truncate=state.get_no_truncate(no_truncate),
        timestamp_format=state.get_timestamp_format(),
        stream=stream,
    )
    if not all_pages:
        warn_if_more_pages(items, pagination_type)


@app.command("get")
@collect_warnings
@handle_errors
def retrieve_steps(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str, typer.Option("--job")] = ...,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get a specific job step."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
        job=job,
    )
    if handle_code_generation(["jobs", "steps"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.steps.retrieve(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("update-status")
@collect_warnings
@handle_errors
def update_status_steps(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    job: Annotated[str | None, typer.Option("--job", help="(required)")] = None,
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
            help="Enumeration of possible job statuses.This enum represents the various states a job can be in during its lifecycle, from creation to a terminal state. (required)",
        ),
    ] = None,
    error_details: Annotated[
        str | None,
        typer.Option("--error-details", help="Optional error details related to the status update. (JSON string)"),
    ] = None,
    status_details: Annotated[
        str | None,
        typer.Option("--status-details", help="Optional status details related to the status update. (JSON string)"),
    ] = None,
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
    """Update a job step status.

    [bold red]Required fields:[/] job, status

    [green]Examples:[/]
    nemo jobs steps update-status <name> --input-file config.json
    nemo jobs steps update-status <name> --input-data '{"job": "value", "status": "value"}'
    echo '{"json": "data"}' | nemo jobs steps update-status <name> --input-file -
    nemo jobs steps update-status <name> --<option> "value"
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
    if status is not None:
        input_payload["status"] = status
    if error_details is not None:
        input_payload["error_details"] = read_payload("error_details", error_details)
    if status_details is not None:
        input_payload["status_details"] = read_payload("status_details", status_details)
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["job", "status"],
        "jobs steps update-status",
        {
            "job": "(required)",
            "status": "Enumeration of possible job statuses.This enum represents the various states a job can be in during its lifecycle, from creation to a terminal state. (required)",
        },
    )

    all_kwargs = {"name": name, **input_payload}

    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["jobs", "steps"], "update_status", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.steps.update_status(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
