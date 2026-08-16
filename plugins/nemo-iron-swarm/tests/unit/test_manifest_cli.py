# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the `nemo iron-swarm manifest show|set` commands (stored defaults, not per-run overrides)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from nemo_iron_swarm_plugin.cli import _shared
from typer.testing import CliRunner


def _patch_cli(cli_main: Any, monkeypatch: pytest.MonkeyPatch, manifests: Any) -> Any:
    fake_sdk = SimpleNamespace(iron_swarm=SimpleNamespace(manifests=manifests))
    monkeypatch.setattr(_shared.checks, "require_preflight", lambda _c: None)
    monkeypatch.setattr(_shared, "make_sdk", lambda _u: fake_sdk)
    monkeypatch.setattr(_shared, "base_url", lambda: "http://localhost:8080")
    monkeypatch.setattr(
        _shared.IronSwarmConfig,
        "get",
        classmethod(lambda _cls: SimpleNamespace(default_workspace="default", operator_env_file=Path(".env"))),
    )
    return cli_main.IronSwarmCLI().get_cli()


def test_manifest_show_prints_the_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.cli import main as cli_main

    record = {"name": "finance", "rounds": 3, "attack_intensity": "thorough"}
    manifests = SimpleNamespace(get=lambda name, *, workspace: record)
    app = _patch_cli(cli_main, monkeypatch, manifests)

    result = CliRunner().invoke(app, ["manifest", "show", "finance"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output[result.output.index("{") :]) == record


def test_manifest_set_builds_patch_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the flags given are sent, so an unset field keeps its stored value."""
    from nemo_iron_swarm_plugin.cli import main as cli_main

    captured: dict[str, Any] = {}

    def _update(name: str, *, workspace: str, **body: Any) -> dict:
        captured["name"] = name
        captured["workspace"] = workspace
        captured["body"] = body
        return {"name": name}

    app = _patch_cli(cli_main, monkeypatch, SimpleNamespace(update=_update))
    result = CliRunner().invoke(
        app,
        [
            "manifest",
            "set",
            "finance",
            "--rounds",
            "3",
            "--defender",
            "guardrails",
            "--egress",
            "example.com",
            "--env",
            "FINANCE_BACKEND_URL=http://host.docker.internal:8086",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["name"] == "finance"
    assert captured["body"] == {
        "rounds": 3,
        "defenders": ["guardrails"],
        "egress": ["example.com"],
        "env": {"FINANCE_BACKEND_URL": "http://host.docker.internal:8086"},
    }
    assert "attack_intensity" not in captured["body"]
    assert "port" not in captured["body"]


def test_manifest_set_requires_a_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """A no-op PATCH would report success while changing nothing."""
    from nemo_iron_swarm_plugin.cli import main as cli_main

    def _update(*_args: Any, **_kwargs: Any) -> dict:  # pragma: no cover - must not run
        raise AssertionError("update should not be called with an empty body")

    app = _patch_cli(cli_main, monkeypatch, SimpleNamespace(update=_update))
    result = CliRunner().invoke(app, ["manifest", "set", "finance"])

    assert result.exit_code == 1
    assert "at least one field" in result.output


def test_manifest_set_rejects_unknown_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same validation as `run`: a typo must not be absorbed into a silent default."""
    from nemo_iron_swarm_plugin.cli import main as cli_main

    def _update(*_args: Any, **_kwargs: Any) -> dict:  # pragma: no cover - must not run
        raise AssertionError("update should not be called with an invalid value")

    app = _patch_cli(cli_main, monkeypatch, SimpleNamespace(update=_update))

    intensity = CliRunner().invoke(app, ["manifest", "set", "finance", "--attack-intensity", "heavy"])
    assert intensity.exit_code == 1
    assert "light, standard, thorough" in intensity.output

    defender = CliRunner().invoke(app, ["manifest", "set", "finance", "--defender", "bogus"])
    assert defender.exit_code == 1
    assert "bogus" in defender.output


def test_manifest_set_merges_models_over_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    """PATCH replaces `models` wholesale, so setting one group must not clear the others."""
    from nemo_iron_swarm_plugin.cli import main as cli_main

    stored = {
        "models": {
            "attack": {"model": "stored/atk", "base_url": "https://stored/v1"},
            "analysis": {"model": "stored/ana"},
        }
    }
    captured: dict[str, Any] = {}

    def _update(name: str, *, workspace: str, **body: Any) -> dict:
        captured["body"] = body
        return {"name": name}

    manifests = SimpleNamespace(get=lambda name, *, workspace: stored, update=_update)
    app = _patch_cli(cli_main, monkeypatch, manifests)
    result = CliRunner().invoke(app, ["manifest", "set", "finance", "--safety-model", "guard-1"])

    assert result.exit_code == 0, result.output
    assert captured["body"]["models"] == {
        "attack": {"model": "stored/atk", "base_url": "https://stored/v1"},  # untouched group survives
        "analysis": {"model": "stored/ana"},
        "safety": {"model": "guard-1"},
    }


def test_manifest_set_merges_within_a_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overriding a group's model keeps that group's other stored fields."""
    from nemo_iron_swarm_plugin.cli import main as cli_main

    stored = {"models": {"attack": {"model": "old", "base_url": "https://stored/v1"}}}
    captured: dict[str, Any] = {}

    manifests = SimpleNamespace(
        get=lambda name, *, workspace: stored,
        update=lambda name, *, workspace, **body: captured.update(body) or {"name": name},
    )
    app = _patch_cli(cli_main, monkeypatch, manifests)
    result = CliRunner().invoke(app, ["manifest", "set", "finance", "--attack-model", "new"])

    assert result.exit_code == 0, result.output
    assert captured["models"]["attack"] == {"model": "new", "base_url": "https://stored/v1"}


def test_manifest_set_without_model_flags_skips_the_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """No model flags means no merge, so the extra GET is not paid for."""
    from nemo_iron_swarm_plugin.cli import main as cli_main

    def _get(*_a: Any, **_k: Any) -> dict:  # pragma: no cover - must not run
        raise AssertionError("manifest should not be read when no model flag was passed")

    captured: dict[str, Any] = {}
    manifests = SimpleNamespace(
        get=_get, update=lambda name, *, workspace, **body: captured.update(body) or {"name": name}
    )
    app = _patch_cli(cli_main, monkeypatch, manifests)
    result = CliRunner().invoke(app, ["manifest", "set", "finance", "--rounds", "2"])

    assert result.exit_code == 0, result.output
    assert "models" not in captured


def test_cli_init_sends_model_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """`init` accepts the same model flags, so a target can be fully configured in one call."""
    from nemo_iron_swarm_plugin.cli import main as cli_main

    captured: dict[str, Any] = {}
    manifests = SimpleNamespace(
        create=lambda *, workspace, **body: captured.update(body) or {"name": body["name"]},
    )
    app = _patch_cli(cli_main, monkeypatch, manifests)
    result = CliRunner().invoke(
        app,
        ["init", "--agent", "react-agent", "--attack-model", "atk/m", "--safety-model", "guard-1"],
    )

    assert result.exit_code == 0, result.output
    assert captured["models"] == {"attack": {"model": "atk/m"}, "safety": {"model": "guard-1"}}


def test_cli_init_omits_models_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.cli import main as cli_main

    captured: dict[str, Any] = {}
    manifests = SimpleNamespace(
        create=lambda *, workspace, **body: captured.update(body) or {"name": body["name"]},
    )
    app = _patch_cli(cli_main, monkeypatch, manifests)
    result = CliRunner().invoke(app, ["init", "--agent", "react-agent"])

    assert result.exit_code == 0, result.output
    assert "models" not in captured
