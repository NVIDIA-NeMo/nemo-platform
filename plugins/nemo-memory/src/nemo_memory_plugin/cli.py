# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Memory CLI — ``nemo memory`` command group.

Registered under the ``nemo.cli`` entry-point group. The platform
discovers this class and mounts it as ``nemo memory <command>``.

The ``triage / eval / export`` commands are auto-generated from the
``TriageJob`` / ``EvalJob`` / ``ExportJob`` NemoJobs registered under
the ``nemo.jobs`` entry-point group: the platform injects them into
this CLI group at startup, exposing ``run / submit / explain`` verbs
for each.

This module currently carries no hand-written commands. It exists so
the auto-injection has a top-level group to attach to. As the plugin
grows (Intake annotations, Studio review surface, future ad-hoc memory
maintenance commands) this is where hand-written verbs would land.
"""

from __future__ import annotations

from typing import ClassVar

import typer
from nemo_platform_plugin.cli import NemoCLI


class MemoryCLI(NemoCLI):
    """CLI commands for the Memory plugin."""

    name: ClassVar[str] = "memory"
    description: ClassVar[str] = (
        "Durable-memory triage, evaluation, and fine-tune-corpus extraction for agent memory stores."
    )

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(
            name="memory",
            help=self.description,
            no_args_is_help=False,
        )

        @app.callback(invoke_without_command=True)
        def memory_callback(ctx: typer.Context) -> None:
            if ctx.invoked_subcommand is None:
                typer.echo(ctx.get_help())
                raise typer.Exit(0)

        return app
