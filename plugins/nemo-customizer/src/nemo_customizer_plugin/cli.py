# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customizer plugin CLI — exposed as ``nemo customizer ...``.

The main user surface (``nemo customizer finetune run ...``) is
auto-mounted by the platform from the ``customizer.finetune`` job's
entry point. This module adds a ``doctor`` helper that probes a venv
for backend health.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from nemo_platform_plugin.cli import NemoCLI


class CustomizerCLI(NemoCLI):
    """Local fine-tuning. See ``finetune run --help``."""

    name = "customizer"
    description = (
        "Local fine-tuning plugin. Backends: unsloth (implemented), "
        "automodel / megatron-bridge (stub — use services/customizer/ remotely)."
    )

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help="Local fine-tuning. See `finetune run --help`.")

        @app.command("doctor")
        def doctor(
            backend: str = typer.Option(
                "unsloth",
                "--backend",
                help="Backend to check (unsloth, automodel, megatron-bridge).",
            ),
            venv: Optional[Path] = typer.Option(
                None,
                "--venv",
                help=(
                    "Path to the venv to probe. Defaults to "
                    "`~/.nemo/customizer/<backend>/.venv` (the conventional location)."
                ),
            ),
        ) -> None:
            """Report whether the venv at *--venv* (or the default path) has the backend installed."""
            from nemo_customizer_plugin.venv_resolver import default_venv_path, probe_venv

            path = venv if venv is not None else default_venv_path(backend)
            ok, detail = probe_venv(path, backend)
            status = "OK" if ok else "MISSING/BROKEN"
            typer.echo(f"backend: {backend}")
            typer.echo(f"venv:    {path}")
            typer.echo(f"status:  {status}")
            typer.echo(f"detail:  {detail}")
            if not ok:
                raise typer.Exit(code=1)

        return app
