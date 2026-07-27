# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the three-phase CLI: manifest persistence, native synth-benign wiring, run --manifest-id."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from _doubles import make_job_context, make_sdk
from nemo_platform_plugin.job_context import JobContext
from typer.testing import CliRunner

_HEADER = "tool,payload,label,rationale,persona\n"


def _ctx(tmp_path: Path, workspace: str = "ws1") -> JobContext:
    return make_job_context(tmp_path, workspace=workspace, job_id="job-1")


# ── IronSwarmManifest.from_agent_resolution ──────────────────────────────────


def test_from_agent_resolution_builds_agent_source_entity() -> None:
    from nemo_iron_swarm_plugin.entities import IronSwarmManifest

    manifest = IronSwarmManifest.from_agent_resolution(
        name="my-target",
        workspace="ws1",
        agent_ref="ws1/chatbot",
        manifest_yaml="agent: {}\n",
        port=8000,
        secrets=["OPENAI_API_KEY"],
        warnings=["heads up"],
    )

    assert manifest.name == "my-target"
    assert manifest.source_type == "agent"
    assert manifest.agent == "ws1/chatbot"
    assert manifest.port == 8000
    assert manifest.secrets == ["OPENAI_API_KEY"]
    # _get_data_fields carries only domain fields (what the CLI persists via sdk.entities.create).
    assert "benign_suite" in manifest._get_data_fields()
    assert "name" not in manifest._get_data_fields()


# ── records.read_and_persist_suite ───────────────────────────────────────────


def test_read_and_persist_suite_persists_when_manifest_and_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nemo_iron_swarm_plugin.jobs import records

    csv = tmp_path / "requests.csv"
    csv.write_text(_HEADER + "search,hello,benign,r,pe\n", encoding="utf-8")
    calls: dict[str, Any] = {}
    monkeypatch.setattr(
        records,
        "_persist_benign_suite",
        lambda sdk, *, workspace, manifest_id, suite, interview=None: calls.update(
            ws=workspace, mid=manifest_id, suite=suite, interview=interview
        ),
    )

    out = records.read_and_persist_suite(object(), _ctx(tmp_path), "m1", csv, interview=[{"q": "a"}])

    assert len(out) == 1
    assert calls == {"ws": "ws1", "mid": "m1", "suite": out, "interview": [{"q": "a"}]}


def test_read_and_persist_suite_skips_persist_without_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.jobs import records

    csv = tmp_path / "requests.csv"
    csv.write_text(_HEADER + "search,hello,benign,r,pe\n", encoding="utf-8")
    calls: list[Any] = []
    monkeypatch.setattr(records, "_persist_benign_suite", lambda *a, **k: calls.append(1))

    out = records.read_and_persist_suite(object(), _ctx(tmp_path), None, csv)

    assert len(out) == 1
    assert calls == []  # no manifest_id → nothing cached


def test_read_and_persist_suite_skips_persist_for_empty_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.jobs import records

    csv = tmp_path / "requests.csv"
    csv.write_text(_HEADER, encoding="utf-8")  # header only → no rows
    calls: list[Any] = []
    monkeypatch.setattr(records, "_persist_benign_suite", lambda *a, **k: calls.append(1))

    out = records.read_and_persist_suite(object(), _ctx(tmp_path), "m1", csv)

    assert out == []
    assert calls == []


# ── execution.run_synth_benign ───────────────────────────────────────────────


def _write_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "iron-swarm.yaml"
    manifest.write_text("agent:\n  name: a\n", encoding="utf-8")
    return manifest


def _fake_run_iron_swarm_success(tmp_path: Path):
    """A _run_iron_swarm stand-in that simulates synth-benign writing requests.csv under the pinned root."""

    def _fake(cmd: list[str], env: dict, log_path: Path, ctx: Any, *, artifact_name: str):
        target = tmp_path / "synth-storage" / "benign_profiles" / "target-x"
        target.mkdir(parents=True, exist_ok=True)
        (target / "requests.csv").write_text(_HEADER + "search,hi,benign,r,pe\n", encoding="utf-8")
        return SimpleNamespace(returncode=0), "", None, None

    return _fake


