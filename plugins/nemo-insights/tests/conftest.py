# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for the insights tests."""

from collections.abc import Callable
from pathlib import Path

import pytest


def _config_yaml(base_url: str, workspace: str | None) -> str:
    workspace_line = f"    workspace: {workspace}\n" if workspace is not None else ""
    return (
        "current_context: test\n"
        "contexts:\n"
        f"  - name: test\n    cluster: test-cluster\n    user: test-user\n{workspace_line}"
        "clusters:\n"
        f"  - name: test-cluster\n    base_url: {base_url}\n"
        "users:\n"
        "  - name: test-user\n    type: oauth\n    token: test-token\n"
    )


@pytest.fixture(autouse=True)
def isolated_nmp_config(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve base URL and workspace against a context-free config by default.

    Both now fall back to the active ``nemo config`` context, so without this
    the developer's own ``~/.config/nmp/config.yaml`` would decide what every
    "no flag given" test sees — passing locally and failing in CI, or worse.
    """
    config = tmp_path_factory.mktemp("nmp-config") / "config.yaml"
    config.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config))
    monkeypatch.delenv("NMP_BASE_URL", raising=False)
    monkeypatch.delenv("NMP_WORKSPACE", raising=False)


@pytest.fixture
def use_nmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """Point NMP_CONFIG_FILE at a config with one populated context."""

    def use(*, base_url: str = "http://config.example", workspace: str | None = None) -> Path:
        config = tmp_path / "nmp-config.yaml"
        config.write_text(_config_yaml(base_url, workspace), encoding="utf-8")
        monkeypatch.setenv("NMP_CONFIG_FILE", str(config))
        return config

    return use
