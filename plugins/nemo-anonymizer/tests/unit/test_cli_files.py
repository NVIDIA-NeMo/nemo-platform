# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest
from anonymizer.config.anonymizer_config import AnonymizerConfig
from anonymizer.config.replace_strategies import Redact
from nemo_anonymizer_plugin.app.input import AnonymizerInputSpec
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest
from nemo_anonymizer_plugin.cli_files import (
    resolve_input_remote_path,
    resolve_local_input_path,
    stage_anonymizer_request_for_remote,
    validate_remote_file_path,
)


def test_resolve_local_input_path_rejects_missing_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.csv"

    with pytest.raises(ValueError, match="must point to an existing file"):
        resolve_local_input_path(str(missing_file))


def test_resolve_local_input_path_rejects_unsupported_suffix(tmp_path: Path) -> None:
    unsupported_file = tmp_path / "input.jsonl"
    unsupported_file.write_text('{"text":"Alice"}\n')

    with pytest.raises(ValueError, match=r"must be one of: \.csv, \.parquet"):
        resolve_local_input_path(str(unsupported_file))


def test_resolve_input_remote_path_rejects_unsupported_suffix(tmp_path: Path) -> None:
    local_input = tmp_path / "input.csv"
    local_input.write_text("text\nAlice\n")

    with pytest.raises(ValueError, match=r"--input-remote-path 'inputs/input.txt' must be one of: \.csv, \.parquet"):
        resolve_input_remote_path("inputs/input.txt", local_input)


def test_resolve_input_remote_path_accepts_supported_suffix(tmp_path: Path) -> None:
    local_input = tmp_path / "input.csv"
    local_input.write_text("text\nAlice\n")

    assert resolve_input_remote_path("inputs/input.parquet", local_input) == "inputs/input.parquet"


@pytest.mark.parametrize("remote_path", ["../input.csv", "inputs/../input.csv", "inputs/.."])
def test_validate_remote_file_path_rejects_parent_directory_segments(remote_path: str) -> None:
    with pytest.raises(ValueError, match="must not include parent-directory segments"):
        validate_remote_file_path(remote_path, option_name="--input-remote-path")


def test_stage_anonymizer_request_rewrites_valid_local_input(tmp_path: Path) -> None:
    local_input = tmp_path / "input.csv"
    local_input.write_text("text\nAlice\n")
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source=str(local_input)),
    )

    staged = stage_anonymizer_request_for_remote(
        request,
        platform_client=None,
        workspace="team-a",
        fileset="anonymizer-inputs",
        input_remote_path=None,
        upload=False,
    )

    assert staged.source_was_local is True
    assert staged.request.data.source == "team-a/anonymizer-inputs#input.csv"
