# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the uploaded-project zip-expansion guards (traversal/symlink/absolute/size)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from nemo_iron_swarm_plugin.filesets import extract_zip_safely


def _write_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def test_extract_zip_safely_extracts_normal_project(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "p.zip", {"pyproject.toml": "[project]\n", "pkg/workflow.yaml": "_type: x\n"})
    dest = extract_zip_safely(zip_path, tmp_path / "out")
    assert (dest / "pyproject.toml").exists()
    assert (dest / "pkg" / "workflow.yaml").read_text() == "_type: x\n"


def test_extract_zip_safely_rejects_traversal(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "p.zip", {"../escape.txt": "x"})
    with pytest.raises(ValueError, match="escapes the destination"):
        extract_zip_safely(zip_path, tmp_path / "out")


def test_extract_zip_safely_rejects_absolute_member(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "p.zip", {"/etc/passwd": "x"})
    with pytest.raises(ValueError, match="absolute path"):
        extract_zip_safely(zip_path, tmp_path / "out")


def test_extract_zip_safely_rejects_symlink(tmp_path: Path) -> None:
    zip_path = tmp_path / "p.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777) << 16  # S_IFLNK — a symlink entry
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(ValueError, match="symlink"):
        extract_zip_safely(zip_path, tmp_path / "out")


def test_extract_zip_safely_rejects_too_many_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nemo_iron_swarm_plugin.filesets._MAX_ENTRIES", 2)
    zip_path = _write_zip(tmp_path / "p.zip", {"a": "1", "b": "2", "c": "3"})
    with pytest.raises(ValueError, match="too many entries"):
        extract_zip_safely(zip_path, tmp_path / "out")


def test_extract_zip_safely_rejects_oversized_by_declared_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nemo_iron_swarm_plugin.filesets._MAX_UNCOMPRESSED_BYTES", 8)
    zip_path = _write_zip(tmp_path / "p.zip", {"big.txt": "x" * 64})
    with pytest.raises(ValueError, match="too large when uncompressed"):
        extract_zip_safely(zip_path, tmp_path / "out")


def test_a_zip_under_reporting_its_size_cannot_beat_the_cap(tmp_path: Path) -> None:
    """Why summing the declared `file_size` is sound: zipfile reads against that same figure.

    A member claiming to be smaller than its data is truncated at the declared length and fails its
    CRC, so lying to slip past the cap yields an error, not an oversized extraction.
    """
    zip_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", "x" * 8192)
    _under_report(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.infolist()[0].file_size == 1  # the archive now claims 1 byte

    with pytest.raises(zipfile.BadZipFile):
        extract_zip_safely(zip_path, tmp_path / "out")


def _under_report(zip_path: Path) -> None:
    """Patch every recorded uncompressed size in *zip_path* to 1 byte, leaving the data intact."""
    raw = bytearray(zip_path.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        start = 0
        while (found := raw.find(signature, start)) != -1:
            raw[found + offset : found + offset + 4] = (1).to_bytes(4, "little")
            start = found + 4
    zip_path.write_bytes(bytes(raw))