@pytest.mark.parametrize(
    ("interview", "expected_flag", "unexpected_flag"),
    [("interactive", None, "--yes"), ("auto", "--yes", "--no-interactive"), ("skip", "--no-interactive", "--yes")],
)
def test_run_synth_benign_maps_interview_to_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interview: str, expected_flag: str | None, unexpected_flag: str
) -> None:
    from nemo_iron_swarm_plugin.jobs import execution

    manifest = _write_manifest(tmp_path)
    captured: dict[str, Any] = {}

    def _capture(cmd: list[str], env: dict, log_path: Path, ctx: Any, *, artifact_name: str):
        captured["cmd"] = cmd
        return _fake_run_iron_swarm_success(tmp_path)(cmd, env, log_path, ctx, artifact_name=artifact_name)

    monkeypatch.setattr(execution, "_run_iron_swarm", _capture)

    csv_path = execution.run_synth_benign(
        "iron-swarm-bin", str(manifest), None, {}, _ctx(tmp_path), interview=interview
    )

    assert csv_path.name == "requests.csv"
    assert csv_path.exists()
    assert captured["cmd"][:4] == ["iron-swarm-bin", "synth-benign", "--config", str(manifest)]
    if expected_flag:
        assert expected_flag in captured["cmd"]
    assert unexpected_flag not in captured["cmd"]
    # storage root is pinned into the manifest (under overrides, the only place iron-swarm's
    # AgentManifest accepts it) so the output CSV is at a known path.
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert data["overrides"]["storage"]["root_dir"].endswith("synth-storage")


def test_run_synth_benign_passes_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.jobs import execution

    manifest = _write_manifest(tmp_path)
    captured: dict[str, Any] = {}

    def _capture(cmd: list[str], *a: Any, **k: Any):
        captured["cmd"] = cmd
        return _fake_run_iron_swarm_success(tmp_path)(cmd, *a, **k)

    monkeypatch.setattr(execution, "_run_iron_swarm", _capture)
    execution.run_synth_benign("bin", str(manifest), "/tmp/.env", {}, _ctx(tmp_path))

    assert "--env-file" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--env-file") + 1] == "/tmp/.env"


def test_run_synth_benign_raises_on_subprocess_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.jobs import execution
    from nemo_iron_swarm_plugin.jobs.errors import IronSwarmRunError

    manifest = _write_manifest(tmp_path)
    failure = SimpleNamespace(category="sandbox", message="boom", remediation="retry")
    monkeypatch.setattr(
        execution, "_run_iron_swarm", lambda *a, **k: (SimpleNamespace(returncode=1), "log", None, failure)
    )

    with pytest.raises(IronSwarmRunError) as exc:
        execution.run_synth_benign("bin", str(manifest), None, {}, _ctx(tmp_path))
    assert exc.value.category == "sandbox"


def test_run_synth_benign_raises_when_no_csv_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.jobs import execution
    from nemo_iron_swarm_plugin.jobs.errors import IronSwarmRunError

    manifest = _write_manifest(tmp_path)
    # Success exit but the run produced no requests.csv under the pinned root.
    monkeypatch.setattr(execution, "_run_iron_swarm", lambda *a, **k: (SimpleNamespace(returncode=0), "", None, None))

    with pytest.raises(IronSwarmRunError):
        execution.run_synth_benign("bin", str(manifest), None, {}, _ctx(tmp_path))


# ── IronSwarmSynthBenignJob._execute ─────────────────────────────────────────


