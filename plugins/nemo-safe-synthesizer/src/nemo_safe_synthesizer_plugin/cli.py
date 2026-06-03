# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Safe Synthesizer plugin CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import ClassVar

import typer
from nemo_platform_plugin.cli import NemoCLI
from nemo_safe_synthesizer_plugin.config import config
from nemo_safe_synthesizer_plugin.runtime import runtime_info, runtime_task_command, setup_runtime


class SafeSynthesizerCLI(NemoCLI):
    """CLI extensions for host-local Safe Synthesizer development."""

    name: ClassVar[str] = "safe-synthesizer"
    description: ClassVar[str] = "Safe Synthesizer: privacy-preserving synthetic tabular data"

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(name=self.name, help=self.description, no_args_is_help=True)
        runtime_app = typer.Typer(help="Manage the separate Safe Synthesizer runtime venv.", no_args_is_help=True)

        @app.callback()
        def main() -> None:
            """Safe Synthesizer host-local development commands."""

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

        @app.command("run-local")
        def run_local_command(
            spec_file: Path = typer.Option(
                ...,
                "--spec-file",
                exists=True,
                file_okay=True,
                dir_okay=False,
                readable=True,
                help="NSS job spec JSON file.",
            ),
            workspace: str = typer.Option("default", "--workspace", help="Workspace used for fileset references."),
            output_dir: Path = typer.Option(
                Path("nss-output"), "--output-dir", help="Directory for local result files."
            ),
            data_source: Path | None = typer.Option(
                None,
                "--data-source",
                exists=True,
                readable=True,
                help="Optional local data file overriding spec.data_source fileset download.",
            ),
        ) -> None:
            """Run NSS on this host, using the managed local CUDA/GPU runtime."""
            args = [
                "run-local",
                "--spec-file",
                str(spec_file),
                "--workspace",
                workspace,
                "--output-dir",
                str(output_dir),
            ]
            if data_source is not None:
                args.extend(["--data-source", str(data_source)])

            try:
                command = runtime_task_command(config, args)
            except RuntimeError as e:
                typer.echo(str(e), err=True)
                raise typer.Exit(1) from e

            result = subprocess.run(command, check=False)
            if result.returncode != 0:
                raise typer.Exit(result.returncode)
            typer.echo(f"Wrote Safe Synthesizer results to {output_dir}")

        app.add_typer(runtime_app, name="runtime")
        return app
