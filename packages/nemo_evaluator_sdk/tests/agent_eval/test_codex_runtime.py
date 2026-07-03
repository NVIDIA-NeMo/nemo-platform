# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.codex import runtime as codex_runtime
from nemo_evaluator_sdk.agent_eval.runtimes.docker_sandbox import DockerSandboxAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask

# The runtime *selection* (local vs docker-cli vs docker-sandbox) is generic and lives here; only the
# ProfBench ``score_source`` labels + candidate prompt live in the example (test_profbench_codex_target).


def _prompt_builder(task: AgentEvalTask) -> str:
    return f"do: {task.id}\n"


def test_resolve_codex_runtime_local_cli_threads_prompt_builder(tmp_path: Path) -> None:
    target, effective = codex_runtime.resolve_codex_runtime(
        runtime=codex_runtime.RuntimeChoice.LOCAL,
        model="gpt-5",
        output_dir=tmp_path / "run",
        env={"OPENAI_API_KEY": "sk-test-key"},
        prompt_builder=_prompt_builder,
    )

    assert isinstance(target, codex_runtime.CodexCliAgentRuntime)
    assert target._model == "gpt-5"
    assert target._work_root == tmp_path / "run" / "evidence" / "codex"
    assert target._prompt_builder is _prompt_builder
    assert effective == codex_runtime.EffectiveCodexRuntime.LOCAL_CLI


def test_resolve_codex_runtime_docker_uses_sandbox_for_openai_secret_key(tmp_path: Path) -> None:
    target, effective = codex_runtime.resolve_codex_runtime(
        runtime=codex_runtime.RuntimeChoice.DOCKER,
        model=None,
        output_dir=tmp_path / "run",
        env={"OPENAI_API_KEY": "sk-test-key"},
    )

    assert isinstance(target, DockerSandboxAgentRuntime)
    assert target._model == codex_runtime.DEFAULT_CODEX_DOCKER_MODEL
    assert effective == codex_runtime.EffectiveCodexRuntime.DOCKER_SANDBOX


def test_resolve_codex_runtime_docker_falls_back_to_cli_without_sdk_key(tmp_path: Path) -> None:
    target, effective = codex_runtime.resolve_codex_runtime(
        runtime=codex_runtime.RuntimeChoice.DOCKER,
        model="gpt-5.4",
        output_dir=tmp_path / "run",
        env={"OPENAI_API_KEY": "oauth-token"},
        prompt_builder=_prompt_builder,
    )

    assert isinstance(target, codex_runtime.CodexDockerCliAgentRuntime)
    assert target._work_root == tmp_path / "run" / "evidence" / "codex-docker"
    assert target._prompt_builder is _prompt_builder
    assert effective == codex_runtime.EffectiveCodexRuntime.DOCKER_CLI