def test_synth_benign_job_execute_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.jobs import synth_benign as job_mod

    manifest = _write_manifest(tmp_path)
    monkeypatch.setattr(job_mod._common, "require_provisioned", lambda _c: None)
    monkeypatch.setattr(job_mod._common, "build_subprocess_env", lambda _c: {})
    monkeypatch.setattr(job_mod._common, "materialize_victim_env_file", lambda *a, **k: None)
    monkeypatch.setattr(job_mod._common, "check_victim_secrets", lambda *a, **k: None)
    monkeypatch.setattr(job_mod, "_materialize_manifest", lambda sdk, mid, ctx: str(manifest))
    monkeypatch.setattr(job_mod.IronSwarmConfig, "get", classmethod(lambda _cls: SimpleNamespace(iron_swarm_bin="bin")))
    seen: dict[str, Any] = {}

    def _fake_run_synth(bin_path, mani, env_file, env, ctx, *, interview):
        seen["interview"] = interview
        return tmp_path / "requests.csv"

    monkeypatch.setattr(job_mod, "run_synth_benign", _fake_run_synth)
    monkeypatch.setattr(job_mod, "read_and_persist_suite", lambda sdk, ctx, mid, csv: [{"tool": "t"}, {"tool": "u"}])

    job = job_mod.IronSwarmSynthBenignJob()
    monkeypatch.setattr(job, "report_progress", lambda *a, **k: None)
    out = job.run({"manifest_id": "m1", "interview": "auto"}, ctx=_ctx(tmp_path), sdk=object())

    assert out == {"status": "completed", "returncode": 0, "manifest_id": "m1", "suite_size": 2}
    assert seen["interview"] == "auto"


def test_synth_benign_job_classifies_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.jobs import synth_benign as job_mod
    from nemo_iron_swarm_plugin.jobs.errors import IronSwarmRunError

    monkeypatch.setattr(job_mod._common, "require_provisioned", lambda _c: None)
    monkeypatch.setattr(job_mod.IronSwarmConfig, "get", classmethod(lambda _cls: SimpleNamespace(iron_swarm_bin="bin")))

    def _boom(sdk, mid, ctx):
        raise IronSwarmRunError("manifest", "no such manifest")

    monkeypatch.setattr(job_mod, "_materialize_manifest", _boom)

    job = job_mod.IronSwarmSynthBenignJob()
    out = job.run({"manifest_id": "missing"}, ctx=_ctx(tmp_path), sdk=object())

    assert out["status"] == "failed"
    assert out["error"]["category"] == "manifest"


def test_synth_benign_job_service_driver_runs_serve_and_finalizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """driver=service drives _run_service_driven(stop_after_synth=True) and finalizes the run record."""
    from nemo_iron_swarm_plugin.jobs import synth_benign as job_mod
    from nemo_iron_swarm_plugin.jobs.execution import RunOutcome

    manifest = _write_manifest(tmp_path)
    monkeypatch.setattr(job_mod._common, "require_provisioned", lambda _c: None)
    monkeypatch.setattr(job_mod._common, "build_subprocess_env", lambda _c: {})
    monkeypatch.setattr(job_mod._common, "materialize_victim_env_file", lambda *a, **k: None)
    monkeypatch.setattr(job_mod._common, "check_victim_secrets", lambda *a, **k: None)
    monkeypatch.setattr(job_mod._common, "build_model_env", lambda *a, **k: {})
    monkeypatch.setattr(job_mod, "_materialize_manifest", lambda sdk, mid, ctx: str(manifest))
    monkeypatch.setattr(job_mod, "_effective_models", lambda sdk, config, ctx: None)
    monkeypatch.setattr(job_mod, "_manifest_facts", lambda mani: ("agent-x", 8000))
    monkeypatch.setattr(job_mod, "_save_events_fileset", lambda *a, **k: "")
    monkeypatch.setattr(job_mod.IronSwarmConfig, "get", classmethod(lambda _cls: SimpleNamespace(iron_swarm_bin="bin")))

    seen: dict[str, Any] = {}

    def _fake_service(mani, env_file, plugin_config, ctx, sdk, agent, port, **kw):
        seen.update(
            agent=agent, port=port, stop_after_synth=kw.get("stop_after_synth"), manifest_id=kw.get("manifest_id")
        )
        return RunOutcome("completed", 0, record_name="run-42")

    updated: dict[str, Any] = {}
    monkeypatch.setattr(job_mod, "_run_service_driven", _fake_service)
    monkeypatch.setattr(
        job_mod, "_update_run", lambda sdk, *, workspace, name, data: updated.update(name=name, data=data)
    )
    monkeypatch.setattr(job_mod, "_create_run", lambda *a, **k: pytest.fail("service path should update, not create"))

    job = job_mod.IronSwarmSynthBenignJob()
    monkeypatch.setattr(job, "report_progress", lambda *a, **k: None)
    out = job.run({"manifest_id": "m1", "driver": "service"}, ctx=_ctx(tmp_path), sdk=object())

    assert out == {"status": "completed", "returncode": 0, "manifest_id": "m1", "run_record": "run-42"}
    assert seen == {"agent": "agent-x", "port": 8000, "stop_after_synth": True, "manifest_id": "m1"}
    assert updated["name"] == "run-42"  # the running record is finalized to completed


