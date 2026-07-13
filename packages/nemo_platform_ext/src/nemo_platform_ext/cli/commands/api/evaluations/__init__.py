# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from importlib import import_module as _importlib_import_module
from typing import Annotated

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
)

_cli_child_sessions = _importlib_import_module("nemo_platform_ext.cli.commands.api.evaluations.sessions")

app = create_typer_app(name="evaluations", help="Manage evaluations")

app.add_typer(_cli_child_sessions.app, name="sessions")


@app.command("create")
@collect_warnings
@handle_errors
def create_evaluations(
    ctx: typer.Context,
    name: Annotated[
        str | None, typer.Argument(help="Producer-supplied, workspace-unique evaluation id. (required)")
    ] = None,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    dataset_name: Annotated[
        str | None, typer.Option("--dataset-name", help="Producer-supplied dataset name. (required)")
    ] = None,
    experiment_group_id: Annotated[
        str | None,
        typer.Option(
            "--experiment-group-id",
            help="Entity id of the owning ExperimentGroup. Required — the group must already exist. (required)",
        ),
    ] = None,
    dataset_version: Annotated[
        str | None, typer.Option("--dataset-version", help="Producer-supplied dataset version.")
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Human-readable description.")] = None,
    metadata: Annotated[
        str | None, typer.Option("--metadata", help="Free-form producer metadata. (JSON string)")
    ] = None,
    parent_evaluation_id: Annotated[
        str | None,
        typer.Option(
            "--parent-evaluation-id",
            help="Entity id of the evaluation this one was derived from (e.g. a variant of a baseline), if any.",
        ),
    ] = None,
    root_cause: Annotated[
        str | None,
        typer.Option(
            "--root-cause",
            help="Human- or agent-authored explanation of the evaluation's outcome (e.g. why it was killed).",
        ),
    ] = None,
    source_link: Annotated[
        str | None, typer.Option("--source-link", help="Optional URL for the source evaluation.")
    ] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="Producer-defined lifecycle status of the evaluation.")
    ] = None,
    exist_ok: Annotated[
        bool | None,
        typer.Option(
            "--exist-ok", help="Do not raise an error if the resource already exists. Returns the existing resource."
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
    """Create Evaluation

    [bold red]Required fields:[/] dataset_name, experiment_group_id, name

    [green]Examples:[/]
    nemo evaluations create <name> --input-file config.json
    nemo evaluations create <name> --input-data '{"dataset_name": "value", "experiment_group_id": "value", "name": "value"}'
    echo '{"json": "data"}' | nemo evaluations create <name> --input-file -
    nemo evaluations create <name> --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if workspace is not None:
        input_payload["workspace"] = workspace
    if dataset_name is not None:
        input_payload["dataset_name"] = dataset_name
    if experiment_group_id is not None:
        input_payload["experiment_group_id"] = experiment_group_id
    if name is not None:
        input_payload["name"] = name
    if dataset_version is not None:
        input_payload["dataset_version"] = dataset_version
    if description is not None:
        input_payload["description"] = description
    if metadata is not None:
        input_payload["metadata"] = read_payload("metadata", metadata)
    if parent_evaluation_id is not None:
        input_payload["parent_evaluation_id"] = parent_evaluation_id
    if root_cause is not None:
        input_payload["root_cause"] = root_cause
    if source_link is not None:
        input_payload["source_link"] = source_link
    if status is not None:
        input_payload["status"] = status
    if exist_ok is not None:
        input_payload["exist_ok"] = exist_ok
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["dataset_name", "experiment_group_id", "name"],
        "evaluations create",
        {
            "dataset_name": "Producer-supplied dataset name. (required)",
            "experiment_group_id": "Entity id of the owning ExperimentGroup. Required — the group must already exist. (required)",
            "name": "Producer-supplied, workspace-unique evaluation id. (required)",
        },
    )

    all_kwargs = input_payload
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["evaluations"], "create", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.evaluations.create(**all_kwargs)

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
def delete_evaluations(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
) -> None:
    """Delete Evaluation"""
    state: CLIContext = ctx.obj
    client = state.get_client()

    kwargs = build_kwargs(
        workspace=workspace,
    )
    client.evaluations.delete(name, **kwargs)

    typer.echo("✓ Deleted successfully")


@app.command("list")
@collect_warnings
@handle_errors
def list_evaluations(
    ctx: typer.Context,
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    filter: Annotated[
        str | None,
        typer.Option(
            "--filter",
            metavar="FILTER_JSON",
            help="Use --filter with JSON for complex/nested queries, or --filter.FIELD options for simple fields. Both can be combined, with field options taking precedence.\nJSON-only fields:\n  cost_usd: {count: NumberFilterParam, mean: NumberFilterParam, median: NumberFilterParam, p90: NumberFilterParam, p95: NumberFilterParam, p99: NumberFilterParam, sum: NumberFilterParam}\n  created_at: {gte: str, lte: str}\n  evaluators: dict[str, MetricStatFiltersParam]\n  latency_ms: {count: NumberFilterParam, mean: NumberFilterParam, median: NumberFilterParam, p90: NumberFilterParam, p95: NumberFilterParam, p99: NumberFilterParam, sum: NumberFilterParam}\n  run_count: {eq: float, gt: float, gte: float, lt: float, lte: float}\n  updated_at: {gte: str, lte: str}\n\nFilter evaluations by name, experiment_group_id, dataset_name, dataset_version, created_by, created_at, or updated_at. Pass is_deleted=true to return only soft-deleted evaluations; omit to see only live ones. Pass is_pinned=true (or false) to filter by pinned state; omit to return both. Filter by a rollup metric with numeric range operators ($gte/$lte/$gt/$lt/$eq): filter[run_count][$gte]=5, filter[cost_usd.mean][$lte]=0.5, filter[latency_ms.p95][$lte]=1000, or filter[evaluators.<name>.mean][$gte]=0.8.",
            rich_help_panel="Filter Options",
        ),
    ] = None,
    filter_created_by: Annotated[
        str | None, typer.Option("--filter.created-by", rich_help_panel="Filter Options")
    ] = None,
    filter_dataset_name: Annotated[
        str | None, typer.Option("--filter.dataset-name", rich_help_panel="Filter Options")
    ] = None,
    filter_dataset_version: Annotated[
        str | None, typer.Option("--filter.dataset-version", rich_help_panel="Filter Options")
    ] = None,
    filter_experiment_group_id: Annotated[
        str | None, typer.Option("--filter.experiment-group-id", rich_help_panel="Filter Options")
    ] = None,
    filter_is_deleted: Annotated[
        bool | None, typer.Option("--filter.is-deleted", rich_help_panel="Filter Options")
    ] = None,
    filter_is_pinned: Annotated[
        bool | None, typer.Option("--filter.is-pinned", rich_help_panel="Filter Options")
    ] = None,
    filter_name: Annotated[str | None, typer.Option("--filter.name", rich_help_panel="Filter Options")] = None,
    page: Annotated[int | None, typer.Option("--page", help="Page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Page size.")] = None,
    sort: Annotated[
        str | None,
        typer.Option(
            "--sort",
            help="Field to sort by; prefix with '-' for descending. Sort by an evaluation attribute (name, created_at, updated_at, pinned_at) or by an aggregate metric: run_count, cost_usd.<stat>, latency_ms.<stat>, or evaluators.<name>.<stat>, where <stat> is one of mean, median, p90, p95, p99, sum, count. When omitted, defaults to -created_at with pinned evaluations first.",
        ),
    ] = None,
    output_format: ListOutputFormatOption = None,
    no_truncate: NoTruncateOption = None,
    columns: OutputColumnsOption = None,
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Fetch all pages")] = False,
) -> None:
    """List Evaluations"""
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
            created_by=filter_created_by,
            dataset_name=filter_dataset_name,
            dataset_version=filter_dataset_version,
            experiment_group_id=filter_experiment_group_id,
            is_deleted=filter_is_deleted,
            is_pinned=filter_is_pinned,
            name=filter_name,
        ),
        page=page,
        page_size=page_size,
        sort=sort,
    )

    if handle_code_generation(["evaluations"], "list", kwargs, output_format, state):
        return

    client = state.get_client()
    path_args = ()
    pagination_type = PaginationType.PAGE_NUMBER
    if all_pages:
        items = fetch_all_pages(
            client.evaluations.list,
            path_args=path_args,
            body_args=kwargs,
            pagination_type=pagination_type,
        )
    else:
        items = client.evaluations.list(*path_args, **kwargs)

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


@app.command("pin")
@collect_warnings
@handle_errors
def pin_evaluations(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Pin an evaluation to the top of the list (workspace-shared).

    Re-pinning an already-pinned evaluation refreshes `pinned_at` to the current
    timestamp, which is intentional (most-recently-pinned sorts first)."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["evaluations"], "pin", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.evaluations.pin(name, **kwargs)

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
def retrieve_evaluations(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Get Evaluation"""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["evaluations"], "retrieve", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.evaluations.retrieve(name, **kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )


@app.command("unpin")
@collect_warnings
@handle_errors
def unpin_evaluations(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    output_format: EntityOutputFormatOption = None,
) -> None:
    """Unpin an evaluation.

    Idempotent: unpinning an already-unpinned evaluation is a
    no-op."""
    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    kwargs = build_kwargs(
        workspace=workspace,
    )
    if handle_code_generation(["evaluations"], "unpin", kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.evaluations.unpin(name, **kwargs)

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
def update_evaluations(
    ctx: typer.Context,
    path_name: Annotated[str, typer.Argument()],
    workspace: Annotated[str | None, typer.Option("--workspace")] = None,
    dataset_name: Annotated[
        str | None, typer.Option("--dataset-name", help="Producer-supplied dataset name. (required)")
    ] = None,
    experiment_group_id: Annotated[
        str | None,
        typer.Option(
            "--experiment-group-id",
            help="Entity id of the owning ExperimentGroup. Required — the group must already exist. (required)",
        ),
    ] = None,
    body_name: Annotated[
        str | None, typer.Option("--body-name", help="Producer-supplied, workspace-unique evaluation id. (required)")
    ] = None,
    dataset_version: Annotated[
        str | None, typer.Option("--dataset-version", help="Producer-supplied dataset version.")
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Human-readable description.")] = None,
    metadata: Annotated[
        str | None, typer.Option("--metadata", help="Free-form producer metadata. (JSON string)")
    ] = None,
    parent_evaluation_id: Annotated[
        str | None,
        typer.Option(
            "--parent-evaluation-id",
            help="Entity id of the evaluation this one was derived from (e.g. a variant of a baseline), if any.",
        ),
    ] = None,
    root_cause: Annotated[
        str | None,
        typer.Option(
            "--root-cause",
            help="Human- or agent-authored explanation of the evaluation's outcome (e.g. why it was killed).",
        ),
    ] = None,
    source_link: Annotated[
        str | None, typer.Option("--source-link", help="Optional URL for the source evaluation.")
    ] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="Producer-defined lifecycle status of the evaluation.")
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
    """Update Evaluation

    [bold red]Required fields:[/] dataset_name, experiment_group_id, body_name

    [green]Examples:[/]
    nemo evaluations update <path_name> --input-file config.json
    nemo evaluations update <path_name> --input-data '{"dataset_name": "value", "experiment_group_id": "value", "body_name": "value"}'
    echo '{"json": "data"}' | nemo evaluations update <path_name> --input-file -
    nemo evaluations update <path_name> --<option> "value"
    """
    # Read base input (optional if all fields provided via flags)
    if input_file or input_data:
        input_payload = read_data_input_with_flags(input_file=input_file, input_data=input_data)
    else:
        input_payload = {}

    # Apply CLI flag overrides (flags take precedence)
    if workspace is not None:
        input_payload["workspace"] = workspace
    if dataset_name is not None:
        input_payload["dataset_name"] = dataset_name
    if experiment_group_id is not None:
        input_payload["experiment_group_id"] = experiment_group_id
    if body_name is not None:
        input_payload["body_name"] = body_name
    if dataset_version is not None:
        input_payload["dataset_version"] = dataset_version
    if description is not None:
        input_payload["description"] = description
    if metadata is not None:
        input_payload["metadata"] = read_payload("metadata", metadata)
    if parent_evaluation_id is not None:
        input_payload["parent_evaluation_id"] = parent_evaluation_id
    if root_cause is not None:
        input_payload["root_cause"] = root_cause
    if source_link is not None:
        input_payload["source_link"] = source_link
    if status is not None:
        input_payload["status"] = status
    # Validate required fields are present after merging
    validate_required_fields(
        input_payload,
        ["dataset_name", "experiment_group_id", "body_name"],
        "evaluations update",
        {
            "dataset_name": "Producer-supplied dataset name. (required)",
            "experiment_group_id": "Entity id of the owning ExperimentGroup. Required — the group must already exist. (required)",
            "body_name": "Producer-supplied, workspace-unique evaluation id. (required)",
        },
    )

    all_kwargs = {"path_name": path_name, **input_payload}

    state: CLIContext = ctx.obj
    output_format = state.get_output_format(output_format)

    if handle_code_generation(["evaluations"], "update", all_kwargs, output_format, state):
        return

    client = state.get_client()
    result = client.evaluations.update(**all_kwargs)

    format_output(
        result,
        is_list=False,
        output_format=output_format,
        no_truncate=state.get_no_truncate(),
        timestamp_format=state.get_timestamp_format(),
    )
