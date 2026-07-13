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

        @app.command()
        def profile(
            path: str = typer.Argument(..., help="Path to a local directory of dataset files."),
            output: str = typer.Option("json", "--output", "-o", help="Output format: json | yaml."),
        ) -> None:
            """Profile a local dataset directory and print its DatasetProfile."""
            from nemo_datasets_plugin.profiler.file_source import LocalFileSource
            from nemo_datasets_plugin.profiler.pipeline import profile as run_profile

            if output not in {"json", "yaml"}:
                raise typer.BadParameter("output must be 'json' or 'yaml'")
            try:
                source = LocalFileSource(path)
            except NotADirectoryError as exc:
                raise typer.BadParameter(str(exc)) from exc

            result = run_profile(source)
            if output == "yaml":
                import yaml

                typer.echo(yaml.safe_dump(result.model_dump(mode="json"), sort_keys=False))
            else:
                typer.echo(result.model_dump_json(indent=2))

        return app