def test_synth_benign_job_compile_builds_synth_task_step(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from nemo_iron_swarm_plugin.jobs import synth_benign as job_mod

    spec = job_mod.SynthBenignSpec(manifest_id="m1", driver="service")
    platform_spec = asyncio.run(
        job_mod.IronSwarmSynthBenignJob.compile(
            workspace="ws1", spec=spec, entity_client=object(), job_name="job-1", async_sdk=object()
        )
    )

    step = list(platform_spec["steps"])[0]  # PlatformJobSpec is a TypedDict; steps is an Iterable
    # Assert the provider first: it narrows the executor union to the subprocess variant.
    assert step["executor"]["provider"] == "subprocess"
    assert step["executor"]["command"] == ["python", "-m", "nemo_iron_swarm_plugin.tasks.synth_benign"]
    assert step["config"]["manifest_id"] == "m1"
    assert step["config"]["driver"] == "service"


# ── SDK routing ──────────────────────────────────────────────────────────────


class _CaptureScheduler:
    captured: dict[str, Any] = {}

    def run_local(self, job: Any, spec: dict, **kwargs: Any) -> dict:
        _CaptureScheduler.captured = {"job": job, "spec": spec, "kwargs": kwargs}
        return {"status": "completed", "suite_size": 3}


def test_sdk_synth_benign_routes_to_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin import sdk as sdk_module

    monkeypatch.setattr(sdk_module, "NemoJobScheduler", _CaptureScheduler)
    platform = make_sdk()
    resource = sdk_module.IronSwarmPluginResource(platform)

    resource.synth_benign(manifest_id="m1", interview="auto", workspace="ws1")

    cap = _CaptureScheduler.captured
    assert cap["job"] is sdk_module.IronSwarmSynthBenignJob
    assert cap["spec"] == {"manifest_id": "m1", "env_file": None, "interview": "auto"}
    assert cap["kwargs"]["workspace"] == "ws1"
    assert cap["kwargs"]["sdk"] is platform


def test_sdk_run_puts_manifest_id_in_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin import sdk as sdk_module

    monkeypatch.setattr(sdk_module, "NemoJobScheduler", _CaptureScheduler)
    resource = sdk_module.IronSwarmPluginResource(make_sdk())

    resource.run(manifest_id="m1", workspace="ws1")

    cap = _CaptureScheduler.captured
    assert cap["spec"]["manifest_id"] == "m1"
    assert cap["spec"]["config"] is None


def test_run_war_game_requires_config_or_manifest_id() -> None:
    from nemo_iron_swarm_plugin import sdk as sdk_module

    with pytest.raises(ValueError, match="config.*manifest_id"):
        sdk_module._run_war_game(
            SimpleNamespace(), config=None, manifest_id=None, env_file=None, workspace="d", benign_suite=None
        )


# ── CLI wiring ───────────────────────────────────────────────────────────────


def _patch_cli(monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]) -> Any:
    from nemo_iron_swarm_plugin.cli import main as cli_main

    fake_iron = SimpleNamespace(
        run=lambda **kw: captured.update(run=kw) or {"status": "completed"},
        synth_benign=lambda **kw: captured.update(synth=kw) or {"status": "completed", "suite_size": 4},
    )
    monkeypatch.setattr(cli_main.checks, "require_preflight", lambda _c: None)
    monkeypatch.setattr(cli_main, "make_sdk", lambda _u: SimpleNamespace(iron_swarm=fake_iron))
    monkeypatch.setattr(cli_main, "base_url", lambda: "http://localhost:8080")
    monkeypatch.setattr(cli_main, "missing_secrets", lambda _p, env_files: [])
    monkeypatch.setattr(
        cli_main.IronSwarmConfig,
        "get",
        classmethod(lambda _cls: SimpleNamespace(default_workspace="default", operator_env_file=Path(".env"))),
    )
    return cli_main.IronSwarmCLI().get_cli()


