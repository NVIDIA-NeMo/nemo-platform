# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the plugin's ``fileset`` workspace-seed handler (registered on import)."""

from __future__ import annotations

from pathlib import Path

import pytest
from nemo_evaluator import agent_seeds
from nemo_evaluator.agent_seeds import FilesetSeed
from nemo_evaluator_sdk.agent_eval.workspace_seeds import WorkspaceSeedError, parse_seed, seed_workspace
from pydantic import ValidationError


def test_fileset_ref_shape_is_validated() -> None:
    assert FilesetSeed(ref="ws/name").ref == "ws/name"
    assert FilesetSeed(ref="ws/name#data.csv").ref == "ws/name#data.csv"
    for bad in ("bad", "a/b/c", "/leading"):
        with pytest.raises(ValidationError):
            FilesetSeed(ref=bad)


def test_importing_plugin_registers_fileset_kind() -> None:
    # Importing nemo_evaluator.agent_seeds is enough to teach the SDK registry the 'fileset' kind;
    # the SDK itself has no awareness of it.
    assert isinstance(parse_seed({"kind": "fileset", "ref": "ws/name"}), FilesetSeed)


def test_fileset_seed_resolves_single_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(sdk: object, ref: object, dest: str) -> Path:
        target = Path(dest) / "data.csv"
        target.write_bytes(b"col\n1\n")
        return target

    monkeypatch.setattr(agent_seeds, "get_task_sdk", lambda service: object())
    monkeypatch.setattr(agent_seeds, "download_dataset_sync", fake_download)

    seed_workspace(tmp_path, {"seed/data.csv": {"kind": "fileset", "ref": "ws/name#data.csv"}})
    assert (tmp_path / "seed" / "data.csv").read_bytes() == b"col\n1\n"


def test_fileset_seed_rejects_multi_file_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(sdk: object, ref: object, dest: str) -> Path:
        root = Path(dest)
        (root / "a.txt").write_text("a")
        (root / "b.txt").write_text("b")
        return root

    monkeypatch.setattr(agent_seeds, "get_task_sdk", lambda service: object())
    monkeypatch.setattr(agent_seeds, "download_dataset_sync", fake_download)

    with pytest.raises(WorkspaceSeedError, match="resolved to 2 files"):
        seed_workspace(tmp_path, {"x": {"kind": "fileset", "ref": "ws/name"}})
