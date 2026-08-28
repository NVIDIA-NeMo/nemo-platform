# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Anonymizer plugin CLI."""

from __future__ import annotations

import inspect
import io
import json
import tarfile
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType
from typing import Any, ClassVar, Literal, Optional, TextIO, cast
from urllib.parse import quote

import httpx
import typer
import yaml
from anonymizer.config.anonymizer_config import AnonymizerConfig
from nemo_anonymizer_plugin import cli_files
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest, PreviewRequest
from nemo_anonymizer_plugin.app.upstream_logging import preserve_root_logging
from nemo_anonymizer_plugin.functions.preview import PreviewFunction
from nemo_platform import NeMoPlatform
from nemo_platform_ext.cli.core.job_watch_renderer import render_job_watch_events
from nemo_platform_plugin._spec_flags import (
    UNSET,
    SpecLeafField,
    build_overlay,
    deep_merge,
    kw,
    walk_spec_leaves,
)
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.cli_errors import print_http_request_error, print_http_status_error
from nemo_platform_plugin.cli_renderer import CLIRenderer, RendererContext
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.commands import (
    _load_spec,
    _merge_options_inputs,
    _output_format_is_json,
    _resolve_submit_auth_headers,
    _resolve_submit_base_url,
)
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.jobs.archive import safe_extract_tar
from nemo_platform_plugin.jobs.client import JobsClient
from nemo_platform_plugin.scheduler import NemoJobScheduler
from pydantic import BaseModel, ValidationError

_ANONYMIZER_RUN_RESERVED_FLAGS = {
    "spec",
    "spec_file",
    "fileset",
    "input_remote_path",
    "output_dir",
    "options",
    "options_file",
    "profile",
    "cluster",
    "base_url",
    "workspace",
    "verbose",
    "dry_run",
    "watch",
    "timeout",
    "poll_interval",
    "include_history",
}

_ANONYMIZER_RUN_WRAPPER_FLAGS = {
    "config",
    "config_file",
    "fileset",
    "input_remote_path",
    "output_dir",
    "verbose",
    "dry_run",
    "watch",
    "timeout",
    "poll_interval",
    "include_history",
}

_ANONYMIZER_PREVIEW_RESERVED_FLAGS = {
    "spec",
    "spec_file",
    "cluster",
    "base_url",
    "workspace",
    "request_id",
    "fileset",
    "input_remote_path",
    "output_remote_path",
    "quiet",
    "output_file",
}


@dataclass(frozen=True)
class _RunCLIArgs:
    spec: str
    spec_file: Path | None
    fileset: str | None
    input_remote_path: str | None
    output_dir: Path | None
    options: list[str]
    options_file: Path | None
    profile: str | None
    cluster: str | None
    base_url: str | None
    workspace: str
    verbose: bool
    dry_run: bool
    watch: bool
    timeout: int | None
    poll_interval: int
    include_history: bool


@dataclass(frozen=True)
class _RunSubmission:
    spec: dict[str, Any]
    options: dict[str, Any] | None
    metadata: dict[str, str] | None
    base_url: str
    headers: dict[str, str]
    platform_client: NeMoPlatform | None