def test_cli_synth_benign_defaults_to_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    app = _patch_cli(monkeypatch, captured)

    result = CliRunner().invoke(app, ["synth-benign", "--manifest-id", "m1"])

    assert result.exit_code == 0, result.output
    assert captured["synth"] == {
        "manifest_id": "m1",
        "env_file": None,
        "interview": "interactive",
        "workspace": "default",
    }


@pytest.mark.parametrize(("flag", "mode"), [("--yes", "auto"), ("--no-interactive", "skip")])
def test_cli_synth_benign_maps_flags(monkeypatch: pytest.MonkeyPatch, flag: str, mode: str) -> None:
    captured: dict[str, Any] = {}
    app = _patch_cli(monkeypatch, captured)

    result = CliRunner().invoke(app, ["synth-benign", "--manifest-id", "m1", flag])

    assert result.exit_code == 0, result.output
    assert captured["synth"]["interview"] == mode


def test_cli_synth_benign_rejects_conflicting_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    app = _patch_cli(monkeypatch, captured)

    result = CliRunner().invoke(app, ["synth-benign", "--manifest-id", "m1", "--yes", "--no-interactive"])

    assert result.exit_code == 1
    assert "synth" not in captured


def test_cli_run_forwards_manifest_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    app = _patch_cli(monkeypatch, captured)

    result = CliRunner().invoke(app, ["run", "--manifest-id", "m1"])

    assert result.exit_code == 0, result.output
    assert captured["run"]["manifest_id"] == "m1"
    assert captured["run"]["config"] is None


def test_cli_run_rejects_config_and_manifest_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    app = _patch_cli(monkeypatch, captured)
    config = tmp_path / "iron-swarm.yaml"
    config.write_text("agent: {}\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["run", "--config", str(config), "--manifest-id", "m1"])

    assert result.exit_code == 1
    assert "run" not in captured


def test_cli_init_persists_manifest_entity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.cli import main as cli_main

    resolved = SimpleNamespace(
        manifest={"agent": {"name": "chatbot"}},
        workflow_path="workflow.yaml",
        project_dir=str(tmp_path),
        workspace="default",
        agent_name="chatbot",
        port=8000,
        secrets=["OPENAI_API_KEY"],
        warnings=[],
    )
    created: dict[str, Any] = {}
    fake_entities = SimpleNamespace(
        create=lambda entity_type, *, workspace, data, name: created.update(
            entity_type=entity_type, workspace=workspace, data=data, name=name
        )
    )
    monkeypatch.setattr(cli_main.checks, "require_preflight", lambda _c: None)
    monkeypatch.setattr(cli_main, "make_sdk", lambda _u: SimpleNamespace(entities=fake_entities))
    monkeypatch.setattr(cli_main, "base_url", lambda: "http://localhost:8080")
    monkeypatch.setattr(cli_main, "resolve_agent_to_manifest", lambda *a, **k: resolved)
    monkeypatch.setattr(
        cli_main.IronSwarmConfig,
        "get",
        classmethod(lambda _cls: SimpleNamespace(default_workspace="default", operator_env_file=Path(".env"))),
    )

    app = cli_main.IronSwarmCLI().get_cli()
    result = CliRunner().invoke(
        app, ["init", "--agent", "chatbot", "--name", "my-target", "-o", str(tmp_path / "iron-swarm.yaml")]
    )

    assert result.exit_code == 0, result.output
    assert created["name"] == "my-target"
    assert created["entity_type"] == "iron_swarm_manifest"
    assert created["data"]["agent"] == "default/chatbot"
    assert (tmp_path / "iron-swarm.yaml").exists()  # local yaml still written
