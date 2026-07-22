# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from importlib import import_module as _importlib_import_module
from typing import Annotated, Literal

import typer

from nemo_platform.cli.core.api import build_kwargs, merge_filter_dict
from nemo_platform.cli.core.code_generator import handle_code_generation
from nemo_platform.cli.core.context import CLIContext
from nemo_platform.cli.core.errors import handle_errors
from nemo_platform.cli.core.formatters import Column, check_output_columns_with_format, format_output
from nemo_platform.cli.core.help_formatter import collect_warnings, create_typer_app
from nemo_platform.cli.core.pagination import PaginationType, fetch_all_pages, warn_if_more_pages
from nemo_platform.cli.core.stdin_utils import read_data_input_with_flags, read_payload, validate_required_fields
from nemo_platform.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
)

_cli_child_results = _importlib_import_module("nemo_platform.cli.commands.api.jobs.results")
_cli_child_steps = _importlib_import_module("nemo_platform.cli.commands.api.jobs.steps")
_cli_child_tasks = _importlib_import_module("nemo_platform.cli.commands.api.jobs.tasks")

app = create_typer_app(name="jobs", help="Manage jobs")

app.add_typer(_cli_child_results.app, name="results")
app.add_typer(_cli_child_steps.app, name="steps")
app.add_typer(_cli_child_tasks.app, name="tasks")