def test_list_codex_agent_models_prints_visible_models(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeCompletedProcess:
        stdout = json.dumps(
            {
                "models": [
                    {"slug": "hidden", "display_name": "Hidden", "visibility": "hidden", "priority": 99},
                    {"slug": "gpt-5.4-mini", "display_name": "GPT-5.4 Mini", "visibility": "list", "priority": 3},
                    {"slug": "gpt-5.5", "display_name": "GPT-5.5", "visibility": "list", "priority": 9},
                ]
            }
        )

    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> FakeCompletedProcess:
        assert command == ["codex", "debug", "models"]
        assert check is True
        assert capture_output is True
        assert text is True
        return FakeCompletedProcess()

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    monkeypatch.setattr(codex_runtime.subprocess, "run", fake_run)

    codex_runtime.print_codex_agent_models()

    assert capsys.readouterr().out.splitlines() == [
        "gpt-5.5\tGPT-5.5",
        "gpt-5.4-mini\tGPT-5.4 Mini",
    ]


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_uses_local_codex_command_and_writes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            # Default prompt is task-agnostic: it states the task and invites workspace edits.
            assert b"Task id: task/1" in input
            assert b"Intent:" in input
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            final_output_path.write_text("codex answer", encoding="utf-8")
            return b'{"type":"event"}\n', b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        commands.append((command, kwargs))
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(
        model="gpt-5",
        work_root=tmp_path / "codex",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(id="task/1", intent="Answer.", inputs={"prompt": "Question?"})

    trials = await runtime.run_tasks([task])

    command, kwargs = commands[0]
    assert command[:2] == ("codex", "exec")
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--skip-git-repo-check" in command
    assert command[command.index("--model") + 1] == "gpt-5"
    assert command[-1] == "-"
    assert kwargs["stdin"] == codex_runtime.subprocess.PIPE
    assert trials[0].status == "completed"
    assert trials[0].output is not None
    assert trials[0].output.output_text == "codex answer"
    assert trials[0].evidence is not None
    assert trials[0].evidence.require("workspace", kind="filesystem").ref == str(
        tmp_path / "codex" / "000000-task-1" / "workspace"
    )
    assert (tmp_path / "codex" / "000000-task-1" / "stdout.jsonl").read_text(encoding="utf-8") == '{"type":"event"}\n'


@pytest.mark.asyncio
async def test_codex_docker_cli_agent_runtime_runs_codex_in_container_and_writes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{}", encoding="utf-8")
    commands: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            assert b"Task id: task/1" in input
            evidence_mount = self.command[self.command.index(f"{auth_path.resolve()}:/root/.codex/auth.json:ro") + 4]
            evidence_dir = Path(evidence_mount.split(":/evidence", maxsplit=1)[0])
            (evidence_dir / "final_output.txt").write_text("docker codex answer", encoding="utf-8")
            return b'{"type":"event"}\n', b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        commands.append((command, kwargs))
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexDockerCliAgentRuntime(
        model="gpt-5.4",
        work_root=tmp_path / "codex-docker",
        auth_path=auth_path,
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(id="task/1", intent="Answer.", inputs={"prompt": "Question?"})

    trials = await runtime.run_tasks([task])

    command, kwargs = commands[0]
    assert command[:4] == ("docker", "run", "--rm", "-i")
    assert f"{auth_path.resolve()}:/root/.codex/auth.json:ro" in command
    assert f"{(tmp_path / 'codex-docker' / '000000-task-1' / 'workspace').resolve()}:/workspace" in command
    assert f"{(tmp_path / 'codex-docker' / '000000-task-1').resolve()}:/evidence" in command
    assert command[-3:] == ("sh", "-lc", command[-1])
    assert f"npx -y {codex_runtime.DEFAULT_CODEX_DOCKER_CLI_PACKAGE} exec" in command[-1]
    assert "--sandbox danger-full-access" in command[-1]
    assert "--model gpt-5.4" in command[-1]
    assert kwargs["stdin"] == codex_runtime.subprocess.PIPE
    assert trials[0].status == "completed"
    assert trials[0].output is not None
    assert trials[0].output.output_text == "docker codex answer"
    assert trials[0].metadata["runtime"] == "codex_docker_cli"
    assert trials[0].evidence is not None
    assert trials[0].evidence.metadata["runtime"] == "codex_docker_cli"


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_kills_process_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.killed = False

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            return b"", b""

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    process = FakeProcess()

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return process

    async def fake_wait_for(awaitable: Any, timeout: float) -> Any:
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    monkeypatch.setattr(codex_runtime.asyncio, "wait_for", fake_wait_for)
    runtime = codex_runtime.CodexCliAgentRuntime(
        work_root=tmp_path / "codex",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(id="task-timeout", intent="Answer.", inputs={"prompt": "Q?"})

    trials = await runtime.run_tasks([task])

    assert process.killed is True
    assert trials[0].status == "failed"
    assert trials[0].output is None
    assert trials[0].metadata["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_falls_back_to_stdout_and_persists_final_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            return b"stdout fallback\n", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess()

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(
        work_root=tmp_path / "codex",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(id="task-2", intent="Answer.", inputs={"prompt": "Q?"})

    trials = await runtime.run_tasks([task])

    assert trials[0].status == "completed"
    assert trials[0].output is not None
    assert trials[0].output.output_text == "stdout fallback\n"
    final_output = tmp_path / "codex" / "000000-task-2" / "final_output.txt"
    assert final_output.read_text(encoding="utf-8") == "stdout fallback\n"


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_seeds_workspace_and_stamps_agent_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            # Seed files are staged before the agent runs and listed (by name) in the prompt.
            workspace_dir = Path(self.command[self.command.index("--cd") + 1])
            assert (workspace_dir / "buggy.py").read_text(encoding="utf-8") == "def add(a, b)\n    return a + b\n"
            assert b"buggy.py" in input
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            final_output_path.write_text("fixed it", encoding="utf-8")
            return b"", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(
        work_root=tmp_path / "codex",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(
        id="fix-bug",
        intent="Fix the syntax error.",
        inputs={"files": {"buggy.py": "def add(a, b)\n    return a + b\n"}},
    )

    trials = await runtime.run_tasks([task])

    assert trials[0].status == "completed"
    # agent_ok is stamped so AgentPhaseSuccessMetric works over Codex trials.
    assert trials[0].metadata["agent_ok"] is True
    assert trials[0].metadata["seeded_files"] == ["buggy.py"]


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_rejects_seed_path_escaping_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_process_factory(*command: str, **kwargs: Any) -> Any:  # pragma: no cover - never reached
        raise AssertionError("agent should not run when seeding fails")

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(
        work_root=tmp_path / "codex",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(id="evil", intent="escape", inputs={"files": {"../escape.txt": "x"}})

    # A traversal path is surfaced as a failed trial (the exception is caught per-task).
    trials = await runtime.run_tasks([task])
    assert trials[0].status == "failed"
    assert trials[0].metadata["error_type"] == "ValueError"
    assert trials[0].metadata["agent_ok"] is False


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_uses_injected_prompt_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            assert input == b"CUSTOM: fix-bug\n"
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            final_output_path.write_text("ok", encoding="utf-8")
            return b"", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(
        work_root=tmp_path / "codex",
        prompt_builder=lambda task: f"CUSTOM: {task.id}\n",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(id="fix-bug", intent="Fix.", inputs={})

    trials = await runtime.run_tasks([task])
    assert trials[0].status == "completed"
