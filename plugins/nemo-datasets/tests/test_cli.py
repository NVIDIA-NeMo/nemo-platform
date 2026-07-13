# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for the ``nemo datasets`` CLI surface."""

from nemo_datasets_plugin.cli import DatasetsCLI
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_metadata():
    cli = DatasetsCLI()
    assert cli.name == "datasets"
    assert cli.description


def test_profile_command_registered():
    app = DatasetsCLI().get_cli()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "profile" in result.stdout