class AnonymizerCLI(NemoCLI):
    name: ClassVar[str] = "anonymizer"
    description: ClassVar[str] = "Anonymizer: detect and replace/rewrite PII in text data"

    def get_cli(self) -> typer.Typer:
        # ``preview`` and ``run`` are generated from NemoFunction/NemoJob
        # entry points, then customized through the hooks below.
        app = typer.Typer(name=self.name, help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            # Keep Typer in command-group mode for explicit manual commands.
            pass

        app.command("validate")(validate_command)
        return app

    def update_function_cli(self, fn_cls: type[NemoFunction], group: typer.Typer) -> None:
        if fn_cls is PreviewFunction:
            _install_anonymizer_preview_verb(group)

    def update_job_cli(self, job_cls: type[NemoJob], group: typer.Typer) -> None:
        if job_cls.name != "run" or job_cls.input_spec_schema is not AnonymizerRequest:
            return

        _install_anonymizer_run_verb(group, service=self.name, job_cls=job_cls)

    def get_function_renderer(
        self,
        fn_cls: type[NemoFunction],
        *,
        verb: Literal["run", "submit"],
    ) -> type[CLIRenderer] | None:
        if fn_cls is PreviewFunction and verb == "submit":
            return AnonymizerPreviewRenderer
        return None

    def get_job_renderer(
        self,
        job_cls: type[NemoJob],
        *,
        verb: Literal["run", "submit"],
    ) -> type[CLIRenderer] | None:
        if job_cls.name == "run" and job_cls.input_spec_schema is AnonymizerRequest and verb == "submit":
            return AnonymizerRunRenderer
        return None


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise typer.BadParameter(f"{path}: expected a YAML mapping at top level")
    return data


def _build_anonymizer_config(payload: dict[str, Any]) -> AnonymizerConfig:
    return AnonymizerConfig.model_validate(payload)


def _make_local_anonymizer(
    *,
    model_configs: str | Path | None,
    artifact_path: Path | None = None,
) -> Any:
    from anonymizer.interface.anonymizer import Anonymizer

    kwargs: dict[str, Any] = {"model_configs": model_configs}
    if artifact_path is not None:
        kwargs["artifact_path"] = artifact_path
    with preserve_root_logging():
        return Anonymizer(**kwargs)


def validate_command(
    config: Path = typer.Option(..., "--config", help="Path to AnonymizerConfig YAML."),
    model_configs: Optional[Path] = typer.Option(None, "--model-configs"),
) -> None:
    """Validate an AnonymizerConfig against the model selection."""
    anonymizer_config = _build_anonymizer_config(_load_yaml(config))
    anonymizer = _make_local_anonymizer(model_configs=str(model_configs) if model_configs else None)
    anonymizer.validate_config(anonymizer_config)
    typer.echo("Config is valid.")


def _install_anonymizer_run_verb(
    group: typer.Typer,
    *,
    service: str,
    job_cls: type[NemoJob],
) -> None:
    original = _pluck_command_callback(group, "run")
    scheduler = _pluck_command_scheduler(original)
    resource_name = f"{service}.{job_cls.name}"
    schema = job_cls.input_spec_schema or job_cls.spec_schema
    leaves = walk_spec_leaves(schema, reserved=_ANONYMIZER_RUN_RESERVED_FLAGS)

    def run(typer_ctx: typer.Context, **kwargs: object) -> None:
        """Submit an anonymizer run job to NeMo Platform."""
        _run_anonymizer_run_command(
            scheduler=scheduler,
            job_cls=job_cls,
            resource_name=resource_name,
            original=original,
            typer_ctx=typer_ctx,
            leaves=leaves,
            kwargs=dict(kwargs),
        )

    setattr(run, "__signature__", _build_anonymizer_run_signature(original))
    _replace_command(group, "run", run, rich_help_panel="Jobs")


def _run_anonymizer_run_command(
    *,
    scheduler: NemoJobScheduler,
    job_cls: type[NemoJob],
    resource_name: str,
    original: Callable[..., None],
    typer_ctx: typer.Context,
    leaves: list[SpecLeafField],
    kwargs: dict[str, object],
) -> None:
    args = _parse_run_cli_args(kwargs)
    _validate_run_cli_args(args)
    if _output_format_is_json(typer_ctx) and args.watch:
        typer.echo("Error: --watch cannot be combined with JSON output.", err=True)
        raise typer.Exit(code=2)

    try:
        submission = _prepare_run_submission(typer_ctx=typer_ctx, args=args, leaves=leaves, kwargs=kwargs)
        if args.verbose or args.dry_run:
            for document in _build_remote_job_diagnostics(scheduler, job_cls, args=args, submission=submission):
                typer.echo(json.dumps(document, indent=2))
            if args.dry_run:
                return

        run_result: dict[str, object] = {}
        _delegate_run_submission(
            original,
            scheduler=scheduler,
            typer_ctx=typer_ctx,
            args=args,
            submission=submission,
            kwargs=kwargs,
            run_result=run_result,
        )
    except ValidationError as exc:
        typer.echo(f"Error: invalid run spec: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"Error: unable to write run output: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except httpx.HTTPStatusError as exc:
        print_http_status_error(exc, action=f"submit {resource_name}")
        raise typer.Exit(code=2) from exc
    except httpx.RequestError as exc:
        print_http_request_error(exc, action=f"submit {resource_name}")
        raise typer.Exit(code=2) from exc
    except httpx.HTTPError as exc:
        typer.echo(f"Error: submit {resource_name} failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if args.watch:
        result = cast(dict[str, object] | None, run_result.get("job"))
        if result is None:
            typer.echo(f"Error: Unable to determine submitted {resource_name} job name for --watch", err=True)
            raise typer.Exit(code=1)
        _watch_run_job(
            resource_name=resource_name,
            submission=submission,
            args=args,
            result=result,
            platform_client=submission.platform_client,
        )


def _parse_run_cli_args(kwargs: dict[str, object]) -> _RunCLIArgs:
    return _RunCLIArgs(
        spec=cast(str, kwargs.pop("spec", "{}")),
        spec_file=cast(Path | None, kwargs.pop("spec_file", None)),
        fileset=cast(str | None, kwargs.pop("fileset", None)),
        input_remote_path=cast(str | None, kwargs.pop("input_remote_path", None)),
        output_dir=cast(Path | None, kwargs.pop("output_dir", None)),
        options=cast(list[str], kwargs.pop("options", [])),
        options_file=cast(Path | None, kwargs.pop("options_file", None)),
        profile=cast(str | None, kwargs.pop("profile", None)),
        cluster=cast(str | None, kwargs.pop("cluster", None)),
        base_url=cast(str | None, kwargs.pop("base_url", None)),
        workspace=cast(str, kwargs.pop("workspace", "default")),
        verbose=cast(bool, kwargs.pop("verbose", False)),
        dry_run=cast(bool, kwargs.pop("dry_run", False)),
        watch=cast(bool, kwargs.pop("watch", False)),
        timeout=cast(int | None, kwargs.pop("timeout", None)),
        poll_interval=cast(int, kwargs.pop("poll_interval", 3)),
        include_history=cast(bool, kwargs.pop("include_history", True)),
    )


def _validate_run_cli_args(args: _RunCLIArgs) -> None:
    if args.dry_run and args.watch:
        typer.echo("Error: --dry-run cannot be combined with --watch.", err=True)
        raise typer.Exit(code=2)
    if args.output_dir is not None and args.dry_run:
        typer.echo("Error: --output-dir cannot be combined with --dry-run.", err=True)
        raise typer.Exit(code=2)
    if args.output_dir is not None and not args.watch:
        typer.echo("Error: --output-dir requires --watch so artifacts are available before download.", err=True)
        raise typer.Exit(code=2)


def _prepare_run_submission(
    *,
    typer_ctx: typer.Context,
    args: _RunCLIArgs,
    leaves: list[SpecLeafField],
    kwargs: dict[str, object],
) -> _RunSubmission:
    base = _load_spec(args.spec, args.spec_file)
    overlay = build_overlay(leaves, kwargs, unset_sentinel=UNSET)
    spec_data = deep_merge(base, overlay)
    options = cast(dict[str, Any], _merge_options_inputs(args.options, args.options_file)) or None
    base_url = _resolve_submit_base_url(typer_ctx, base_url=args.base_url, cluster=args.cluster)
    headers = _resolve_submit_auth_headers(typer_ctx)
    request = AnonymizerRequest.model_validate(spec_data)

    platform_client: NeMoPlatform | None = None
    if args.fileset is not None and not args.dry_run:
        platform_client = cli_files.make_platform_client(
            base_url=base_url,
            workspace=args.workspace,
            headers=headers,
        )
    staged_request = cli_files.stage_anonymizer_request_for_remote(
        request,
        platform_client=platform_client,
        workspace=args.workspace,
        fileset=args.fileset,
        input_remote_path=args.input_remote_path,
        upload=not args.dry_run,
    )
    request = staged_request.request
    if args.fileset is not None and not args.dry_run and not staged_request.source_was_local:
        if platform_client is None:
            raise ValueError("--fileset requires a platform client.")
        cli_files.ensure_fileset_exists(platform_client, workspace=args.workspace, fileset=args.fileset)

    return _RunSubmission(
        spec=request.model_dump(mode="json", exclude_none=True),
        options=options,
        metadata={"output_location": args.fileset} if args.fileset is not None else None,
        base_url=base_url,
        headers=headers,
        platform_client=platform_client,
    )


def _delegate_run_submission(
    original: Callable[..., None],
    *,
    scheduler: NemoJobScheduler,
    typer_ctx: typer.Context,
    args: _RunCLIArgs,
    submission: _RunSubmission,
    kwargs: dict[str, object],
    run_result: dict[str, object],
) -> None:
    delegate_kwargs = dict(kwargs)
    delegate_kwargs.pop("config", None)
    delegate_kwargs.pop("config_file", None)
    delegate_kwargs.update(
        {
            "spec": json.dumps(submission.spec),
            "spec_file": None,
            "options": args.options,
            "options_file": args.options_file,
            "profile": args.profile,
            "cluster": None,
            "base_url": submission.base_url,
            "workspace": args.workspace,
            "_run_result": run_result,
        }
    )
    with _inject_submit_metadata(scheduler, submission.metadata):
        original(typer_ctx, **delegate_kwargs)


def _watch_run_job(
    *,
    resource_name: str,
    submission: _RunSubmission,
    args: _RunCLIArgs,
    result: dict[str, object],
    platform_client: NeMoPlatform | None,
) -> None:
    job_name = result.get("name")
    if not job_name:
        typer.echo(f"Error: Unable to determine submitted {resource_name} job name for --watch", err=True)
        raise typer.Exit(code=1)

    platform_client = platform_client or cli_files.make_platform_client(
        base_url=submission.base_url,
        workspace=args.workspace,
        headers=submission.headers,
    )
    job_workspace = cast(str, result.get("workspace") or args.workspace)
    jobs_client = client_from_platform(platform_client, JobsClient)
    events = jobs_client.watch_job(
        cast(str, job_name),
        workspace=job_workspace,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
        include_history=args.include_history,
    )
    if not _watch_render_succeeded(render_job_watch_events(events, resource_label="job")):
        raise typer.Exit(code=1)

    if args.output_dir is not None:
        _download_run_artifacts(
            _build_run_artifacts_download_url(
                submission.base_url,
                workspace=job_workspace,
                job_name=cast(str, job_name),
            ),
            headers=submission.headers,
            output_dir=args.output_dir,
        )
        typer.echo(f"Downloaded run artifacts to {args.output_dir / 'artifacts'}", err=True)


def _build_remote_job_diagnostics(
    scheduler: NemoJobScheduler,
    job_cls: type[NemoJob],
    *,
    args: _RunCLIArgs,
    submission: _RunSubmission,
) -> list[dict[str, Any]]:
    return [
        scheduler.explain(job_cls, profile=args.profile),
        {
            "method": "POST",
            "url": scheduler._build_submit_url(
                job_cls,
                base_url=submission.base_url,
                workspace=args.workspace,
            ),
            "body": scheduler._build_submit_body(
                submission.spec,
                profile=args.profile,
                options=submission.options,
                metadata=submission.metadata,
            ),
        },
    ]


def _build_anonymizer_run_signature(original: Callable[..., None]) -> inspect.Signature:
    params = [
        param
        for param in inspect.signature(original).parameters.values()
        if param.name not in _ANONYMIZER_RUN_WRAPPER_FLAGS
    ]
    params.extend(
        [
            kw(
                "fileset",
                Optional[str],
                typer.Option(
                    None,
                    "--fileset",
                    help="Fileset used for local input upload and run artifacts.",
                    rich_help_panel="Files",
                ),
            ),
            kw(
                "input_remote_path",
                Optional[str],
                typer.Option(
                    None,
                    "--input-remote-path",
                    help="Path inside --fileset for an uploaded local input file. Defaults to the local filename.",
                    rich_help_panel="Files",
                ),
            ),
            kw(
                "output_dir",
                Optional[Path],
                typer.Option(
                    None,
                    "--output-dir",
                    help="Download run artifacts to this local directory after --watch completes.",
                    rich_help_panel="Output",
                ),
            ),
            kw(
                "verbose",
                bool,
                typer.Option(
                    False,
                    "--verbose",
                    help="Print the job schema and resolved submit request before creating the job.",
                    rich_help_panel="Submission",
                ),
            ),
            kw(
                "dry_run",
                bool,
                typer.Option(
                    False,
                    "--dry-run",
                    help="Print the job schema and resolved submit request without creating a job.",
                    rich_help_panel="Submission",
                ),
            ),
            kw(
                "watch",
                bool,
                typer.Option(
                    False,
                    "--watch",
                    help="Watch the submitted job to a terminal state.",
                    rich_help_panel="Watch",
                ),
            ),
            kw(
                "timeout",
                Optional[int],
                typer.Option(
                    None,
                    "--timeout",
                    min=1,
                    help="Maximum watch time in seconds.",
                    rich_help_panel="Watch",
                ),
            ),
            kw(
                "poll_interval",
                int,
                typer.Option(
                    3,
                    "--poll-interval",
                    min=1,
                    help="Seconds between status checks.",
                    rich_help_panel="Watch",
                ),
            ),
            kw(
                "include_history",
                bool,
                typer.Option(
                    True,
                    "--history/--no-history",
                    help="Include logs already present before watching.",
                    rich_help_panel="Watch",
                ),
            ),
        ]
    )
    return inspect.Signature(parameters=params)


def _install_anonymizer_preview_verb(group: typer.Typer) -> None:
    original = _pluck_command_callback(group, "preview")

    def preview(
        typer_ctx: typer.Context,
        **kwargs: object,
    ) -> None:
        """Run a streaming preview through the Anonymizer service."""
        _run_preview_function_wrapper(
            original,
            typer_ctx=typer_ctx,
            kwargs=dict(kwargs),
        )

    setattr(preview, "__signature__", _build_anonymizer_preview_signature(original))
    _replace_command(group, "preview", preview, rich_help_panel="Functions")


def _build_anonymizer_preview_signature(original: Callable[..., None]) -> inspect.Signature:
    params = list(inspect.signature(original).parameters.values())
    params.extend(
        [
            kw(
                "fileset",
                Optional[str],
                typer.Option(
                    None,
                    "--fileset",
                    help="Fileset used for local input upload and optional preview output upload.",
                    rich_help_panel="Files",
                ),
            ),
            kw(
                "input_remote_path",
                Optional[str],
                typer.Option(
                    None,
                    "--input-remote-path",
                    help="Path inside --fileset for an uploaded local input file. Defaults to the local filename.",
                    rich_help_panel="Files",
                ),
            ),
            kw(
                "output_remote_path",
                Optional[str],
                typer.Option(
                    None,
                    "--output-remote-path",
                    help="Path inside --fileset for saved preview NDJSON output.",
                    rich_help_panel="Files",
                ),
            ),
            kw(
                "quiet",
                bool,
                typer.Option(
                    False,
                    "--quiet",
                    help="Suppress preview log frames on stderr.",
                    rich_help_panel="Output",
                ),
            ),
            kw(
                "output_file",
                Optional[Path],
                typer.Option(
                    None,
                    "--output-file",
                    help="Write non-log preview frames to an NDJSON file instead of stdout.",
                    rich_help_panel="Output",
                ),
            ),
        ]
    )
    return inspect.Signature(parameters=params)


def _pluck_command_callback(group: typer.Typer, command_name: str) -> Callable[..., None]:
    for command in reversed(group.registered_commands):
        if command.name == command_name and command.callback is not None:
            return command.callback
    raise RuntimeError(f"missing generated {command_name!r} command")


def _pluck_command_scheduler(callback: Callable[..., None]) -> NemoJobScheduler:
    if not isinstance(callback, FunctionType):
        raise RuntimeError("missing generated run command scheduler")

    closure = callback.__closure__
    if closure is None:
        raise RuntimeError("missing generated run command scheduler")

    for name, cell in zip(callback.__code__.co_freevars, closure, strict=False):
        if name != "scheduler":
            continue
        scheduler = cell.cell_contents
        if isinstance(scheduler, NemoJobScheduler):
            return scheduler

    raise RuntimeError("missing generated run command scheduler")


def _replace_command(
    group: typer.Typer,
    command_name: str,
    callback: Callable[..., None],
    *,
    rich_help_panel: str,
) -> None:
    original_count = len(group.registered_commands)
    group.registered_commands[:] = [command for command in group.registered_commands if command.name != command_name]
    if len(group.registered_commands) == original_count:
        raise RuntimeError(f"missing generated {command_name!r} command")
    group.command(command_name, rich_help_panel=rich_help_panel)(callback)


def _run_preview_function_wrapper(
    original: Callable[..., None],
    *,
    typer_ctx: typer.Context,
    kwargs: dict[str, object],
) -> None:
    spec = cast(str, kwargs.pop("spec", "{}"))
    spec_file = cast(Path | None, kwargs.pop("spec_file", None))
    cluster = cast(str | None, kwargs.pop("cluster", None))
    base_url = cast(str | None, kwargs.pop("base_url", None))
    workspace = cast(str, kwargs.pop("workspace", "default"))
    request_id = cast(str | None, kwargs.pop("request_id", None))
    fileset = cast(str | None, kwargs.pop("fileset", None))
    input_remote_path = cast(str | None, kwargs.pop("input_remote_path", None))
    output_remote_path = cast(str | None, kwargs.pop("output_remote_path", None))
    quiet = cast(bool, kwargs.pop("quiet", False))
    output_file = cast(Path | None, kwargs.pop("output_file", None))

    if _output_format_is_json(typer_ctx) and (quiet or output_file is not None or output_remote_path is not None):
        typer.echo(
            "Error: --quiet, --output-file, and --output-remote-path cannot be combined with JSON output.", err=True
        )
        raise typer.Exit(code=2)

    spec_data = _load_spec(spec, spec_file)
    overlay = build_overlay(
        walk_spec_leaves(PreviewRequest, reserved=_ANONYMIZER_PREVIEW_RESERVED_FLAGS),
        kwargs,
        unset_sentinel=UNSET,
    )
    spec_data = deep_merge(spec_data, overlay)
    try:
        request = PreviewRequest.model_validate(spec_data)
    except ValidationError as exc:
        typer.echo(f"Error: invalid preview spec: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        resolved_base_url = _resolve_submit_base_url(typer_ctx, base_url=base_url, cluster=cluster)
        headers = _resolve_submit_auth_headers(typer_ctx)
        if request_id is not None:
            headers["X-Request-ID"] = request_id
        platform_client = cli_files.make_platform_client(
            base_url=resolved_base_url,
            workspace=workspace,
            headers=headers,
        )
        staged_request = cli_files.stage_anonymizer_request_for_remote(
            request,
            platform_client=platform_client,
            workspace=workspace,
            fileset=fileset,
            input_remote_path=input_remote_path,
            upload=True,
            quiet=quiet,
        )
        request = staged_request.request
        if output_remote_path is not None and fileset is None:
            raise ValueError("--output-remote-path requires --fileset.")
        if output_remote_path is not None:
            cli_files.validate_remote_file_path(output_remote_path, option_name="--output-remote-path")
            cli_files.ensure_fileset_exists(platform_client, workspace=workspace, fileset=cast(str, fileset))

        preview_status = {"succeeded": True}
        with _preview_capture_path(output_file=output_file, output_remote_path=output_remote_path) as capture_file:
            original(
                typer_ctx,
                spec=json.dumps(request.model_dump(mode="json", exclude_none=True)),
                spec_file=None,
                cluster=cluster,
                base_url=base_url,
                workspace=workspace,
                request_id=request_id,
                quiet=quiet,
                output_file=output_file,
                _capture_file=capture_file,
                _preview_status=preview_status,
            )
            if not preview_status["succeeded"]:
                raise typer.Exit(code=1)
            if output_remote_path is not None:
                cli_files.upload_file_to_fileset(
                    platform_client,
                    local_path=output_file or cast(Path, capture_file),
                    remote_path=output_remote_path,
                    fileset=cast(str, fileset),
                    workspace=workspace,
                    description="preview output",
                    quiet=quiet,
                )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"Error: unable to write preview output: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except httpx.HTTPStatusError as exc:
        print_http_status_error(exc, action="preview anonymizer")
        raise typer.Exit(code=2) from exc
    except httpx.RequestError as exc:
        print_http_request_error(exc, action="preview anonymizer")
        raise typer.Exit(code=2) from exc
    except httpx.HTTPError as exc:
        typer.echo(f"Error: preview anonymizer failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc


class AnonymizerPreviewRenderer(CLIRenderer):
    def __init__(self) -> None:
        self._stack = ExitStack()
        self._output: TextIO | None = None
        self._capture: TextIO | None = None
        self._quiet = False
        self._error_seen = False

    def on_start(self, *, ctx: RendererContext) -> None:
        self._quiet = bool(ctx.cli_kwargs.get("quiet"))
        output_file = _optional_path(ctx.cli_kwargs.get("output_file"))
        capture_file = _optional_path(ctx.cli_kwargs.get("_capture_file"))
        self._output = self._stack.enter_context(output_file.open("w")) if output_file is not None else None
        self._capture = self._stack.enter_context(capture_file.open("w")) if capture_file is not None else None

    def on_frame(self, frame: Any, *, ctx: RendererContext) -> None:
        del ctx
        line = frame.model_dump_json(exclude_none=True) if isinstance(frame, BaseModel) else json.dumps(frame)
        self._error_seen = (
            _emit_preview_line(
                line,
                quiet=self._quiet,
                output=self._output,
                capture=self._capture,
            )
            or self._error_seen
        )

    def on_complete(self, *, ctx: RendererContext) -> None:
        self._set_status(ctx)
        self._stack.close()

    def on_error(self, error: BaseException, *, ctx: RendererContext) -> None:
        del error
        self._set_status(ctx)
        self._stack.close()

    def _set_status(self, ctx: RendererContext) -> None:
        status = ctx.cli_kwargs.get("_preview_status")
        if isinstance(status, dict):
            status["succeeded"] = not self._error_seen


class AnonymizerRunRenderer(CLIRenderer):
    def on_frame(self, frame: Any, *, ctx: RendererContext) -> None:
        result = ctx.cli_kwargs.get("_run_result")
        if isinstance(result, dict) and isinstance(frame, dict):
            result["job"] = frame
        typer.echo(json.dumps(frame, indent=2))


def _optional_path(value: object) -> Path | None:
    return value if isinstance(value, Path) else None


def _build_run_artifacts_download_url(base_url: str, *, workspace: str, job_name: str) -> str:
    workspace_segment = quote(workspace, safe="")
    job_segment = quote(job_name, safe="")
    return (
        f"{base_url.rstrip('/')}/apis/anonymizer/v2/workspaces/{workspace_segment}"
        f"/jobs/run/{job_segment}/results/artifacts/download"
    )


@contextmanager
def _preview_capture_path(
    *,
    output_file: Path | None,
    output_remote_path: str | None,
) -> Iterator[Path | None]:
    if output_remote_path is None:
        yield None
        return
    if output_file is not None:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="nemo-anonymizer-preview-") as temp_dir:
        yield Path(temp_dir) / "preview.ndjson"


_SUBMIT_REMOTE_SENTINEL = object()


@contextmanager
def _inject_submit_metadata(
    scheduler: NemoJobScheduler,
    submit_metadata: dict[str, str] | None,
) -> Iterator[None]:
    previous = scheduler.__dict__.get("submit_remote", _SUBMIT_REMOTE_SENTINEL)
    submit_remote = scheduler.submit_remote

    def submit_remote_with_metadata(
        job_cls: type[NemoJob],
        spec: dict,
        *,
        base_url: str | None = None,
        workspace: str = "default",
        profile: str | None = None,
        options: dict | None = None,
        metadata: dict | None = None,
        http_client: httpx.Client | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict:
        del metadata
        submit_kwargs: dict[str, Any] = {
            "base_url": base_url,
            "workspace": workspace,
            "profile": profile,
            "options": options,
            "metadata": submit_metadata,
            "headers": headers,
        }
        if http_client is not None:
            submit_kwargs["http_client"] = http_client
        if timeout != 30.0:
            submit_kwargs["timeout"] = timeout
        return submit_remote(job_cls, spec, **submit_kwargs)

    setattr(scheduler, "submit_remote", submit_remote_with_metadata)
    try:
        yield
    finally:
        if previous is _SUBMIT_REMOTE_SENTINEL:
            delattr(scheduler, "submit_remote")
        else:
            setattr(scheduler, "submit_remote", previous)


def _emit_preview_line(
    line: str,
    *,
    quiet: bool,
    output: TextIO | None = None,
    capture: TextIO | None = None,
) -> bool:
    try:
        frame = json.loads(line)
    except json.JSONDecodeError:
        _write_preview_output(line, output, capture=capture)
        return False
    if not isinstance(frame, dict):
        _write_preview_output(json.dumps(frame), output, capture=capture)
        return False

    kind = frame.get("kind")
    if kind == "log":
        if not quiet:
            message = frame.get("message")
            typer.echo(str(message) if message is not None else json.dumps(frame), err=True)
        return False

    _write_preview_output(json.dumps(frame), output, capture=capture)
    return kind == "error"


def _write_preview_output(line: str, output: TextIO | None, *, capture: TextIO | None = None) -> None:
    if output is None:
        typer.echo(line)
    else:
        output.write(f"{line}\n")
        output.flush()
    if capture is not None:
        capture.write(f"{line}\n")
        capture.flush()


def _download_run_artifacts(
    url: str,
    *,
    headers: dict[str, str],
    output_dir: Path,
    timeout: float = 300.0,
) -> None:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, headers=headers)
        if response.status_code >= 400:
            response.raise_for_status()
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:*") as tar:
            safe_extract_tar(tar, output_dir)


def _watch_render_succeeded(result: object) -> bool:
    return result is True or result == "succeeded"
