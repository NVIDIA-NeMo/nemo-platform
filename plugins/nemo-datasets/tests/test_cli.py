# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for the ``nemo datasets`` CLI surface."""

import json

import pyarrow as pa
import pyarrow.parquet as pq
import typer
from nemo_datasets_plugin.cli import DatasetsCLI
from typer.testing import CliRunner

runner = CliRunner()


def _mounted() -> typer.Typer:
    """The app as the platform mounts it: ``nemo datasets <command>``."""
    root = typer.Typer()
    root.add_typer(DatasetsCLI().get_cli(), name="datasets")
    return root


def test_cli_metadata():
    cli = DatasetsCLI()
    assert cli.name == "datasets"
    assert cli.description


def test_profile_command_registered():
    app = DatasetsCLI().get_cli()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "profile" in result.stdout


def test_profile_command_profiles_a_directory(tmp_path):
    pq.write_table(
        pa.Table.from_pylist([{"prompt": "a"}, {"prompt": "b"}]),
        tmp_path / "train-00000-of-00001.parquet",
    )
    result = runner.invoke(_mounted(), ["datasets", "profile", str(tmp_path)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["partitions"][0]["features"][0]["name"] == "prompt"
    assert payload["sampling"]["rows_scanned"] == 2


def test_profile_command_rejects_unknown_output_format(tmp_path):
    result = runner.invoke(_mounted(), ["datasets", "profile", str(tmp_path), "--output", "xml"])
    assert result.exit_code != 0


def test_profile_command_rejects_non_directory(tmp_path):
    target = tmp_path / "not-a-dir"
    target.write_text("x")
    result = runner.invoke(_mounted(), ["datasets", "profile", str(target)])
    assert result.exit_code != 0


def test_profile_command_accepts_column_role_hints(tmp_path):
    # The hint mechanism needs a caller on this branch; reading them from fileset metadata is the
    # platform half and lands with the Files integration.
    pq.write_table(pa.Table.from_pylist([{"q": "why?", "a": "because"}]), tmp_path / "train.parquet")
    result = runner.invoke(
        _mounted(), ["datasets", "profile", str(tmp_path), "--column-role", "q=prompt", "--column-role", "a=completion"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    partition = payload["partitions"][0]
    assert partition["classification"]["dataset_type"] == "prompt_completion"
    assert [f["semantic_role_source"] for f in partition["features"]] == ["declared", "declared"]


def test_profile_command_rejects_a_malformed_column_role(tmp_path):
    result = runner.invoke(_mounted(), ["datasets", "profile", str(tmp_path), "--column-role", "no-equals-sign"])
    assert result.exit_code != 0
