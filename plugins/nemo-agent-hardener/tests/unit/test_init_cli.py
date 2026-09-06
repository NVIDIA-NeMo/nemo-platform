# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for `nemo agent-hardener init --project-dir`, focused on the BYO (custom image) launch mode."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from nemo_agent_hardener_plugin.cli import _shared, lifecycle


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "deploy").mkdir(parents=True)
    (project / "deploy" / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    return project


def _patch_cli(cli_main: Any, monkeypatch: pytest.MonkeyPatch, captured: list[list[str]], created: dict) -> Any:
    """Neutralize preflight/SDK/upload and capture both the init argv and the create body."""

    def fake_create(*, workspace: str, **body):
        created.update(body)
        return {"name": body["name"], "launch_mode": body.get("launch_mode"), "dockerfile": "deploy/Dockerfile"}

    fake_sdk = SimpleNamespace(agent_hardener=SimpleNamespace(manifests=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(_shared.checks, "require_preflight", lambda _c: None)
    monkeypatch.setattr(_shared, "make_sdk", lambda _u: fake_sdk)
    monkeypatch.setattr(_shared, "base_url", lambda: "http://localhost:8080")
    monkeypatch.setattr(
        _shared.AgentHardenerConfig,
        "get",
        classmethod(
            lambda _cls: SimpleNamespace(
                default_workspace="default",
                operator_env_file=Path(".env"),
                agent_hardener_bin=Path("/bin/agent-hardener"),
            )
        ),
    )
    monkeypatch.setattr(lifecycle, "upload_project_dir", lambda *_a, **_k: "default/proj-bundle")

    def fake_subprocess(cmd, _action, *, cwd=None, timeout=None, env=None):
        captured.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_text("agent:\n  name: lab\n  project_dir: .\n", encoding="utf-8")

    monkeypatch.setattr(lifecycle.provisioning, "run_subprocess", fake_subprocess)
    return cli_main.AgentHardenerCLI().get_cli()
