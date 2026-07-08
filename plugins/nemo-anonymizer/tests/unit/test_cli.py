# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import yaml
from nemo_anonymizer_plugin import cli as cli_module
from nemo_anonymizer_plugin.cli import AnonymizerCLI
from nemo_platform_plugin.commands import add_job_commands
from nemo_platform_plugin.job import NemoJob
from typer.testing import CliRunner


class _RunJob(NemoJob):
    name: ClassVar[str] = "run"
    description: ClassVar[str] = "Run test job."

    def run(self, config: dict) -> dict:
        return {"config": config}


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "replace": {
                    "kind": "redact",
                    "format_template": "[REDACTED_{label}]",
                }
            }
        )
    )


def test_cli_only_registers_manual_validate_command() -> None:
    result = CliRunner().invoke(AnonymizerCLI().get_cli(), ["--help"])

    assert result.exit_code == 0, result.output
    assert "validate" in result.output
    assert "preview-local" not in result.output
    assert "run-local" not in result.output


def test_run_job_collapses_local_run_alias() -> None:
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _RunJob}, cli=cli)
    runner = CliRunner()

    alias_result = runner.invoke(app, ["run", "--config", '{"name": "Alias"}'])
    nested_result = runner.invoke(app, ["run", "run", "--config", '{"name": "Nested"}'])
    help_result = runner.invoke(app, ["run", "--help"])

    assert alias_result.exit_code == 0, alias_result.output
    assert json.loads(alias_result.output) == {"config": {"name": "Alias"}}
    assert nested_result.exit_code == 0, nested_result.output
    assert json.loads(nested_result.output) == {"config": {"name": "Nested"}}
    assert help_result.exit_code == 0, help_result.output
    assert "Run locally, in-process." in help_result.output
    assert "Run run locally" not in help_result.output


def test_validate_command_runs_library_validation(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAnonymizer:
        def validate_config(self, config: object) -> None:
            captured["config"] = config

    def fake_make_local_anonymizer(*, model_configs: str | Path | None, artifact_path: Path | None = None):
        captured["model_configs"] = model_configs
        captured["artifact_path"] = artifact_path
        return FakeAnonymizer()

    monkeypatch.setattr(cli_module, "_make_local_anonymizer", fake_make_local_anonymizer)

    config = tmp_path / "config.yaml"
    model_configs = tmp_path / "models.yaml"
    _write_config(config)
    model_configs.write_text("model_configs: []\n")

    result = CliRunner().invoke(
        AnonymizerCLI().get_cli(),
        [
            "validate",
            "--config",
            str(config),
            "--model-configs",
            str(model_configs),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["model_configs"] == str(model_configs)
    assert captured["artifact_path"] is None
    assert "Config is valid." in result.output
