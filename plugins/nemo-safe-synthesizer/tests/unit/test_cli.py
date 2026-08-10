# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_safe_synthesizer_plugin.cli import SafeSynthesizerCLI
from typer.testing import CliRunner


def test_cli_exposes_runtime_but_not_removed_local_command() -> None:
    result = CliRunner().invoke(SafeSynthesizerCLI().get_cli(), ["--help"])

    assert result.exit_code == 0
    assert "runtime" in result.output
    assert "run-" + "local" not in result.output
