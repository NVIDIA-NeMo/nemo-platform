# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.hook_loading import load_fabric_task_hook
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.hooks import FabricTaskRunSession
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.hooks_mcp_binding import (
    McpRunBindingHook,
    McpRunBindingHookError,
)
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.runtime import _first_mcp_binding_result


@dataclass
class _FakeServer:
    transport: str = "stdio"
    url: str = "placeholder"
    exposure: str = "harness_native"
    env: dict[str, str] = field(default_factory=dict)

    @property
    def extra_fields(self) -> dict[str, Any]:
        return {"env": dict(self.env)} if self.env else {}


@dataclass
class _FakeMcp:
    servers: dict[str, _FakeServer] = field(default_factory=dict)


@dataclass
class _FakeConfig:
    mcp: _FakeMcp = field(default_factory=_FakeMcp)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def add_mcp_server(
        self,
        name: str,
        *,
        transport: str,
        url: str,
        exposure: str = "harness_native",
        extra_fields: dict[str, Any] | None = None,
    ) -> _FakeConfig:
        self.calls.append(
            {
                "name": name,
                "transport": transport,
                "url": url,
                "exposure": exposure,
                "extra_fields": dict(extra_fields or {}),
            }
        )
        existing = self.mcp.servers.get(name)
        env = dict(existing.env) if existing else {}
        if extra_fields and isinstance(extra_fields.get("env"), dict):
            env = dict(extra_fields["env"])
        self.mcp.servers[name] = _FakeServer(transport=transport, url=url, exposure=exposure, env=env)
        return self


@dataclass
class _FakeTask:
    prompt: str = "hello email"

    def agent_prompt(self) -> str:
        return self.prompt


@dataclass
class _FakeAudit:
    analysis: dict[str, Any] | None = None
    invocation_count: int = 1

    def public_mapping(self) -> dict[str, Any]:
        return {"invocation_count": self.invocation_count}


@dataclass
class _FakeBinding:
    mcp_command: Path
    cleaned: bool = False
    verify_calls: int = 0
    create_kwargs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, prompt: str, parent: Path, **kwargs: Any) -> _FakeBinding:
        del prompt
        run_dir = parent / "run-1"
        run_dir.mkdir(parents=True, exist_ok=True)
        command = run_dir / "mcp-bin"
        command.write_text("#!/bin/sh\n", encoding="utf-8")
        return cls(mcp_command=command, create_kwargs=dict(kwargs))

    def verify(self) -> _FakeAudit:
        self.verify_calls += 1
        return _FakeAudit(analysis={"label": "phishing"}, invocation_count=1)

    def cleanup(self) -> None:
        self.cleaned = True


@dataclass
class _FakeHandoff:
    socket_path: Path
    token: str
    closed: bool = False

    @classmethod
    def start(cls, credential: str, timeout_seconds: float = 60.0) -> _FakeHandoff:
        del timeout_seconds
        assert credential
        return cls(socket_path=Path("/tmp/fake.sock"), token="tok")

    def close(self) -> None:
        self.closed = True


@dataclass
class _OrderedBinding:
    name: str
    mcp_command: Path
    events: list[str]
    cleaned: bool = False

    @classmethod
    def factory(cls, name: str, events: list[str]) -> type:
        class _Bound:
            @staticmethod
            def create(prompt: str, parent: Path, **kwargs: Any) -> _OrderedBinding:
                del prompt, kwargs
                events.append(f"create:{name}")
                command = parent / f"{name}-mcp"
                command.write_text("x", encoding="utf-8")
                return cls(name=name, mcp_command=command, events=events)

        return _Bound

    def verify_exactly_once(self) -> _FakeAudit:
        self.events.append(f"verify:{self.name}")
        return _FakeAudit(analysis={"server": self.name})

    def cleanup(self) -> None:
        self.events.append(f"cleanup:{self.name}")
        self.cleaned = True


