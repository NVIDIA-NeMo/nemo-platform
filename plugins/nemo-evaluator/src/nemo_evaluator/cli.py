# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI surface for the evaluator plugin scaffold."""

from __future__ import annotations

import json
from typing import Annotated, ClassVar

import typer
from nemo_evaluator.shared.metric_bundles.container_image import (
    build_metric_server_image,
    default_metric_server_python_version,
    metric_server_image_build_plan,
)
from nemo_platform_plugin.cli import NemoCLI


class EvaluatorPluginCLI(NemoCLI):
    """CLI surface for the evaluator plugin scaffold."""

    name: ClassVar[str] = "evaluator"
    description: ClassVar[str] = "Evaluator plugin commands."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(
            name=self.name,
            help=self.description,
            no_args_is_help=True,
        )

        @app.command("info")
        def info() -> None:
            """Print the current plugin status."""
            typer.echo(
                json.dumps(
                    {
                        "plugin": self.name,
                        "status": "ready",
                        "service": "/apis/evaluator/v1/healthz",
                        "jobs": ["evaluator.evaluate"],
                        "sdk": "nemo_evaluator_sdk.Evaluator",
                    },
                    indent=2,
                )
            )

        images_app = typer.Typer(
            name="images",
            help="Build evaluator plugin container images.",
            no_args_is_help=True,
        )

        @images_app.command("build-metric-server")
        def build_metric_server(
            image: Annotated[
                str | None,
                typer.Option("--image", help="Fully qualified image tag to build."),
            ] = None,
            python_version: Annotated[
                str,
                typer.Option("--python-version", help="Python major.minor version for the base image."),
            ] = default_metric_server_python_version(),
            python_base_image: Annotated[
                str | None,
                typer.Option(
                    "--python-base-image",
                    help="Python runtime image to use, e.g. python:3.12-slim, python:3.12-alpine, or a DHI tag.",
                ),
            ] = None,
            dry_run: Annotated[
                bool,
                typer.Option("--dry-run", help="Print the resolved build plan without running Docker."),
            ] = False,
        ) -> None:
            """Build the metric-server base image used by container metric bundles."""
            result = (
                metric_server_image_build_plan(
                    image=image,
                    python_version=python_version,
                    python_base_image=python_base_image,
                )
                if dry_run
                else build_metric_server_image(
                    image=image,
                    python_version=python_version,
                    python_base_image=python_base_image,
                )
            )
            typer.echo(result.model_dump_json(indent=2))

        app.add_typer(images_app)

        return app
