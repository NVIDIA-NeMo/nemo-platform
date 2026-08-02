# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the IronSwarmManifest routes (list/get/delete + the `init` create path).

TestClient + dependency_overrides mock the entity client; the platform SDK and the (network-bound)
agent resolver are monkeypatched so `init` exercises the request/response flow without a live agent.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_iron_swarm_plugin.agent_resolver import ResolvedManifest
from nemo_iron_swarm_plugin.api.v2 import manifests as manifests_module
from nemo_iron_swarm_plugin.entities import IronSwarmManifest
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError, NemoPaginationInfo, get_entity_client

NOW = datetime.now(timezone.utc)
PREFIX = "/apis/iron-swarm/v2/workspaces/{workspace}"


def _resolved() -> ResolvedManifest:
    return ResolvedManifest(
        manifest={"agent": {"name": "clockbot", "port": 8000}, "backends": []},
        workflow_path=Path("/tmp/workflow.yaml"),
        project_dir=Path("/tmp/proj"),
        workspace="default",
        agent_name="clockbot",
        port=8000,
        secrets=["INFERENCE_API_KEY"],
        warnings=["no running deployment; defaulting port to 8000."],
    )


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_entity_client: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(manifests_module, "get_platform_sdk", lambda **_: MagicMock())
    monkeypatch.setattr(manifests_module, "resolve_agent_to_manifest", lambda *_a, **_k: _resolved())
    app = FastAPI()
    app.include_router(manifests_module.router, prefix=PREFIX)
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return TestClient(app, raise_server_exceptions=False)


def test_init_from_agent_creates_manifest(client, mock_entity_client) -> None:
    mock_entity_client.create = AsyncMock(side_effect=lambda entity: entity)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={"name": "clockbot-hardening", "source_type": "agent", "agent": "clockbot"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "clockbot-hardening"
    assert body["agent"] == "default/clockbot"
    assert body["port"] == 8000
    assert "clockbot" in body["manifest_yaml"]
    call = mock_entity_client.create.await_args
    assert call is not None
    created = call.args[0]
    assert isinstance(created, IronSwarmManifest)


def test_inspect_agent_returns_derived_defaults(client, monkeypatch) -> None:
    monkeypatch.setattr(
        manifests_module,
        "inspect_agent",
        lambda *_a, **_k: ("default/clockbot", 9123, ["INFERENCE_API_KEY"], ["heads up"]),
    )
    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests/inspect-agent",
        json={"agent": "clockbot"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "agent": "default/clockbot",
        "port": 9123,
        "secrets": ["INFERENCE_API_KEY"],
        "warnings": ["heads up"],
    }


def test_inspect_agent_reports_resolution_error(client, monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise manifests_module.AgentResolutionError("agent 'ghost' not found")

    monkeypatch.setattr(manifests_module, "inspect_agent", _boom)
    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests/inspect-agent",
        json={"agent": "ghost"},
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_init_agent_source_requires_agent(client) -> None:
    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={"name": "no-agent", "source_type": "agent"},
    )
    assert resp.status_code == 422


def test_init_project_source_requires_fileset(client) -> None:
    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={"name": "from-project", "source_type": "project"},
    )
    assert resp.status_code == 422
    assert "project_fileset" in resp.json()["detail"]


_INSPECT_JSON = (
    '{"project_dir": "myproject", "workflows": ["agents/research/workflow.yaml"], "dockerfiles": [], '
    '"suggested_launch_mode": "workflow", "default_agent_name": "research", "default_port": 8000, '
    '"secrets_file": ".env", "secret_names": ["INFERENCE_API_KEY"], "egress": ["inference-api.nvidia.com"]}'
)


def _stub_project_subprocess(
    monkeypatch: pytest.MonkeyPatch, *, returncode: int, stdout: str = "", stderr: str = ""
) -> None:
    """Stub the fileset download + iron-swarm subprocess for the project manifest paths."""
    monkeypatch.setattr(manifests_module, "download_and_extract_project", lambda *_a, **_k: Path("/tmp/proj"))
    monkeypatch.setattr(
        manifests_module.IronSwarmConfig,
        "get",
        classmethod(lambda cls: MagicMock(iron_swarm_bin=Path("/bin/iron-swarm"))),
    )

    def fake_run(cmd, **_kwargs):
        # `init` writes to the -o path; emulate it so _init can read the manifest back.
        if returncode == 0 and "-o" in cmd:
            out = Path(cmd[cmd.index("-o") + 1])
            out.write_text("agent:\n  name: research\n  project_dir: /tmp/proj\n  port: 8000\n", encoding="utf-8")
        return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(manifests_module.subprocess, "run", fake_run)