def test_mcp_run_binding_prepare_preserves_env_and_rebinds_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "secret")
    config = _FakeConfig(
        mcp=_FakeMcp(
            servers={
                "email-phishing-analyzer": _FakeServer(
                    url="placeholder",
                    env={"NVIDIA_API_KEY": "${NVIDIA_API_KEY}"},
                )
            }
        )
    )
    executable = tmp_path / "mcp-exe"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    cfg = tmp_path / "analyzer.yaml"
    cfg.write_text("x: 1\n", encoding="utf-8")

    hook = McpRunBindingHook(
        agent_src=tmp_path,
        bindings=[
            {
                "server": "email-phishing-analyzer",
                "binding": _FakeBinding,
                "executable": executable,
                "config_paths": [cfg],
                "handoff": {"env": "NVIDIA_API_KEY", "ref": _FakeHandoff},
            }
        ],
    )

    session = FabricTaskRunSession()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    out = hook.prepare(config, _FakeTask(), evidence, tmp_path, session)
    assert out is config
    assert len(config.calls) == 1
    call = config.calls[0]
    assert call["name"] == "email-phishing-analyzer"
    assert call["url"].endswith("mcp-bin")
    assert call["extra_fields"]["env"] == {"NVIDIA_API_KEY": "${NVIDIA_API_KEY}"}

    started = session.state["mcp_bindings"][0]
    binding = started["binding"]
    handoff = started["handoff"]
    assert binding.create_kwargs["executable"] == executable.resolve()
    assert binding.create_kwargs["config_path"] == cfg.resolve()
    assert binding.create_kwargs["config_paths"] == [cfg.resolve()]
    assert binding.create_kwargs["credential_token"] == "tok"

    extras = hook.after_success(_FakeTask(), None, session)
    assert extras is not None
    assert extras["mcp_bindings"]["email-phishing-analyzer"]["result"] == {"label": "phishing"}
    assert extras["analyzer_analysis"] == {"label": "phishing"}
    assert binding.verify_calls == 1

    hook.cleanup(session)
    assert binding.cleaned is True
    assert handoff.closed is True
    assert session.state.get("mcp_bindings") is None


def test_mcp_run_binding_order_and_lifo_cleanup(tmp_path: Path) -> None:
    events: list[str] = []
    hook = McpRunBindingHook(
        bindings=[
            {"server": "a", "binding": _OrderedBinding.factory("a", events)},
            {"server": "b", "binding": _OrderedBinding.factory("b", events)},
        ]
    )

    session = FabricTaskRunSession()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    config = _FakeConfig()
    hook.prepare(config, _FakeTask(), evidence, tmp_path, session)
    hook.after_success(_FakeTask(), None, session)
    hook.cleanup(session)
    assert events == [
        "create:a",
        "create:b",
        "verify:a",
        "verify:b",
        "cleanup:b",
        "cleanup:a",
    ]
    assert [c["name"] for c in config.calls] == ["a", "b"]


def test_mcp_run_binding_registers_before_rebind_failure(tmp_path: Path) -> None:
    cleaned: list[str] = []

    class _TrackedBinding(_FakeBinding):
        def cleanup(self) -> None:
            cleaned.append("binding")
            super().cleanup()

    class _FailingConfig(_FakeConfig):
        def add_mcp_server(self, *args: Any, **kwargs: Any) -> _FakeConfig:
            raise RuntimeError("rebind boom")

    hook = McpRunBindingHook(bindings=[{"server": "s1", "binding": _TrackedBinding}])
    session = FabricTaskRunSession()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    with pytest.raises(RuntimeError, match="rebind boom"):
        hook.prepare(_FailingConfig(), _FakeTask(), evidence, tmp_path, session)
    assert cleaned == ["binding"]
    assert session.state.get("mcp_bindings") is None


