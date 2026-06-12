# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI input overrides for the Data Designer ``preview`` and ``create`` verbs.

Replace the auto-generated per-leaf flags with a single ``[CONFIG_SOURCE]``
positional plus ``--num-records``, mirroring the upstream
``data-designer preview`` / ``data-designer create`` CLIs. The wrappers
delegate to the original auto-generated callbacks via ``--spec`` JSON, so
spec validation and frame iteration stay framework-owned.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import typer
from data_designer.cli.ui import print_error
from data_designer.cli.utils.config_loader import ConfigLoadError, load_config_builder
from data_designer.config.config_builder import DataDesignerConfigBuilder
from data_designer.config.utils.constants import DEFAULT_NUM_RECORDS

_NON_INTERACTIVE_HELP = (
    "Display all records at once instead of browsing interactively. Ignored when --save-results is used."
)
_SAVE_RESULTS_HELP = (
    "Save preview artifacts to disk (dataset.parquet, per-record HTML, analysis report) "
    "instead of displaying records in the terminal."
)
_ARTIFACT_PATH_HELP = "Directory for saved results (used with --save-results). Defaults to ./artifacts."

_CONFIG_SOURCE_HELP = (
    "Path or URL to a config file (.yaml/.yml/.json), "
    "or a local Python module (.py) that defines a load_config_builder() function."
)


# Stash the constructed builder so the renderer can pick it up. The renderer
# is instantiated by the framework with no constructor args, so a contextvar
# is the simplest plumbing — the wrapper sets it before calling the original
# callback (which then drives the renderer), and unsets it after.
_current_config_builder: contextvars.ContextVar[DataDesignerConfigBuilder | None] = contextvars.ContextVar(
    "_dd_current_config_builder", default=None
)


def get_current_config_builder() -> DataDesignerConfigBuilder | None:
    """Return the builder constructed by the active wrapper, if any.

    Used by ``cli/renderers.py`` to assemble :class:`PreviewResults` for the
    interactive record browser. Returns ``None`` outside a wrapper invocation.
    """
    return _current_config_builder.get()


@contextlib.contextmanager
def _spec_from_builder(config_source: str, num_records: int) -> Iterator[str]:
    try:
        builder = load_config_builder(config_source)
    except ConfigLoadError as e:
        print_error(f"Could not load config: {e}")
        raise typer.Exit(code=1) from e

    spec_json = _build_spec_from_builder(builder, num_records)
    token = _current_config_builder.set(builder)
    try:
        yield spec_json
    finally:
        _current_config_builder.reset(token)


def apply_preview_cli_overrides(group: typer.Typer) -> None:
    """Replace ``preview run`` / ``preview submit`` with friendly wrappers."""
    _replace_function_run(group)
    _replace_function_submit(group)


def apply_create_cli_overrides(group: typer.Typer) -> None:
    """Replace ``create run`` / ``create submit`` with friendly wrappers.

    Jobs also have an ``explain`` verb that prints schemas; it's not affected
    here because it doesn't take a config-source input.
    """
    _replace_job_run(group)
    _replace_job_submit(group)


def _build_spec_from_builder(builder: DataDesignerConfigBuilder, num_records: int) -> str:
    config = builder.build()
    spec = {"config": config.model_dump(mode="json"), "num_records": num_records}
    return json.dumps(spec)


def _pluck_callback(group: typer.Typer, verb: str) -> Callable[..., None]:
    callback = next(c for c in group.registered_commands if c.name == verb).callback
    assert callback is not None, f"missing {verb!r} callback to override"
    return callback