def test_inspect_project_returns_detection(client, monkeypatch) -> None:
    _stub_project_subprocess(monkeypatch, returncode=0, stdout=_INSPECT_JSON)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests/inspect",
        json={"project_fileset": "default/proj-bundle"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflows"] == ["agents/research/workflow.yaml"]
    assert body["default_agent_name"] == "research"
    assert body["secret_names"] == ["INFERENCE_API_KEY"]


def test_inspect_project_reports_subprocess_failure(client, monkeypatch) -> None:
    _stub_project_subprocess(monkeypatch, returncode=1, stderr="no workflow found")

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests/inspect",
        json={"project_fileset": "default/proj-bundle"},
    )

    assert resp.status_code == 400
    assert "no workflow found" in resp.json()["detail"]


def _stub_hanging_subprocess(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Make the iron-swarm subprocess time out, recording the timeout it was given."""
    monkeypatch.setattr(manifests_module, "download_and_extract_project", lambda *_a, **_k: Path("/tmp/proj"))
    monkeypatch.setattr(
        manifests_module.IronSwarmConfig,
        "get",
        classmethod(lambda cls: MagicMock(iron_swarm_bin=Path("/bin/iron-swarm"))),
    )
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout") or 0)

    monkeypatch.setattr(manifests_module.subprocess, "run", fake_run)
    return seen


def test_inspect_project_bounds_a_hanging_subprocess(client, monkeypatch) -> None:
    """Unbounded, a wedged `iron-swarm inspect` pins its threadpool worker for the process's life."""
    seen = _stub_hanging_subprocess(monkeypatch)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests/inspect",
        json={"project_fileset": "default/proj-bundle"},
    )

    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"]
    assert seen["timeout"] == manifests_module._SUBPROCESS_TIMEOUT_SECONDS


def test_create_project_manifest_bounds_a_hanging_subprocess(client, monkeypatch) -> None:
    seen = _stub_hanging_subprocess(monkeypatch)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={"name": "m1", "source_type": "project", "project_fileset": "default/proj-bundle"},
    )

    assert resp.status_code == 504
    assert seen["timeout"] == manifests_module._SUBPROCESS_TIMEOUT_SECONDS


