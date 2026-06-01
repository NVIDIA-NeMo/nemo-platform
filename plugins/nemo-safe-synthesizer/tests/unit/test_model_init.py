# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nemo_safe_synthesizer_plugin.tasks.safe_synthesizer.model_init import _snapshot_target_path


def test_snapshot_target_path_allows_nested_files(tmp_path: Path):
    snapshot_path = tmp_path / "models--test" / "snapshots" / "abc123"

    target = _snapshot_target_path(snapshot_path, "subdir/config.json")

    assert target == snapshot_path.resolve() / "subdir" / "config.json"


@pytest.mark.parametrize("file_path", ["../config.json", "/tmp/config.json", "subdir/../../config.json", "", "."])
def test_snapshot_target_path_rejects_unsafe_paths(tmp_path: Path, file_path: str):
    snapshot_path = tmp_path / "models--test" / "snapshots" / "abc123"

    with pytest.raises(ValueError, match="Invalid file path"):
        _snapshot_target_path(snapshot_path, file_path)
