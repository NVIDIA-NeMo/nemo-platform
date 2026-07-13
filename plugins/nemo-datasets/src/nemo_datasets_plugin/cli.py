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
            # The profiling core lands in a follow-up commit; this wires up the command surface.
            raise typer.BadParameter("dataset profiling is not implemented yet")

        return app
