# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The ``nemo datasets`` CLI — registered under the ``nemo.cli`` entry point."""

from __future__ import annotations

import typer
from nemo_platform_plugin.cli import NemoCLI


class DatasetsCLI(NemoCLI):
    """Exposes dataset commands as ``nemo datasets ...``."""

    name = "datasets"
    description = "Profile datasets stored as filesets."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help="Dataset profiling commands.")

        @app.callback()
        def _root() -> None:
            """Dataset profiling commands."""
            # A no-op callback keeps ``profile`` an explicit subcommand (``nemo datasets profile
            # <path>``) instead of Typer collapsing the lone command into ``nemo datasets <path>``,
            # which would break the moment a second command is added.

        @app.command()
        def profile(
            path: str = typer.Argument(..., help="Path to a local directory of dataset files."),
            output: str = typer.Option("json", "--output", "-o", help="Output format: json | yaml."),
            rows_per_file: int = typer.Option(
                None,
                "--rows-per-file",
                help="Rows to read from each file (default 1000); 0 reads every row, which is exact "
                "but scales memory with the dataset rather than the file count.",
                min=0,
            ),
            column_role: list[str] = typer.Option(
                None,
                "--column-role",
                help="Assert a column's role as NAME=ROLE (repeatable), e.g. --column-role q=prompt. "
                "Takes precedence over name detection, but the dtype must still support the role; a "
                "rejected hint is reported in the profile's evidence.",
                metavar="NAME=ROLE",
            ),
        ) -> None:
            """Profile a local dataset directory and print its DatasetProfile."""
            # Imported here, not at module scope: the platform calls get_cli() for every plugin at
            # startup, and the profiler pulls in pyarrow. The row-cap default lives in the pipeline
            # rather than being restated here, so an unspecified flag simply omits the argument.
            from nemo_datasets_plugin.profiler.file_source import LocalFileSource
            from nemo_datasets_plugin.profiler.pipeline import profile as run_profile

            if output not in {"json", "yaml"}:
                raise typer.BadParameter("output must be 'json' or 'yaml'")
            column_roles: dict[str, str] = {}
            for pair in column_role or []:
                name, separator, role = pair.partition("=")
                if not separator or not name or not role:
                    raise typer.BadParameter(f"--column-role expects NAME=ROLE, got {pair!r}")
                column_roles[name] = role
            try:
                source = LocalFileSource(path)
            except NotADirectoryError as exc:
                raise typer.BadParameter(str(exc)) from exc

            if rows_per_file is None:
                result = run_profile(source, column_roles=column_roles)
            else:
                result = run_profile(source, row_cap=rows_per_file or None, column_roles=column_roles)
            if output == "yaml":
                import yaml

                typer.echo(yaml.safe_dump(result.model_dump(mode="json"), sort_keys=False))
            else:
                typer.echo(result.model_dump_json(indent=2))

        return app
