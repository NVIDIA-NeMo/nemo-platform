# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from typing import Annotated, Literal

import typer

from nemo_platform.cli.core.api import build_kwargs, merge_filter_dict
from nemo_platform.cli.core.code_generator import handle_code_generation
from nemo_platform.cli.core.context import CLIContext
from nemo_platform.cli.core.errors import handle_errors
from nemo_platform.cli.core.formatters import Column, check_output_columns_with_format, format_output
from nemo_platform.cli.core.help_formatter import collect_warnings, create_typer_app
from nemo_platform.cli.core.pagination import PaginationType, fetch_all_pages, warn_if_more_pages
from nemo_platform.cli.core.types import ListOutputFormatOption, NoTruncateOption, OutputColumnsOption

app = create_typer_app(name="sessions", help="Manage sessions")


@app.command("list")
@collect_warnings
@handle_errors
def list_sessions(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    filter: Annotated[
        str | None,
        typer.Option(
            "--filter",
            metavar="FILTER_JSON",
            help="Use --filter with JSON for complex/nested queries, or --filter.FIELD options for simple fields. Both can be combined, with field options taking precedence.\n\nFilter sessions by test_case_id and status.",
            rich_help_panel="Filter Options",
        ),
    ] = None,
    filter_status: Annotated[str | None, typer.Option("--filter.status", rich_help_panel="Filter Options")] = None,
    filter_test_case_id: Annotated[
        str | None, typer.Option("--filter.test-case-id", rich_help_panel="Filter Options")
    ] = None,
    mode: Annotated[
        Literal["summary", "detailed"] | None,
        typer.Option(
            "--mode",
            help="Response payload mode. summary keeps the same session row fields but truncates root-span input to 1000 characters; detailed returns the full root-span input.",
        ),
    ] = None,
    page: Annotated[int | None, typer.Option("--page", help="Page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Page size.")] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """List Evaluation Sessions"""
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
        filter=merge_filter_dict(filter, status=filter_status, test_case_id=filter_test_case_id),
        mode=mode,
        page=page,
        page_size=page_size,
    )

    if handle_code_generation(["evaluations", "sessions"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = (name,)
    pagination_type = PaginationType.PAGE_NUMBER
    if all_pages:
        items = fetch_all_pages(
            client.evaluations.sessions.list,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.evaluations.sessions.list(*path_args, **kwargs)

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
