# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hermetic tests for Fabric sandbox image provisioning (mock the docker subprocess boundary)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.fabric import image as image_mod
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.image import (
    FabricImageError,
    ensure_fabric_image,
    fabric_image_tag,
)


class _DockerRecorder:
    """Fake subprocess.run: records argv, returns canned codes by subcommand."""

    def __init__(self, *, image_present: bool) -> None:
        self.calls: list[list[str]] = []
        self._image_present = image_present

        self.build_context: dict[str, bool] = {}

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            code = 0 if self._image_present else 1
        else:  # docker build <ctx> — snapshot the staged context before it is torn down.
            ctx = Path(argv[-1])
            self.build_context = {
                "Dockerfile": (ctx / "Dockerfile").is_file(),
                "nemo-fabric": (ctx / "nemo-fabric").is_dir(),
            }
            code = 0
        return subprocess.CompletedProcess(argv, code, b"", b"")

    @property
    def build_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[1] == "build"]


def _fabric_repo(tmp_path: Path) -> Path:
    """A stub checkout with every build input _stage_source requires."""
    repo = tmp_path / "NeMo-Fabric"
    (repo / "crates").mkdir(parents=True)
    (repo / "python").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='nemo-fabric'\n", encoding="utf-8")
    for name in ("Cargo.toml", "Cargo.lock", "README.md"):
        (repo / name).write_text("x", encoding="utf-8")
    return repo


def test_tag_is_content_addressed_and_harness_agnostic() -> None:
    tag = fabric_image_tag()
    assert tag.startswith("localhost/nemo-evaluator/fabric-sandbox:")
    assert "hermes" not in tag  # one image serves any built-in harness — no harness in the tag
    assert fabric_image_tag() == tag  # deterministic


def test_ensure_skips_build_when_image_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = _DockerRecorder(image_present=True)
    monkeypatch.setattr(image_mod.subprocess, "run", recorder)
    tag = ensure_fabric_image(fabric_repo=_fabric_repo(tmp_path))
    assert tag == fabric_image_tag()
    assert recorder.build_calls == []  # inspected, found, no build


def test_ensure_builds_when_image_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = _DockerRecorder(image_present=False)
    monkeypatch.setattr(image_mod.subprocess, "run", recorder)
    tag = ensure_fabric_image(fabric_repo=_fabric_repo(tmp_path))
    (build,) = recorder.build_calls
    assert build[:2] == ["docker", "build"]
    assert ["--build-arg", "EXTRAS=hermes,relay"] == build[2:4]  # baked harness runtime deps
    assert build[4:6] == ["-t", tag]
    # The staged context had the Dockerfile + the copied fabric source.
    assert recorder.build_context == {"Dockerfile": True, "nemo-fabric": True}


def test_ensure_errors_when_fabric_source_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = _DockerRecorder(image_present=False)
    monkeypatch.setattr(image_mod.subprocess, "run", recorder)
    with pytest.raises(FabricImageError, match="NeMo-Fabric source not found"):
        ensure_fabric_image(fabric_repo=tmp_path / "does-not-exist")


def test_image_exists_raises_when_daemon_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    # A stopped daemon must surface as a clear error, not "image absent" (which would trigger a build
    # that also fails confusingly).
    def _daemon_down(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 1, b"", b"Cannot connect to the Docker daemon at unix:///...")

    monkeypatch.setattr(image_mod.subprocess, "run", _daemon_down)
    with pytest.raises(FabricImageError, match="cannot reach the Docker daemon"):
        image_mod.image_exists(fabric_image_tag())


def test_image_exists_false_when_image_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def _absent(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 1, b"", b"Error: No such image: foo")

    monkeypatch.setattr(image_mod.subprocess, "run", _absent)
    assert image_mod.image_exists(fabric_image_tag()) is False


def test_image_exists_raises_on_daemon_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # An unresponsive daemon must fail fast (bounded), not hang the runtime indefinitely.
    def _hang(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(image_mod.subprocess, "run", _hang)
    with pytest.raises(FabricImageError, match="timed out"):
        image_mod.image_exists(fabric_image_tag())
