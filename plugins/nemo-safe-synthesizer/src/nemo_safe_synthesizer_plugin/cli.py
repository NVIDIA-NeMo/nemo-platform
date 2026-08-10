# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Safe Synthesizer plugin CLI."""

from __future__ import annotations

from typing import ClassVar

import typer
from nemo_platform_plugin.cli import NemoCLI
from nemo_safe_synthesizer_plugin.config import config
from nemo_safe_synthesizer_plugin.runtime import runtime_info, setup_runtime


class SafeSynthesizerCLI(NemoCLI):
    """CLI extensions for managing the Safe Synthesizer runtime."""

    name: ClassVar[str] = "safe-synthesizer"
    description: ClassVar[str] = "Safe Synthesizer: privacy-preserving synthetic tabular data"

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(name=self.name, help=self.description, no_args_is_help=True)
        runtime_app = typer.Typer(help="Manage the separate Safe Synthesizer runtime venv.", no_args_is_help=True)

        @app.callback()
        def main() -> None:
            """Safe Synthesizer commands."""

        @runtime_app.command("setup")
        def setup_runtime_command(
            force: bool = typer.Option(False, "--force", help="Recreate the runtime virtualenv if it already exists."),
            package: str | None = typer.Option(
                None,
                "--package",
                help="Override the runtime package spec to install.",
            ),
            python_version: str | None = typer.Option(
                None,
                "--python",
                help="Python version or executable to pass to `uv venv --python`.",
            ),
        ) -> None:
            """Install Safe Synthesizer engine/CUDA dependencies into the runtime venv."""
            runtime_python = setup_runtime(
                config,
                force=force,
                package=package,
                python_version=python_version,
            )
            typer.echo(f"Safe Synthesizer runtime Python: {runtime_python}")

        @runtime_app.command("info")
        def runtime_info_command() -> None:
            """Print the configured Safe Synthesizer runtime."""
            for key, value in runtime_info(config).items():
                typer.echo(f"{key}: {value}")

        app.add_typer(runtime_app, name="runtime")
        return app
