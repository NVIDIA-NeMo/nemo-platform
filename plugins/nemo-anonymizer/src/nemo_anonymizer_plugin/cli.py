# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Anonymizer plugin CLI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Optional, cast

import typer
import yaml
from anonymizer.config.anonymizer_config import AnonymizerConfig
from nemo_anonymizer_plugin.app.upstream_logging import preserve_root_logging
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.job import NemoJob


class AnonymizerCLI(NemoCLI):
    name: ClassVar[str] = "anonymizer"
    description: ClassVar[str] = "Anonymizer: detect and replace/rewrite PII in text data"

    def get_cli(self) -> typer.Typer:
        # ``preview`` and ``run`` are generated from the NemoFunction/NemoJob
        # entry points. Keep only explicit commands that are not generated.
        app = typer.Typer(name=self.name, help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            # Keep Typer in command-group mode even while ``validate`` is the
            # only manually registered command.
            pass

        app.command("validate")(validate_command)
        return app

    def update_job_cli(self, job_cls: type[NemoJob], group: typer.Typer) -> None:
        if job_cls.name != "run":
            return

        run_command = next((command for command in group.registered_commands if command.name == "run"), None)
        if run_command is None or run_command.callback is None:
            return

        run_callback = cast(Callable[..., None], run_command.callback)
        signature = getattr(run_callback, "__signature__", None)
        if signature is None:
            return

        def _collapsed_run(typer_ctx: typer.Context, **kwargs: object) -> None:
            if typer_ctx.invoked_subcommand is not None:
                return
            run_callback(typer_ctx, **kwargs)

        setattr(_collapsed_run, "__signature__", signature)
        group.callback(invoke_without_command=True)(_collapsed_run)


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