def test_create_project_manifest(client, mock_entity_client, monkeypatch) -> None:
    _stub_project_subprocess(monkeypatch, returncode=0)
    mock_entity_client.create = AsyncMock(side_effect=lambda entity: entity)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={
            "name": "research-hardening",
            "source_type": "project",
            "project_fileset": "default/proj-bundle",
            "workflow": "agents/research/workflow.yaml",
            "secrets": ["INFERENCE_API_KEY"],
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_type"] == "project"
    assert body["project_fileset"] == "default/proj-bundle"
    assert body["workflow"] == "agents/research/workflow.yaml"
    # The persisted manifest can't hold the temp path; project_dir is normalized to '.'.
    assert "project_dir: ." in body["manifest_yaml"]


def test_create_project_manifest_forwards_egress(client, mock_entity_client, monkeypatch) -> None:
    monkeypatch.setattr(manifests_module, "download_and_extract_project", lambda *_a, **_k: Path("/tmp/proj"))
    monkeypatch.setattr(
        manifests_module.IronSwarmConfig,
        "get",
        classmethod(lambda cls: MagicMock(iron_swarm_bin=Path("/bin/iron-swarm"))),
    )
    captured: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        captured.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_text("agent:\n  name: research\n  project_dir: .\n", encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(manifests_module.subprocess, "run", fake_run)
    mock_entity_client.create = AsyncMock(side_effect=lambda entity: entity)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={
            "name": "research-hardening",
            "source_type": "project",
            "project_fileset": "default/proj-bundle",
            "workflow": "agents/research/workflow.yaml",
            "egress": ["host.docker.internal:8086", "inference-api.nvidia.com"],
        },
    )

    assert resp.status_code == 201, resp.text
    argv = captured[0]
    egress_flags = [argv[i + 1] for i, tok in enumerate(argv) if tok == "--egress"]
    assert egress_flags == ["host.docker.internal:8086", "inference-api.nvidia.com"]


def test_create_project_manifest_forwards_backends(client, mock_entity_client, monkeypatch) -> None:
    monkeypatch.setattr(manifests_module, "download_and_extract_project", lambda *_a, **_k: Path("/tmp/proj"))
    monkeypatch.setattr(
        manifests_module.IronSwarmConfig,
        "get",
        classmethod(lambda cls: MagicMock(iron_swarm_bin=Path("/bin/iron-swarm"))),
    )
    captured: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        captured.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_text("agent:\n  name: research\n  project_dir: .\n", encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(manifests_module.subprocess, "run", fake_run)
    mock_entity_client.create = AsyncMock(side_effect=lambda entity: entity)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={
            "name": "finance",
            "source_type": "project",
            "project_fileset": "default/proj-bundle",
            "workflow": "agents_lab/agents/finance/workflow.yaml",
            "backends": ["finance:8086", "cache:6379,6380"],
        },
    )

    assert resp.status_code == 201, resp.text
    argv = captured[0]
    backend_flags = [argv[i + 1] for i, tok in enumerate(argv) if tok == "--backend"]
    assert backend_flags == ["finance:8086", "cache:6379,6380"]


def test_delete_missing_manifest_returns_404(client, mock_entity_client) -> None:
    mock_entity_client.delete = AsyncMock(side_effect=NemoEntityNotFoundError("nope"))

    resp = client.delete("/apis/iron-swarm/v2/workspaces/default/manifests/ghost")

    assert resp.status_code == 404


def test_patch_updates_benign_suite_and_port(client, mock_entity_client) -> None:
    existing = IronSwarmManifest(name="m1", workspace="default", agent="default/clockbot", port=8000)
    mock_entity_client.get = AsyncMock(return_value=existing)
    mock_entity_client.update = AsyncMock(side_effect=lambda entity: entity)

    resp = client.patch(
        "/apis/iron-swarm/v2/workspaces/default/manifests/m1",
        json={"benign_suite": [{"tool": "clock", "payload": "what time", "label": "benign"}], "port": 9000},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["port"] == 9000
    assert body["benign_suite"][0]["tool"] == "clock"
    call = mock_entity_client.update.await_args
    assert call is not None
    updated = call.args[0]
    assert updated.port == 9000
    assert updated.benign_suite[0]["payload"] == "what time"


def test_patch_updates_egress(client, mock_entity_client) -> None:
    """Egress is a persisted setting now, so it has to be editable after creation."""
    existing = IronSwarmManifest(name="m1", workspace="default", agent="default/clockbot", port=8000)
    mock_entity_client.get = AsyncMock(return_value=existing)
    mock_entity_client.update = AsyncMock(side_effect=lambda entity: entity)

    resp = client.patch(
        "/apis/iron-swarm/v2/workspaces/default/manifests/m1",
        json={"egress": ["en.wikipedia.org", "api.example.com:443"]},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["egress"] == ["en.wikipedia.org", "api.example.com:443"]


def test_create_agent_manifest_persists_egress(client, mock_entity_client) -> None:
    """Passed to the resolver *and* stored: the run re-resolves and would otherwise drop it."""
    mock_entity_client.create = AsyncMock(side_effect=lambda entity: entity)

    resp = client.post(
        "/apis/iron-swarm/v2/workspaces/default/manifests",
        json={"name": "m1", "source_type": "agent", "agent": "clockbot", "egress": ["en.wikipedia.org"]},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["egress"] == ["en.wikipedia.org"]


def test_patch_missing_manifest_returns_404(client, mock_entity_client) -> None:
    mock_entity_client.get = AsyncMock(side_effect=NemoEntityNotFoundError("nope"))

    resp = client.patch("/apis/iron-swarm/v2/workspaces/default/manifests/ghost", json={"port": 9000})

    assert resp.status_code == 404


def test_list_returns_envelope(client, mock_entity_client) -> None:
    manifest = IronSwarmManifest(name="m1", workspace="default", agent="default/clockbot")
    page = MagicMock()
    page.data = [manifest]
    page.pagination = NemoPaginationInfo(page=1, page_size=20, current_page_size=1, total_pages=1, total_results=1)
    mock_entity_client.list = AsyncMock(return_value=page)

    resp = client.get("/apis/iron-swarm/v2/workspaces/default/manifests")

    assert resp.status_code == 200, resp.text
    assert [m["name"] for m in resp.json()["data"]] == ["m1"]
