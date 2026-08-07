# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from typing import Annotated

import typer

from nemo_platform_ext.cli.core.api import build_kwargs, merge_filter_dict
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
from nemo_platform_ext.cli.core.pagination import PaginationType, fetch_all_pages, warn_if_more_pages
from nemo_platform_ext.cli.core.stdin_utils import read_data_input_with_flags, validate_required_fields
from nemo_platform_ext.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
    StreamOutputOption,
)

app = create_typer_app(name="role_bindings", help="Manage role_bindings")


@app.command("create")
@collect_warnings
@handle_errors
def create_role_bindings(
    ctx: typer.Context,
    principal: Annotated[
        str | None,
        typer.Option("--principal", help="The principal identifier (email, user ID, or group ID) (required)"),
    ] = None,
    role: Annotated[
        str | None, typer.Option("--role", help="The role name (e.g., 'Viewer', 'Editor', 'Admin') (required)")
    ] = None,
    wait_role_propagation: Annotated[
        bool | None,
        typer.Option(
            "--wait-role-propagation",
            help="If true, wait for role to propagate before returning (default: true). Set to false for bulk operations.",
        ),
    ] = None,
    workspace: Annotated[
        str | None,
        typer.Option("--workspace", help="The workspace this binding applies to. None for platform-level roles."),
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
    """Create a new role binding (Platform Admin only)

    [bold red]Required fields:[/] principal, role

    [green]Examples:[/]
    nemo iam role-bindings create --input-file config.json
    nemo iam role-bindings create --input-data '{"principal": "value", "role": "value"}'
    echo '{"json": "data"}' | nemo iam role-bindings create --input-file -
    nemo iam role-bindings create --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if principal is not None:
        input_payload["principal"] = principal
    if role is not None:
        input_payload["role"] = role
    if wait_role_propagation is not None:
        input_payload["wait_role_propagation"] = wait_role_propagation
    if workspace is not None:
        input_payload["workspace"] = workspace
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["principal", "role"],
        "iam role-bindings create",
        {
            "principal": "The principal identifier (email, user ID, or group ID) (required)",
            "role": "The role name (e.g., 'Viewer', 'Editor', 'Admin') (required)",
        },
    )

    all_kwargs = input_payload
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["iam", "role_bindings"], "create", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.iam.role_bindings.create(**all_kwargs)

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
def delete_role_bindings(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    wait_role_propagation: Annotated[
        bool | None,
        typer.Option(
            "--wait-role-propagation",
            help="If true, wait for role to propagate before returning (default: true). Set to false for bulk operations.",
        ),
    ] = None,
) -> None:
    """Revoke a role binding (Platform Admin only)"""
    state: CLIContext = ctx.obj
    client = state.get_client()

    kwargs = build_kwargs(
        wait_role_propagation=wait_role_propagation,
    )
    client.iam.role_bindings.delete(name, **kwargs)

    typer.echo("✓ Deleted successfully")


@app.command("list")
@collect_warnings
@handle_errors
def list_role_bindings(
    ctx: typer.Context,
    filter: Annotated[
        str | None,
        typer.Option(
            "--filter",
            metavar="FILTER_JSON",
            help="Use --filter with JSON for complex/nested queries, or --filter.FIELD options for simple fields. Both can be combined, with field options taking precedence.\nJSON-only fields:\n  granted_at: {gte: str, lte: str}\n  revoked_at: {gte: str, lte: str}\n\nFilter role bindings by principal, workspace, role, granted_by, is_active, granted_at, and revoked_at.",
            rich_help_panel="Filter Options",
        ),
    ] = None,
    filter_granted_by: Annotated[
        str | None, typer.Option("--filter.granted-by", rich_help_panel="Filter Options")
    ] = None,
    filter_is_active: Annotated[
        bool | None, typer.Option("--filter.is-active", rich_help_panel="Filter Options")
    ] = None,
    filter_principal: Annotated[
        str | None, typer.Option("--filter.principal", rich_help_panel="Filter Options")
    ] = None,
    filter_role: Annotated[str | None, typer.Option("--filter.role", rich_help_panel="Filter Options")] = None,
    filter_workspace: Annotated[
        str | None, typer.Option("--filter.workspace", rich_help_panel="Filter Options")
    ] = None,
    page: Annotated[int | None, typer.Option("--page", help="Page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Page size.")] = None,
    sort: Annotated[
        str | None,
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
    """List all role bindings (Platform Admin only)"""
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
        filter=merge_filter_dict(
            filter,
            granted_by=filter_granted_by,
            is_active=filter_is_active,
            principal=filter_principal,
            role=filter_role,
            workspace=filter_workspace,
        ),
        page=page,
        page_size=page_size,
        sort=sort,
    )

    if handle_code_generation(["iam", "role_bindings"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = ()
    pagination_type = PaginationType.PAGE_NUMBER
    if all_pages:
        items = fetch_all_pages(
            client.iam.role_bindings.list,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.iam.role_bindings.list(*path_args, **kwargs)

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
def retrieve_role_bindings(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get a specific role binding (Platform Admin only)"""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs()
    if handle_code_generation(["iam", "role_bindings"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.iam.role_bindings.retrieve(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