def _replace_function_run(group: typer.Typer) -> None:
    original = _pluck_callback(group, "run")

    @group.command("run")
    def run(
        typer_ctx: typer.Context,
        config_source: str = typer.Argument(..., metavar="[CONFIG_SOURCE]", help=_CONFIG_SOURCE_HELP),
        num_records: int = typer.Option(
            DEFAULT_NUM_RECORDS, "--num-records", "-n", help="Number of records to generate.", min=1
        ),
        workspace: str = typer.Option(
            "default", "--workspace", "-w", help="Workspace identity passed to the function as ctx.workspace."
        ),
        non_interactive: bool = typer.Option(False, "--non-interactive", help=_NON_INTERACTIVE_HELP),
        save_results: bool = typer.Option(False, "--save-results", help=_SAVE_RESULTS_HELP),
        artifact_path: str | None = typer.Option(None, "--artifact-path", "-o", help=_ARTIFACT_PATH_HELP),
    ) -> None:
        with _spec_from_builder(config_source, num_records) as spec:
            original(
                typer_ctx,
                spec=spec,
                spec_file=None,
                workspace=workspace,
                non_interactive=non_interactive,
                save_results=save_results,
                artifact_path=artifact_path,
            )


def _replace_function_submit(group: typer.Typer) -> None:
    original = _pluck_callback(group, "submit")

    @group.command("submit")
    def submit(
        typer_ctx: typer.Context,
        config_source: str = typer.Argument(..., metavar="[CONFIG_SOURCE]", help=_CONFIG_SOURCE_HELP),
        num_records: int = typer.Option(DEFAULT_NUM_RECORDS, "--num-records", "-n", min=1),
        workspace: str = typer.Option("default", "--workspace", "-w"),
        cluster: str | None = typer.Option(None, "--cluster"),
        base_url: str | None = typer.Option(None, "--base-url"),
        request_id: str | None = typer.Option(None, "--request-id"),
        non_interactive: bool = typer.Option(False, "--non-interactive", help=_NON_INTERACTIVE_HELP),
        save_results: bool = typer.Option(False, "--save-results", help=_SAVE_RESULTS_HELP),
        artifact_path: str | None = typer.Option(None, "--artifact-path", "-o", help=_ARTIFACT_PATH_HELP),
    ) -> None:
        with _spec_from_builder(config_source, num_records) as spec:
            original(
                typer_ctx,
                spec=spec,
                spec_file=None,
                cluster=cluster,
                base_url=base_url,
                workspace=workspace,
                request_id=request_id,
                non_interactive=non_interactive,
                save_results=save_results,
                artifact_path=artifact_path,
            )


def _replace_job_run(group: typer.Typer) -> None:
    original = _pluck_callback(group, "run")

    @group.command("run")
    def run(
        typer_ctx: typer.Context,
        config_source: str = typer.Argument(..., metavar="[CONFIG_SOURCE]", help=_CONFIG_SOURCE_HELP),
        num_records: int = typer.Option(
            DEFAULT_NUM_RECORDS, "--num-records", "-n", help="Number of records to generate.", min=1
        ),
    ) -> None:
        with _spec_from_builder(config_source, num_records) as spec:
            original(typer_ctx, spec=spec, spec_file=None, config=None, config_file=None)


def _replace_job_submit(group: typer.Typer) -> None:
    original = _pluck_callback(group, "submit")

    @group.command("submit")
    def submit(
        typer_ctx: typer.Context,
        config_source: str = typer.Argument(..., metavar="[CONFIG_SOURCE]", help=_CONFIG_SOURCE_HELP),
        num_records: int = typer.Option(DEFAULT_NUM_RECORDS, "--num-records", "-n", min=1),
        workspace: str = typer.Option("default", "--workspace", "-w"),
        profile: str | None = typer.Option(None, "--profile"),
        cluster: str | None = typer.Option(None, "--cluster"),
        base_url: str | None = typer.Option(None, "--base-url"),
        options: list[str] = typer.Option(  # noqa: B008 — Typer evaluates default lazily per invocation
            [],  # noqa: B006
            "-o",
            help="Backend option override, 'backend.key=value' (repeatable).",
        ),
        options_file: Path | None = typer.Option(None, "--options-file"),
    ) -> None:
        with _spec_from_builder(config_source, num_records) as spec:
            original(
                typer_ctx,
                spec=spec,
                spec_file=None,
                options=options,
                options_file=options_file,
                profile=profile,
                cluster=cluster,
                base_url=base_url,
                workspace=workspace,
                config=None,
                config_file=None,
            )
