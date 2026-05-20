# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import nemo_data_designer_plugin.testing.utils as u
import pytest
import typer
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    return u.make_data_designer_cli_app()


def test_nemotron_personas_download_is_wired(runner: CliRunner, app: typer.Typer) -> None:
    result = runner.invoke(app, ["personas", "download", "--help"])

    assert result.exit_code == 0, result.output
    assert "Download Nemotron-Personas" in result.output
    assert "nemo data-designer personas download --list" in result.output
    assert "data-designer download personas" not in result.output


@pytest.mark.parametrize("verb", ["run", "submit"])
def test_preview_exposes_save_results_flags(runner: CliRunner, app: typer.Typer, verb: str) -> None:
    result = runner.invoke(app, ["preview", verb, "--help"])

    assert result.exit_code == 0, result.output
    assert "--save-results" in result.output
    assert "--artifact-path" in result.output
    assert "--non-interactive" in result.output