def test_mcp_run_binding_cleanup_continues_after_individual_failures(tmp_path: Path) -> None:
    events: list[str] = []

    class _BoomBinding:
        @staticmethod
        def create(prompt: str, parent: Path, **kwargs: Any) -> Any:
            del prompt, kwargs
            command = parent / "boom-mcp"
            command.write_text("x", encoding="utf-8")

            class _Inst:
                mcp_command = command

                def verify_exactly_once(self) -> _FakeAudit:
                    return _FakeAudit()

                def cleanup(self) -> None:
                    events.append("cleanup:boom")
                    raise RuntimeError("cleanup failed")

            return _Inst()

    class _OkBinding:
        @staticmethod
        def create(prompt: str, parent: Path, **kwargs: Any) -> Any:
            del prompt, kwargs
            command = parent / "ok-mcp"
            command.write_text("x", encoding="utf-8")

            class _Inst:
                mcp_command = command

                def verify_exactly_once(self) -> _FakeAudit:
                    return _FakeAudit()

                def cleanup(self) -> None:
                    events.append("cleanup:ok")

            return _Inst()

    class _BoomHandoff:
        @classmethod
        def start(cls, credential: str, timeout_seconds: float = 60.0) -> Any:
            del credential, timeout_seconds

            class _H:
                socket_path = Path("/tmp/h.sock")
                token = "t"

                def close(self) -> None:
                    events.append("close:handoff")
                    raise RuntimeError("close failed")

            return _H()

    hook = McpRunBindingHook(
        bindings=[
            {
                "server": "a",
                "binding": _BoomBinding,
                "handoff": {"env": "NVIDIA_API_KEY", "ref": _BoomHandoff},
            },
            {"server": "b", "binding": _OkBinding},
        ]
    )
    session = FabricTaskRunSession()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    monkey_env = pytest.MonkeyPatch()
    monkey_env.setenv("NVIDIA_API_KEY", "secret")
    try:
        hook.prepare(_FakeConfig(), _FakeTask(), evidence, tmp_path, session)
        hook.cleanup(session)
    finally:
        monkey_env.undo()
    assert events == ["cleanup:ok", "cleanup:boom", "close:handoff"]
    assert session.state.get("mcp_bindings") is None


def test_mcp_run_binding_path_based_ref(tmp_path: Path) -> None:
    pkg = tmp_path / "agent_pkg"
    pkg.mkdir()
    # Implicit namespace package (no __init__.py); agent_src puts tmp_path on sys.path.
    (pkg / "audit.py").write_text(
        """
from pathlib import Path

class _Audit:
    analysis = {"label": "x"}
    def public_mapping(self):
        return {"ok": True}

class Binding:
    def __init__(self, mcp_command):
        self.mcp_command = mcp_command
    @classmethod
    def create(cls, prompt, parent, **kwargs):
        path = parent / "cmd"
        path.write_text("x")
        return cls(path)
    def verify(self):
        return _Audit()
    def cleanup(self):
        pass
""",
        encoding="utf-8",
    )

    hook = McpRunBindingHook(
        agent_src=tmp_path,
        bindings=[{"server": "s1", "binding": "agent_pkg.audit:Binding"}],
    )
    session = FabricTaskRunSession()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    config = _FakeConfig()
    hook.prepare(config, _FakeTask(), evidence, tmp_path, session)
    extras = hook.after_success(_FakeTask(), None, session)
    assert extras is not None
    assert extras["mcp_bindings"]["s1"]["audit"] == {"ok": True}
    assert extras["mcp_bindings"]["s1"]["result"] == {"label": "x"}
    hook.cleanup(session)


def test_load_mcp_run_binding_entry_point(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "bin"
    executable.write_text("x", encoding="utf-8")

    class _EP:
        name = "mcp_run_binding"

        def load(self) -> type[McpRunBindingHook]:
            return McpRunBindingHook

    monkeypatch.setattr(
        "nemo_evaluator_sdk.agent_eval.runtimes.fabric.hook_loading.importlib.metadata.entry_points",
        lambda group: [_EP()] if group == "nemo.fabric.task_hooks" else [],
    )
    hook = load_fabric_task_hook(
        {
            "type": "mcp_run_binding",
            "bindings": [
                {
                    "server": "s",
                    "binding": _FakeBinding,
                    "executable": str(executable),
                }
            ],
        }
    )
    assert isinstance(hook, McpRunBindingHook)


def test_mcp_run_binding_rejects_empty_bindings() -> None:
    with pytest.raises(McpRunBindingHookError, match="non-empty"):
        McpRunBindingHook(bindings=[])


def test_first_mcp_binding_result_helper() -> None:
    assert _first_mcp_binding_result({}) is None
    assert _first_mcp_binding_result({"mcp_bindings": {"a": {"audit": {}}, "b": {"result": {"x": 1}}}}) == {"x": 1}
