# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from importlib.metadata import PackageNotFoundError

from nmp.platform_runner.version import _resolve_version, get_revision


def test_resolve_version_uses_nemo_platform(monkeypatch):
    monkeypatch.setattr("nmp.platform_runner.version.version", lambda _: "1.2.3")
    assert _resolve_version() == "1.2.3"


def test_resolve_version_falls_back_to_env(monkeypatch):
    def _missing(_name: str) -> str:
        raise PackageNotFoundError("nemo-platform")

    monkeypatch.setattr("nmp.platform_runner.version.version", _missing)
    monkeypatch.setenv("NMP_PLATFORM_VERSION", "9.9.9")
    assert _resolve_version() == "9.9.9"


def test_resolve_version_defaults_to_dev(monkeypatch):
    def _missing(_name: str) -> str:
        raise PackageNotFoundError("nemo-platform")

    monkeypatch.setattr("nmp.platform_runner.version.version", _missing)
    monkeypatch.delenv("NMP_PLATFORM_VERSION", raising=False)
    assert _resolve_version() == "dev"


def test_get_revision(monkeypatch):
    monkeypatch.setenv("NMP_CODE_REVISION", "abc123")
    assert get_revision() == "abc123"
    monkeypatch.delenv("NMP_CODE_REVISION", raising=False)
    assert get_revision() == "dev"
