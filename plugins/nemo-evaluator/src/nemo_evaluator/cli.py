# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI surface for the evaluator plugin scaffold."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import typer
from nemo_evaluator.metric_catalog import metric_type_entries, metric_type_models
from nemo_platform_plugin.cli import NemoCLI


def _echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2))


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
            _echo_json(
                {
                    "plugin": self.name,
                    "status": "ready",
                    "service": "/apis/evaluator/v1/healthz",
                    "jobs": ["evaluator.evaluate"],
                    "sdk": "nemo_evaluator_sdk.Evaluator",
                }
            )

        @app.command("metric-types")
        def metric_types(
            metric_types_name: str | None = typer.Argument(None, metavar="<metric-name>"),
        ) -> None:
            """Print available evaluator metric names or a metric JSON schema."""
            if metric_types_name is None:
                _echo_json({"metric_types": metric_type_entries()})
                return

            metric_types_map = metric_type_models()
            model_cls = metric_types_map.get(metric_types_name)
            if model_cls is None:
                typer.echo(
                    f"Unknown metric name '{metric_types_name}'. Run `nemo evaluator metric-types` to list available metric names.",
                    err=True,
                )
                raise typer.Exit(code=1)
            _echo_json(model_cls.model_json_schema())

        return app