@app.command("cancel")
@collect_warnings
@handle_errors
def cancel_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Cancel a platform job."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["jobs"], "cancel", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.cancel(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("create")
@collect_warnings
@handle_errors
def create_jobs(
    ctx: typer.Context,
    name: Annotated[str | None, typer.Argument()] = None,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    platform_spec: Annotated[
        str | None,
        typer.Option(
            "--platform-spec",
            help="Specification for a platform job, containing steps and secrets. (JSON string) (required)",
        ),
    ] = None,
    source: Annotated[str | None, typer.Option("--source", help="(required)")] = None,
    spec: Annotated[str | None, typer.Option("--spec", help="JSON string (required)")] = None,
    custom_fields: Annotated[str | None, typer.Option("--custom-fields", help="JSON string")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    ownership: Annotated[str | None, typer.Option("--ownership", help="JSON string")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
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
    """Create a new platform job.

    [bold red]Required fields:[/] platform_spec, source, spec

    [green]Examples:[/]
    nemo jobs create <name> --input-file config.json
    nemo jobs create <name> --input-data '{"platform_spec": {}, "source": "value", "spec": {}}'
    echo '{"json": "data"}' | nemo jobs create <name> --input-file -
    nemo jobs create <name> --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if workspace is not None:
        input_payload["workspace"] = workspace
    if platform_spec is not None:
        input_payload["platform_spec"] = read_payload("platform_spec", platform_spec)
    if source is not None:
        input_payload["source"] = source
    if spec is not None:
        input_payload["spec"] = read_payload("spec", spec)
    if custom_fields is not None:
        input_payload["custom_fields"] = read_payload("custom_fields", custom_fields)
    if description is not None:
        input_payload["description"] = description
    if name is not None:
        input_payload["name"] = name
    if ownership is not None:
        input_payload["ownership"] = read_payload("ownership", ownership)
    if project is not None:
        input_payload["project"] = project
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["platform_spec", "source", "spec"],
        "jobs create",
        {
            "platform_spec": "Specification for a platform job, containing steps and secrets. (JSON string) (required)",
            "source": "(required)",
            "spec": "JSON string (required)",
        },
    )

    all_kwargs = input_payload
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["jobs"], "create", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.create(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("delete")
@collect_warnings
@handle_errors
def delete_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
) -> None:
    """Delete a platform job."""
    state: CLIContext = ctx.obj
    client = state.get_client()

    kwargs = build_kwargs(
        workspace=workspace,
    )
    client.jobs.delete(name, **kwargs)

    typer.echo("✓ Deleted successfully")


@app.command("get-logs")
@collect_warnings
@handle_errors
def get_logs_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    attempt_id: Annotated[int | None, typer.Option("--attempt-id", help="Filter logs by job attempt ID")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum number of logs to return")] = None,
    page_cursor: Annotated[str | None, typer.Option("--page-cursor", help="Page cursor")] = None,
    step_id: Annotated[str | None, typer.Option("--step-id", help="Filter logs by step name")] = None,
    task_id: Annotated[str | None, typer.Option("--task-id", help="Filter logs by task ID")] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """Get paginated logs for a platform job."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    check_output_columns_with_format(columns, output_format)

    default_columns = [
        Column("timestamp", None),
        Column("message", None),
    ]
    if columns is None or str(columns).strip() == "default":
        columns = default_columns

    kwargs = build_kwargs(
        workspace=workspace,
        attempt_id=attempt_id,
        limit=limit,
        page_cursor=page_cursor,
        step_id=step_id,
        task_id=task_id,
    )

    if handle_code_generation(["jobs"], "get_logs", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = (name,)
    pagination_type = PaginationType.CURSOR
    if all_pages:
        items = fetch_all_pages(
            client.jobs.get_logs,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.jobs.get_logs(*path_args, **kwargs)

    format_output(
        items,
        is_list=True,
        output_format=output_format,
        output_columns=columns,
        no_truncate=state.get_no_truncate(no_truncate),
        timestamp_format=state.get_timestamp_format(),
    )
    if not all_pages:
        warn_if_more_pages(items, pagination_type)


@app.command("get-status")
@collect_warnings
@handle_errors
def get_status_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get the status of a platform job."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["jobs"], "get_status", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.get_status(name, **kwargs)

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
def list_jobs(
    ctx: typer.Context,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    filter: Annotated[
        str | None,
        typer.Option(
            "--filter",
            metavar="FILTER_JSON",
            help="Use --filter with JSON for complex/nested queries, or --filter.FIELD options for simple fields. Both can be combined, with field options taking precedence.\nJSON-only fields:\n  created_at: {gte: str, lte: str}\n  updated_at: {gte: str, lte: str}\n\nFilter jobs by workspace, project, name, status, source, created_at, and updated_at.",
            rich_help_panel="Filter Options",
        ),
    ] = None,
    filter_name: Annotated[str | None, typer.Option("--filter.name", rich_help_panel="Filter Options")] = None,
    filter_project: Annotated[str | None, typer.Option("--filter.project", rich_help_panel="Filter Options")] = None,
    filter_source: Annotated[str | None, typer.Option("--filter.source", rich_help_panel="Filter Options")] = None,
    filter_status: Annotated[
        list[str] | None, typer.Option("--filter.status", rich_help_panel="Filter Options")
    ] = None,
    filter_workspace: Annotated[
        str | None, typer.Option("--filter.workspace", rich_help_panel="Filter Options")
    ] = None,
    page: Annotated[int | None, typer.Option("--page", help="Page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Page size.")] = None,
    sort: Annotated[
        Literal["created_at", "-created_at", "updated_at", "-updated_at", "source", "-source"] | None,
        typer.Option(
            "--sort", help="The field to sort by. To sort in decreasing order, use `-` in front of the field name."
        ),
    ] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """List platform jobs with filtering and pagination."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    check_output_columns_with_format(columns, output_format)

    default_columns = [
        Column("name", None),
        Column("description", None),
        Column("status", None),
        Column("created_at", None),
    ]
    if columns is None or str(columns).strip() == "default":
        columns = default_columns

    kwargs = build_kwargs(
        workspace=workspace,
        filter=merge_filter_dict(
            filter,
            name=filter_name,
            project=filter_project,
            source=filter_source,
            status=filter_status,
            workspace=filter_workspace,
        ),
        page=page,
        page_size=page_size,
        sort=sort,
    )

    if handle_code_generation(["jobs"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = ()
    pagination_type = PaginationType.PAGE_NUMBER
    if all_pages:
        items = fetch_all_pages(
            client.jobs.list,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.jobs.list(*path_args, **kwargs)

    format_output(
        items,
        is_list=True,
        output_format=output_format,
        output_columns=columns,
        no_truncate=state.get_no_truncate(no_truncate),
        timestamp_format=state.get_timestamp_format(),
    )
    if not all_pages:
        warn_if_more_pages(items, pagination_type)


@app.command("list-execution-profiles")
@collect_warnings
@handle_errors
def list_execution_profiles_jobs(
    ctx: typer.Context,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
) -> None:
    """Get all currently configured execution profiles."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    check_output_columns_with_format(columns, output_format)

    default_columns = [
        Column("profile", None),
        Column("backend", None),
        Column("provider", None),
        Column("config", None),
    ]
    if columns is None or str(columns).strip() == "default":
        columns = default_columns

    kwargs = build_kwargs()

    if handle_code_generation(["jobs"], "list_execution_profiles", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = ()
    items = client.jobs.list_execution_profiles(*path_args, **kwargs)

    format_output(
        items,
        is_list=True,
        output_format=output_format,
        output_columns=columns,
        no_truncate=state.get_no_truncate(no_truncate),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("pause")
@collect_warnings
@handle_errors
def pause_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Pause a platform job."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["jobs"], "pause", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.pause(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("resume")
@collect_warnings
@handle_errors
def resume_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Resume a paused platform job."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["jobs"], "resume", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.resume(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("get")
@collect_warnings
@handle_errors
def retrieve_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get a platform job by name."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["jobs"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.retrieve(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("update-status-details")
@collect_warnings
@handle_errors
def update_status_details_jobs(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    body: Annotated[str | None, typer.Option("--body", help="JSON string (required)")] = None,
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
    """Update the status details of a platform job.

    [bold red]Required fields:[/] body

    [green]Examples:[/]
    nemo jobs update-status-details <name> --input-file config.json
    nemo jobs update-status-details <name> --input-data '{"body": {}}'
    echo '{"json": "data"}' | nemo jobs update-status-details <name> --input-file -
    nemo jobs update-status-details <name> --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if workspace is not None:
        input_payload["workspace"] = workspace
    if body is not None:
        input_payload["body"] = read_payload("body", body)
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["body"],
        "jobs update-status-details",
        {
            "body": "JSON string (required)",
        },
    )

    all_kwargs = {"name": name, **input_payload}

    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["jobs"], "update_status_details", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.jobs.update_status_details(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
