# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from importlib import import_module as _importlib_import_module
from typing import Annotated

import typer

from nemo_platform.cli.core.api import build_kwargs
from nemo_platform.cli.core.api import merge_filter_dict as merge_filter_dict
from nemo_platform.cli.core.code_generator import handle_code_generation
from nemo_platform.cli.core.context import CLIContext
from nemo_platform.cli.core.errors import handle_errors
from nemo_platform.cli.core.formatters import Column, check_output_columns_with_format, format_output
from nemo_platform.cli.core.help_formatter import collect_warnings, create_typer_app
from nemo_platform.cli.core.pagination import PaginationType, fetch_all_pages, warn_if_more_pages
from nemo_platform.cli.core.stdin_utils import (
    resolve_secret_value,
    validate_required_fields,
)
from nemo_platform.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
)

_cli_child_admin = _importlib_import_module("nemo_platform.cli.commands.api.secrets.admin")

app = create_typer_app(name="secrets", help="Manage secrets")

app.add_typer(_cli_child_admin.app, name="admin")


@app.command("access")
@collect_warnings
@handle_errors
def access_secrets(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Access the value of a secret."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["secrets"], "access", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.secrets.access(name, **kwargs)

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
def create_secrets(
    ctx: typer.Context,
    name: Annotated[str | None, typer.Argument(help="The name of the secret to create")] = None,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--from-file", help="Path to file containing the secret value. Use '-' to read from stdin."),
    ] = None,
    value: Annotated[
        str | None,
        typer.Option("--value", help="Secret value directly. Use --from-file for large or sensitive input."),
    ] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="An optional description of the secret")
    ] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Create a new secret.

    [green]Examples:[/]
    [dim]# Pass secret value directly[/]
    nemo secrets create my-secret --value "abc123"
    [dim]# Read secret from a file[/]
    nemo secrets create my-secret --from-file ./secret.txt --description "API key for X"
    [dim]# Read secret from stdin[/]
    cat secret.txt | nemo secrets create my-secret --from-file -
    [dim]# Read secret from environment variable[/]
    echo "$API_KEY" | nemo secrets create my-secret --from-file -
    """
    input_payload = {}

    if workspace is not None:
        input_payload["workspace"] = workspace
    if from_file is not None:
        input_payload["from_file"] = from_file
    if value is not None:
        input_payload["value"] = value
    if name is not None:
        input_payload["name"] = name
    if description is not None:
        input_payload["description"] = description

    validate_required_fields(
        input_payload,
        ["name"],
        "secrets create",
        {
            "name": "The name of the secret to create",
        },
    )
    secret_data = resolve_secret_value(from_file, value, required=True, command_name="secrets create")
    assert secret_data is not None  # required=True guarantees non-None

    all_kwargs = {k: v for k, v in input_payload.items() if k not in ("from_file", "value")}
    all_kwargs["value"] = "***"
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)
    if handle_code_generation(["secrets"], "create", all_kwargs, output_format, state):
        return

    all_kwargs["value"] = secret_data
    client = state.get_client()
    result = client.secrets.create(**all_kwargs)

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
def delete_secrets(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
) -> None:
    """Delete a secret."""
    state: CLIContext = ctx.obj
    client = state.get_client()

    kwargs = build_kwargs(
        workspace=workspace,
    )
    client.secrets.delete(name, **kwargs)

    typer.echo("✓ Deleted successfully")


@app.command("list")
@collect_warnings
@handle_errors
def list_secrets(
    ctx: typer.Context,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    page: Annotated[int | None, typer.Option("--page", help="Page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Page size.")] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """List available secrets"""
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
        page=page,
        page_size=page_size,
    )

    if handle_code_generation(["secrets"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = ()
    pagination_type = PaginationType.PAGE_NUMBER
    if all_pages:
        items = fetch_all_pages(
            client.secrets.list,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.secrets.list(*path_args, **kwargs)

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


@app.command("get")
@collect_warnings
@handle_errors
def retrieve_secrets(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Retrieve a secret by its name."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["secrets"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.secrets.retrieve(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("update")
@collect_warnings
@handle_errors
def update_secrets(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--from-file", help="Path to file containing the secret value. Use '-' to read from stdin."),
    ] = None,
    value: Annotated[
        str | None,
        typer.Option("--value", help="Secret value directly. Use --from-file for large or sensitive input."),
    ] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="An optional description of the secret")
    ] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Update a secret's metadata and/or value.

    [green]Examples:[/]
    [dim]# Update secret value directly[/]
    nemo secrets update my-secret --value "new-value"
    [dim]# Read secret from a file[/]
    nemo secrets update my-secret --from-file ./secret.txt --description "Updated!"
    [dim]# Read secret from stdin[/]
    cat secret.txt | nemo secrets update my-secret --from-file -
    [dim]# Read secret from environment variable[/]
    echo "$API_KEY" | nemo secrets update my-secret --from-file -
    """
    input_payload = {}

    if workspace is not None:
        input_payload["workspace"] = workspace
    if description is not None:
        input_payload["description"] = description

    all_kwargs = {"name": name, **input_payload}
    secret_data = resolve_secret_value(from_file, value, required=False)
    if secret_data is not None:
        all_kwargs["value"] = "***"

    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)
    if handle_code_generation(["secrets"], "update", all_kwargs, output_format, state):
        return

    if secret_data is not None:
        all_kwargs["value"] = secret_data
    client = state.get_client()
    result = client.secrets.update(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
