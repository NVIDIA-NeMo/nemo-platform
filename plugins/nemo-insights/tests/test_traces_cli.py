# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from pathlib import Path

import pytest
from nemo_insights_plugin import traces_cli
from nemo_insights_plugin.contracts.workflow_context import load_workflow_context
from typer.testing import CliRunner


def test_import_uses_profile_workspace_and_writes_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "optimizer.yaml").write_text(
        "agent: nemo-oo-airline\nworkspace: tau2-airline\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "state-v9.tar.zst"
    bundle.touch()
    manifest = {
        "kind": "testbed-export",
        "workspaces": ["old-workspace"],
        "min_start_time": "2026-07-10T12:00:00+00:00",
    }
    captured: dict[str, object] = {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NMP_BASE_URL", raising=False)
    monkeypatch.setattr(
        traces_cli,
        "_resolve_bundle",
        lambda source, cache_dir: (bundle, source),
    )
    monkeypatch.setattr(traces_cli, "_read_bundle_manifest", lambda path: manifest)
    monkeypatch.setattr(
        traces_cli,
        "_resolve_platform_root",
        lambda explicit, profile_dir: tmp_path,
    )
    monkeypatch.setattr(
        traces_cli,
        "_import_bundle",
        lambda path, **kwargs: (
            captured.update(kwargs)
            or {
                "old-workspace": {
                    "spans": {"ingested": 270, "skipped": 0},
                }
            }
        ),
    )
    monkeypatch.setattr(
        traces_cli.reingest,
        "manifest_since",
        lambda payload: datetime(2026, 7, 9, 12, tzinfo=UTC),
    )

    result = CliRunner().invoke(
        traces_cli.TracesCLI().get_cli(),
        ["import", "state-v9"],
    )

    assert result.exit_code == 0, result.output
    assert "Trace corpus ready: tau2-airline (270 spans ingested" in result.output
    assert captured["workspace"] == "tau2-airline"
    assert captured["base_url"] == "http://localhost:8080"
    context = load_workflow_context(tmp_path, agent="nemo-oo-airline")
    assert context is not None
    assert context.workspace == "tau2-airline"
    assert context.trace_source == "state-v9"
    assert context.trace_since == datetime(2026, 7, 9, 12, tzinfo=UTC)


def test_import_requires_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        traces_cli.TracesCLI().get_cli(),
        ["import", "state-v9"],
    )

    assert result.exit_code == 1
    assert "No optimizer.yaml found" in result.output
