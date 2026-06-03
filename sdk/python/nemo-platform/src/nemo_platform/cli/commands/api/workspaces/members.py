# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from typing import Annotated

import typer

from nemo_platform.cli.core.api import build_kwargs
from nemo_platform.cli.core.code_generator import handle_code_generation
from nemo_platform.cli.core.context import CLIContext
from nemo_platform.cli.core.errors import handle_errors
from nemo_platform.cli.core.formatters import Column, check_output_columns_with_format, format_output
from nemo_platform.cli.core.help_formatter import collect_warnings, create_typer_app
from nemo_platform.cli.core.stdin_utils import read_data_input_with_flags, validate_required_fields
from nemo_platform.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
)

app = create_typer_app(name="members", help="Manage members")


@app.command("create")
@collect_warnings
@handle_errors
def create_members(
    ctx: typer.Context,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    principal: Annotated[
        str | None,
        typer.Option("--principal", help="The principal identifier (email, user ID, or group ID) (required)"),
    ] = None,
    wait_role_propagation: Annotated[
        bool | None,
        typer.Option(
            "--wait-role-propagation",
            help="If true, wait for roles to propagate before returning (default: true). Set to false for bulk operations.",
        ),
    ] = None,
    roles: Annotated[
        list[str] | None, typer.Option("--roles", help="List of roles to grant to the principal (can be repeated)")
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
    """Add a new member to the workspace with specified roles.

    This creates role bindings for the specified principal with the given roles. By
    default, this endpoint waits for the roles to propagate before returning. Use
    `wait_role_propagation=false` to skip waiting (useful for bulk operations).

    Example:

    ```
    POST /apis/entities/v2/workspaces/ml-team/members
    {"principal": "user@example.com", "roles": ["Editor"]}
    ```

        [bold red]Required fields:[/] principal

        [green]Examples:[/]
        nemo workspaces members create --input-file config.json
        nemo workspaces members create --input-data '{"principal": "value"}'
        echo '{"json": "data"}' | nemo workspaces members create --input-file -
        nemo workspaces members create --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if workspace is not None:
        input_payload["workspace"] = workspace
    if principal is not None:
        input_payload["principal"] = principal
    if wait_role_propagation is not None:
        input_payload["wait_role_propagation"] = wait_role_propagation
    if roles:  # Check for non-empty list
        input_payload["roles"] = roles
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["principal"],
        "workspaces members create",
        {
            "principal": "The principal identifier (email, user ID, or group ID) (required)",
        },
    )

    all_kwargs = input_payload
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["workspaces", "members"], "create", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.workspaces.members.create(**all_kwargs)

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
def delete_members(
    ctx: typer.Context,
    principal_id: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    wait_role_propagation: Annotated[
        bool | None,
        typer.Option(
            "--wait-role-propagation",
            help="If true, wait for roles to propagate before returning (default: true). Set to false for bulk operations.",
        ),
    ] = None,
) -> None:
    """Remove a member from the workspace by revoking all their roles.

    This revokes all active role bindings for the principal in the workspace. By
    default, this endpoint waits for all roles to be revoked before returning. Use
    `wait_role_propagation=false` to skip waiting (useful for bulk operations).

    Example:

    ```
    DELETE /apis/entities/v2/workspaces/ml-team/members/user@example.com
    ```"""
    state: CLIContext = ctx.obj
    client = state.get_client()

    kwargs = build_kwargs(
        workspace=workspace,
        wait_role_propagation=wait_role_propagation,
    )
    client.workspaces.members.delete(principal_id, **kwargs)

    typer.echo("✓ Deleted successfully")


@app.command("list")
@collect_warnings
@handle_errors
def list_members(
    ctx: typer.Context,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
) -> None:
    """List all members of a workspace with their roles.

    Returns a list of all principals with active role bindings in the workspace.

    Example:

    ```
    GET /apis/entities/v2/workspaces/ml-team/members
    ```"""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    check_output_columns_with_format(columns, output_format)

    default_columns = [
        Column("principal", None),
        Column("roles", None),
        Column("granted_by", None),
        Column("granted_at", None),
    ]
    if columns is None or str(columns).strip() == "default":
        columns = default_columns

    kwargs = build_kwargs(
        workspace=workspace,
    )

    if handle_code_generation(["workspaces", "members"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = ()
    items = client.workspaces.members.list(*path_args, **kwargs)

    format_output(
        items,
        is_list=True,
        output_format=output_format,
        output_columns=columns,
        no_truncate=state.get_no_truncate(no_truncate),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("update")
@collect_warnings
@handle_errors
def update_members(
    ctx: typer.Context,
    principal_id: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    roles: Annotated[
        list[str] | None,
        typer.Option("--roles", help="Updated list of roles for the principal (can be repeated) (required)"),
    ] = None,
    wait_role_propagation: Annotated[
        bool | None,
        typer.Option(
            "--wait-role-propagation",
            help="If true, wait for roles to propagate before returning (default: true). Set to false for bulk operations.",
        ),
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
    """Update the roles for a workspace member.

    This will revoke existing roles not in the new list and add new roles. By
    default, this endpoint waits for the roles to propagate before returning. Use
    `wait_role_propagation=false` to skip waiting (useful for bulk operations).

    Example:

    ```
    PUT /apis/entities/v2/workspaces/ml-team/members/user@example.com
    {"roles": ["Viewer", "Editor"]}
    ```

        [bold red]Required fields:[/] roles

        [green]Examples:[/]
        nemo workspaces members update <principal_id> --input-file config.json
        nemo workspaces members update <principal_id> --input-data '{"roles": "value"}'
        echo '{"json": "data"}' | nemo workspaces members update <principal_id> --input-file -
        nemo workspaces members update <principal_id> --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if workspace is not None:
        input_payload["workspace"] = workspace
    if roles:  # Check for non-empty list
        input_payload["roles"] = roles
    if wait_role_propagation is not None:
        input_payload["wait_role_propagation"] = wait_role_propagation
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["roles"],
        "workspaces members update",
        {
            "roles": "Updated list of roles for the principal (can be repeated) (required)",
        },
    )

    all_kwargs = {"principal_id": principal_id, **input_payload}

    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["workspaces", "members"], "update", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.workspaces.members.update(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
