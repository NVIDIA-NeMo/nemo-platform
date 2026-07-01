# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from subprocess import CompletedProcess

from nemo_safe_synthesizer_plugin import cli
from nemo_safe_synthesizer_plugin.cli import NEMO_DEPLOYMENT_TYPE_ENVVAR, NMP_DEPLOYMENT_TYPE, SafeSynthesizerCLI
from typer.testing import CliRunner


def test_run_local_sets_nmp_deployment_type_for_runtime_subprocess(tmp_path, monkeypatch):
    spec_file = tmp_path / "nss-job.json"
    spec_file.write_text("{}", encoding="utf-8")
    data_file = tmp_path / "input.csv"
    data_file.write_text("name\nAda\n", encoding="utf-8")
    output_dir = tmp_path / "nss-output"
    captured = {}

    def fake_runtime_task_command(_config, args):
        return ["runtime-python", *args]

    def fake_run(command, *, check=False, env=None):
        captured["command"] = command
        captured["check"] = check
        captured["env"] = env
        return CompletedProcess(command, 0)

    monkeypatch.setattr(cli, "runtime_task_command", fake_runtime_task_command)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = CliRunner().invoke(
        SafeSynthesizerCLI().get_cli(),
        [
            "run-local",
            "--workspace",
            "default",
            "--spec-file",
            str(spec_file),
            "--data-source",
            str(data_file),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["check"] is False
    assert captured["env"][NEMO_DEPLOYMENT_TYPE_ENVVAR] == NMP_DEPLOYMENT_TYPE
