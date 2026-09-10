# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``nemo secrets`` command group, backed by the typed Secrets client."""

from __future__ import annotations

from typing import Annotated

import typer
from nemo_platform_plugin.secrets.client import SecretsClient
from nemo_platform_plugin.secrets.types import (
    ListSecretsQueryParams,
    PlatformSecretCreateRequest,
    PlatformSecretUpdateRequest,
)
from pydantic import SecretStr

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
from nemo_platform_ext.cli.core.pagination import PaginationType, collect_offset_pages, warn_if_more_pages
from nemo_platform_ext.cli.core.stdin_utils import resolve_secret_value, validate_required_fields
from nemo_platform_ext.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
    StreamOutputOption,
)

app = create_typer_app(name="secrets", help="Manage secrets.")
admin_app = create_typer_app(name="admin", help="Manage admin")
app.add_typer(admin_app, name="admin")


def _list_secrets_query_params(page: int | None, page_size: int | None) -> ListSecretsQueryParams | None:
    query_params: ListSecretsQueryParams = {}
    if page is not None:
        query_params["page"] = page
    if page_size is not None:
        query_params["page_size"] = page_size
    return query_params or None


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
    resolved_output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(name=name, workspace=workspace)
    if handle_code_generation(SecretsClient, "access_secret", kwargs, resolved_output_format, state):
        return

    result = state.typed_client(SecretsClient).access_secret(name=name, workspace=workspace)

    format_output(
        result,
        is_list=False,
        output_format=resolved_output_format,
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
    input_payload: dict[str, str] = {}

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
    assert name is not None  # validate_required_fields guarantees non-None

    body = PlatformSecretCreateRequest(name=name, value=SecretStr(secret_data))
    if description is not None:
        body = body.model_copy(update={"description": description})
    state: CLIContext = ctx.obj
    resolved_output_format = state.get_output_format(output_format)
    if handle_code_generation(
        SecretsClient, "create_secret", {"workspace": workspace, "body": body}, output_format, state
    ):
        return

    result = state.typed_client(SecretsClient).create_secret(workspace=workspace, body=body)

    format_output(
        result,
        is_list=False,
        output_format=resolved_output_format,
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
    state.typed_client(SecretsClient).delete_secret(name=name, workspace=workspace)

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
    stream: StreamOutputOption = False,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """List available secrets"""
    state: CLIContext = ctx.obj
    resolved_output_format = state.get_output_format(output_format)
    validate_stream_output_format(resolved_output_format, stream)

    check_output_columns_with_format(columns, resolved_output_format)

    default_columns = [
        Column("name", None),
        Column("workspace", None),
        Column("created_at", None),
    ]
    output_columns: str | list[Column] | None = columns
    if columns is None or str(columns).strip() == "default":
        output_columns = default_columns

    query_params = _list_secrets_query_params(page, page_size)
    kwargs = build_kwargs(workspace=workspace, query_params=query_params)
    if handle_code_generation(SecretsClient, "list_secrets", kwargs, resolved_output_format, state, result="list"):
        return

    response = state.typed_client(SecretsClient).list_secrets(workspace=workspace, query_params=query_params)
    pagination_type = PaginationType.PAGE_NUMBER
    items = collect_offset_pages(response, all_pages=all_pages)

    format_output(
        items,
        is_list=True,
        output_format=resolved_output_format,
        output_columns=output_columns,
        no_truncate=state.get_no_truncate(no_truncate),
        timestamp_format=state.get_timestamp_format(),
        stream=stream,
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
    resolved_output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(name=name, workspace=workspace)
    if handle_code_generation(SecretsClient, "get_secret", kwargs, resolved_output_format, state):
        return

    result = state.typed_client(SecretsClient).get_secret(name=name, workspace=workspace)

    format_output(
        result,
        is_list=False,
        output_format=resolved_output_format,
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
    secret_data = resolve_secret_value(from_file, value, required=False)
    body = PlatformSecretUpdateRequest()
    if description is not None:
        body = body.model_copy(update={"description": description})
    if secret_data is not None:
        body = body.model_copy(update={"value": SecretStr(secret_data)})

    state: CLIContext = ctx.obj
    resolved_output_format = state.get_output_format(output_format)
    kwargs = build_kwargs(name=name, workspace=workspace, body=body)
    if handle_code_generation(SecretsClient, "update_secret", kwargs, resolved_output_format, state):
        return

    result = state.typed_client(SecretsClient).update_secret(name=name, workspace=workspace, body=body)

    format_output(
        result,
        is_list=False,
        output_format=resolved_output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@admin_app.command("rotate-encryption-keys")
@collect_warnings
@handle_errors
def rotate_encryption_keys_admin(
    ctx: typer.Context,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Rotate encryption keys for all platform secrets."""
    state: CLIContext = ctx.obj
    resolved_output_format = state.get_output_format(output_format)

    if handle_code_generation(SecretsClient, "rotate_encryption_keys", {}, resolved_output_format, state):
        return

    result = state.typed_client(SecretsClient).rotate_encryption_keys()

    format_output(
        result,
        is_list=False,
        output_format=resolved_output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
