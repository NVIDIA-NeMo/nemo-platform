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
from nemo_platform_ext.cli.core.types import (
    EntityOutputFormatOption,
    ListOutputFormatOption,
    NoTruncateOption,
    OutputColumnsOption,
)

app = create_typer_app(name="traces", help="Manage traces")


@app.command("list")
@collect_warnings
@handle_errors
def list_traces(
    ctx: typer.Context,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    filter: Annotated[
        str | None,
        typer.Option(
            "--filter",
            metavar="FILTER_JSON",
            help="Use --filter with JSON for complex/nested queries, or --filter.FIELD options for simple fields. Both can be combined, with field options taking precedence.\nJSON-only fields:\n  started_at: {gte: str, lte: str}\n\nFilter root-span-backed traces by id, session_id, rolled-up status, root span started_at, and root-span evaluation context fields.",
            rich_help_panel="Filter Options",
        ),
    ] = None,
    filter_id: Annotated[str | None, typer.Option("--filter.id", rich_help_panel="Filter Options")] = None,
    filter_dataset_id: Annotated[
        str | None, typer.Option("--filter.dataset-id", rich_help_panel="Filter Options")
    ] = None,
    filter_dataset_name: Annotated[
        str | None, typer.Option("--filter.dataset-name", rich_help_panel="Filter Options")
    ] = None,
    filter_dataset_version: Annotated[
        str | None, typer.Option("--filter.dataset-version", rich_help_panel="Filter Options")
    ] = None,
    filter_evaluation_id: Annotated[
        str | None, typer.Option("--filter.evaluation-id", rich_help_panel="Filter Options")
    ] = None,
    filter_evaluation_run_id: Annotated[
        str | None, typer.Option("--filter.evaluation-run-id", rich_help_panel="Filter Options")
    ] = None,
    filter_evaluation_sha: Annotated[
        str | None, typer.Option("--filter.evaluation-sha", rich_help_panel="Filter Options")
    ] = None,
    filter_session_id: Annotated[
        str | None, typer.Option("--filter.session-id", rich_help_panel="Filter Options")
    ] = None,
    filter_status: Annotated[str | None, typer.Option("--filter.status", rich_help_panel="Filter Options")] = None,
    filter_test_case_id: Annotated[
        str | None, typer.Option("--filter.test-case-id", rich_help_panel="Filter Options")
    ] = None,
    mode: Annotated[
        Literal["summary", "detailed"] | None,
        typer.Option(
            "--mode",
            help="Use summary for root-span trace fields only, or detailed to include token, cost, and span-count rollups.",
        ),
    ] = None,
    page: Annotated[int | None, typer.Option("--page", help="Page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Page size.")] = None,
    sort: Annotated[Literal["started_at", "-started_at"] | None, typer.Option("--sort")] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """List Traces"""
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
        filter=merge_filter_dict(
            filter,
            id=filter_id,
            dataset_id=filter_dataset_id,
            dataset_name=filter_dataset_name,
            dataset_version=filter_dataset_version,
            evaluation_id=filter_evaluation_id,
            evaluation_run_id=filter_evaluation_run_id,
            evaluation_sha=filter_evaluation_sha,
            session_id=filter_session_id,
            status=filter_status,
            test_case_id=filter_test_case_id,
        ),
        mode=mode,
        page=page,
        page_size=page_size,
        sort=sort,
    )

    if handle_code_generation(["intake", "traces"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = ()
    pagination_type = PaginationType.PAGE_NUMBER
    if all_pages:
        items = fetch_all_pages(
            client.intake.traces.list,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.intake.traces.list(*path_args, **kwargs)

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
def retrieve_traces(
    ctx: typer.Context,
    id: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    mode: Annotated[
        Literal["summary", "detailed"] | None,
        typer.Option(
            "--mode",
            help="Use summary for root-span trace fields only, or detailed to include token, cost, and span-count rollups.",
        ),
    ] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get Trace"""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
        mode=mode,
    )
    if handle_code_generation(["intake", "traces"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.intake.traces.retrieve(id, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
