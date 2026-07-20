# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import os
import stat
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval import workspace_seeds
from nemo_evaluator_sdk.agent_eval.runtimes.codex import runtime as codex_runtime
from nemo_evaluator_sdk.agent_eval.runtimes.docker_sandbox import DockerSandboxAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from pydantic import BaseModel

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
            # Default prompt is exactly the instruction from inputs — no runtime framing — and never
            # leaks the eval-side `intent`.
            assert input == b"Question?"
            assert b"Answer." not in input  # intent stays eval-side
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            final_output_path.write_text("codex answer", encoding="utf-8")
            return b'{"type":"event"}\n', b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        evidence_dir = Path(command[command.index("--output-last-message") + 1]).parent
        assert stat.S_IMODE(evidence_dir.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(evidence_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE((evidence_dir / "workspace").stat().st_mode) == 0o700
        assert stat.S_IMODE((evidence_dir / "task.json").stat().st_mode) == 0o600
        assert stat.S_IMODE((evidence_dir / "prompt.txt").stat().st_mode) == 0o600
        commands.append((command, kwargs))
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(
        model="gpt-5",
        work_root=tmp_path / "codex",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(id="task/1", intent="Answer.", inputs={"instruction": "Question?"})

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
    final_output = tmp_path / "codex" / "000000-task-1" / "final_output.txt"
    assert final_output.read_text(encoding="utf-8") == "codex answer"
    assert final_output.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "codex" / "000000-task-1" / "stdout.jsonl").read_text(encoding="utf-8") == '{"type":"event"}\n'
    assert (tmp_path / "codex" / "000000-task-1" / "stdout.jsonl").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "codex" / "000000-task-1" / "stderr.txt").stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_codex_task_json_omits_grader_only_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The docker variant mounts the evidence dir into the sandbox (danger-full-access), so the persisted
    # task.json must never carry grader-only fields — otherwise the agent could read `intent` (desired
    # behavior) or the held-out `reference` back out of /evidence and reward-hack. Enforced on the shared
    # base runtime so both the local and docker variants persist an agent-safe task.json.
    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            final_output_path.write_text("ok", encoding="utf-8")
            return b"", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(work_root=tmp_path / "codex", process_factory=fake_process_factory)
    task = AgentEvalTask(
        id="task/1",
        intent="SECRET_GRADER_INTENT",
        inputs={"instruction": "do the thing"},
        reference={"expected": "HELD_OUT_GROUND_TRUTH"},
    )

    await runtime.run_tasks([task])

    task_json = (tmp_path / "codex" / "000000-task-1" / "task.json").read_text(encoding="utf-8")
    assert "SECRET_GRADER_INTENT" not in task_json  # intent is eval-side desired-behavior metadata
    assert "HELD_OUT_GROUND_TRUTH" not in task_json  # reference is grader-only ground truth
    assert '"intent"' not in task_json and '"reference"' not in task_json  # dropped entirely, not just empty
    assert "do the thing" in task_json  # agent-safe fields (id, inputs) are still persisted


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
            assert input == b"Question?"  # prompt is the instruction verbatim
            evidence_mount = self.command[self.command.index(f"{auth_path.resolve()}:/root/.codex/auth.json:ro") + 4]
            evidence_dir = Path(evidence_mount.split(":/evidence", maxsplit=1)[0])
            (evidence_dir / "final_output.txt").write_text("docker codex answer", encoding="utf-8")
            for directory, _subdirectories, filenames in os.walk(evidence_dir):
                Path(directory).chmod(0o700)
                for filename in filenames:
                    (Path(directory) / filename).chmod(0o600)
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
    task = AgentEvalTask(id="task/1", intent="Answer.", inputs={"instruction": "Question?"})

    trials = await runtime.run_tasks([task])

    command, kwargs = commands[0]
    assert command[:4] == ("docker", "run", "--rm", "-i")
    assert command[command.index("-e") + 1] == "PYTHONDONTWRITEBYTECODE=1"
    assert f"{auth_path.resolve()}:/root/.codex/auth.json:ro" in command
    assert f"{(tmp_path / 'codex-docker' / '000000-task-1' / 'workspace').resolve()}:/workspace" in command
    assert f"{(tmp_path / 'codex-docker' / '000000-task-1').resolve()}:/evidence" in command
    assert command[-3:] == ("sh", "-lc", command[-1])
    assert f"npx -y {codex_runtime.DEFAULT_CODEX_DOCKER_CLI_PACKAGE} exec" in command[-1]
    assert "--sandbox danger-full-access" in command[-1]
    assert "--model gpt-5.4" in command[-1]
    assert "host_owner=\"$(stat -c '%u:%g' /evidence 2>/dev/null)\" || true" in command[-1]
    assert command[-1].index("host_owner=") < command[-1].index("npx -y")
    assert "codex_status=$?" in command[-1]
    assert 'chown -R "$host_owner" /workspace /evidence 2>/dev/null || true' in command[-1]
    assert "chmod -R u+rwX,go-rwx /workspace /evidence" in command[-1]
    assert 'if [ "$codex_status" -ne 0 ]; then exit "$codex_status"; fi' in command[-1]
    assert 'exit "$permissions_status"' in command[-1]
    assert command[-1].index('if [ "$codex_status"') < command[-1].index('exit "$permissions_status"')
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
    task = AgentEvalTask(id="task-timeout", intent="Answer.", inputs={"instruction": "Q?"})

    trials = await runtime.run_tasks([task])

    assert process.killed is True
    assert trials[0].status == "failed"
    assert trials[0].output is None
    assert trials[0].metadata["error_type"] == "TimeoutError"
    assert (tmp_path / "codex" / "000000-task-timeout" / "error.json").stat().st_mode & 0o777 == 0o600


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
    task = AgentEvalTask(id="task-2", intent="Answer.", inputs={"instruction": "Q?"})

    trials = await runtime.run_tasks([task])

    assert trials[0].status == "completed"
    assert trials[0].output is not None
    assert trials[0].output.output_text == "stdout fallback\n"
    final_output = tmp_path / "codex" / "000000-task-2" / "final_output.txt"
    assert final_output.read_text(encoding="utf-8") == "stdout fallback\n"
    assert final_output.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_rejects_agent_created_final_output_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external.txt"
    external.write_text("secret", encoding="utf-8")

    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            final_output_path.symlink_to(external)
            return b"stdout fallback\n", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(work_root=tmp_path / "codex", process_factory=fake_process_factory)
    task = AgentEvalTask(id="task-symlink", intent="Answer.", inputs={"instruction": "Q?"})

    trials = await runtime.run_tasks([task])

    assert trials[0].status == "failed"
    assert trials[0].output is None
    assert trials[0].metadata["error_type"] == "OSError"
    assert external.read_text(encoding="utf-8") == "secret"


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_rejects_agent_created_final_output_fifo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            os.mkfifo(final_output_path, 0o600)
            final_output_path.chmod(0o600)
            return b"stdout fallback\n", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(work_root=tmp_path / "codex", process_factory=fake_process_factory)
    task = AgentEvalTask(id="task-fifo", intent="Answer.", inputs={"instruction": "Q?"})

    trials = await asyncio.wait_for(runtime.run_tasks([task]), timeout=5)

    assert trials[0].status == "failed"
    assert trials[0].output is None
    assert trials[0].metadata["error_type"] == "PermissionError"


def test_private_directory_creation_repairs_modes_and_rejects_unsafe_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_dir = tmp_path / "private"
    private_dir.mkdir(mode=0o755)

    codex_runtime._ensure_private_directory(private_dir)

    assert stat.S_IMODE(private_dir.stat().st_mode) == 0o700

    symlink = tmp_path / "symlink"
    symlink.symlink_to(private_dir, target_is_directory=True)
    with pytest.raises(OSError):
        codex_runtime._ensure_private_directory(symlink)

    not_a_directory = tmp_path / "file"
    not_a_directory.touch()
    with pytest.raises(FileExistsError):
        codex_runtime._ensure_private_directory(not_a_directory)

    different_uid = os.getuid() + 1
    monkeypatch.setattr(codex_runtime.os, "getuid", lambda: different_uid)
    with pytest.raises(PermissionError, match="not owned"):
        codex_runtime._ensure_private_directory(private_dir)


def test_private_text_write_is_owner_only_atomic_and_replaces_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external.txt"
    external.write_text("external", encoding="utf-8")
    target = tmp_path / "artifact.txt"
    target.symlink_to(external)
    original_replace = codex_runtime.os.replace

    def checked_replace(source: str | Path, destination: str | Path) -> None:
        assert stat.S_IMODE(Path(source).stat().st_mode) == 0o600
        original_replace(source, destination)

    monkeypatch.setattr(codex_runtime.os, "replace", checked_replace)

    codex_runtime._write_private_text(target, "private")

    assert not target.is_symlink()
    assert target.read_text(encoding="utf-8") == "private"
    assert external.read_text(encoding="utf-8") == "external"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_private_text_write_cleans_temporary_file_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "artifact.txt"
    explicitly_closed: list[int] = []
    original_close = codex_runtime.os.close

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("replace failed")

    def track_close(descriptor: int) -> None:
        explicitly_closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(codex_runtime.os, "replace", fail_replace)
    monkeypatch.setattr(codex_runtime.os, "close", track_close)

    with pytest.raises(OSError, match="replace failed"):
        codex_runtime._write_private_text(target, "private")

    assert explicitly_closed == []
    assert list(tmp_path.glob(".artifact.txt.*.tmp")) == []


def test_private_text_write_closes_descriptor_when_fdopen_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "artifact.txt"
    explicitly_closed: list[int] = []
    original_close = codex_runtime.os.close

    def fail_fdopen(descriptor: int, mode: str, *, encoding: str) -> None:
        raise OSError("fdopen failed")

    def track_close(descriptor: int) -> None:
        explicitly_closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(codex_runtime.os, "fdopen", fail_fdopen)
    monkeypatch.setattr(codex_runtime.os, "close", track_close)

    with pytest.raises(OSError, match="fdopen failed"):
        codex_runtime._write_private_text(target, "private")

    assert len(explicitly_closed) == 1
    assert list(tmp_path.glob(".artifact.txt.*.tmp")) == []


@pytest.mark.asyncio
async def test_setup_failure_does_not_write_error_through_untrusted_evidence_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work_root = tmp_path / "codex"
    work_root.mkdir(mode=0o700)
    external = tmp_path / "external"
    external.mkdir()
    evidence_dir = work_root / "000000-task-symlink"
    evidence_dir.symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(work_root=work_root)
    task = AgentEvalTask(id="task-symlink", intent="Answer.", inputs={"instruction": "Q?"})

    trial = (await runtime.run_tasks([task]))[0]

    assert trial.status == "failed"
    assert trial.output is None
    assert trial.evidence is None
    assert not (external / "error.json").exists()


def test_private_tree_validation_is_root_inclusive_and_does_not_follow_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "evidence"
    root.mkdir(mode=0o700)
    nested = root / "nested"
    nested.mkdir(mode=0o700)
    regular = nested / "regular.txt"
    regular.write_text("ok", encoding="utf-8")
    regular.chmod(0o600)
    executable = nested / "script.sh"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    (nested / "host-link").symlink_to("/etc/passwd")

    codex_runtime._validate_private_tree(root)

    regular.chmod(0o640)
    with pytest.raises(PermissionError, match="group or other"):
        codex_runtime._validate_private_tree(root)
    regular.chmod(0o400)
    with pytest.raises(PermissionError, match="owner-readable and writable"):
        codex_runtime._validate_private_tree(root)
    regular.chmod(0o600)
    root.chmod(0o750)
    with pytest.raises(PermissionError, match="group or other"):
        codex_runtime._validate_private_tree(root)
    root.chmod(0o700)
    different_uid = os.getuid() + 1
    monkeypatch.setattr(codex_runtime.os, "getuid", lambda: different_uid)
    with pytest.raises(PermissionError, match="not owned"):
        codex_runtime._validate_private_tree(root)


def test_private_tree_validation_rejects_special_files(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir(mode=0o700)
    fifo = root / "agent.fifo"
    os.mkfifo(fifo, 0o600)
    fifo.chmod(0o600)

    with pytest.raises(PermissionError, match="not a regular file or directory"):
        codex_runtime._validate_private_tree(root)


@pytest.mark.asyncio
async def test_codex_success_fails_when_permission_postcondition_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{}", encoding="utf-8")

    class FakeProcess:
        returncode = 0

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            return b"", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess()

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexDockerCliAgentRuntime(
        work_root=tmp_path / "codex-docker",
        auth_path=auth_path,
        process_factory=fake_process_factory,
    )

    def fail_validation(evidence_dir: Path) -> None:
        raise PermissionError("unsafe evidence")

    monkeypatch.setattr(runtime, "_validate_artifact_permissions", fail_validation)
    task = AgentEvalTask(id="success", intent="Succeed.", inputs={"instruction": "succeed"})

    (trial,) = await runtime.run_tasks([task])

    assert trial.status == "failed"
    assert trial.metadata["error_type"] == "PermissionError"
    assert "unsafe evidence" in trial.metadata["permission_cleanup_error"]


@pytest.mark.asyncio
async def test_codex_failure_preserves_status_and_reports_permission_cleanup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{}", encoding="utf-8")

    class FakeProcess:
        returncode = 23

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            return b"", b"codex failed"

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess()

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexDockerCliAgentRuntime(
        work_root=tmp_path / "codex-docker",
        auth_path=auth_path,
        process_factory=fake_process_factory,
    )

    def fail_validation(evidence_dir: Path) -> None:
        raise PermissionError("unsafe evidence")

    monkeypatch.setattr(runtime, "_validate_artifact_permissions", fail_validation)
    task = AgentEvalTask(id="failure", intent="Fail.", inputs={"instruction": "fail"})

    (trial,) = await runtime.run_tasks([task])

    assert trial.status == "failed"
    assert "status 23" in trial.metadata["error"]
    assert "unsafe evidence" in trial.metadata["permission_cleanup_error"]


def test_failed_trial_survives_inaccessible_error_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = AgentEvalTask(id="failure", intent="Fail.", inputs={"instruction": "fail"})

    def fail_write(path: Path, content: str) -> None:
        raise PermissionError("inaccessible")

    monkeypatch.setattr(codex_runtime, "_write_private_text", fail_write)

    trial = codex_runtime._failed_codex_trial(task, tmp_path / "missing", RuntimeError("original"))

    assert trial.status == "failed"
    assert trial.evidence is None
    assert trial.metadata["error"] == "original"
    assert "inaccessible" in trial.metadata["error_artifact_error"]


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_seeds_workspace_and_stamps_agent_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            # Seed files are staged into the workspace before the agent runs.
            workspace_dir = Path(self.command[self.command.index("--cd") + 1])
            assert (workspace_dir / "buggy.py").read_text(encoding="utf-8") == "def add(a, b)\n    return a + b\n"
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
        inputs={"instruction": "fix the bug", "files": {"buggy.py": "def add(a, b)\n    return a + b\n"}},
    )

    trials = await runtime.run_tasks([task])

    assert trials[0].status == "completed"
    # agent_ok is stamped so AgentPhaseSuccessMetric works over Codex trials.
    assert trials[0].metadata["agent_ok"] is True
    assert trials[0].metadata["seeded_files"] == ["buggy.py"]


@pytest.mark.asyncio
async def test_codex_cli_agent_runtime_seeds_off_the_event_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seeding is synchronous and a handler may block (e.g. the plugin's fileset download). It runs on
    # the event loop shared by every concurrent task, so it must be offloaded to a worker thread —
    # otherwise one slow seed stalls the whole run. Register a probe handler that records the thread
    # it resolves on and assert it is not the loop thread.
    class _ProbeSeed(BaseModel):
        kind: str = "thread_probe"

    class _ProbeHandler:
        kind = "thread_probe"
        resolved_on: int | None = None

        def parse(self, value: Mapping[str, Any]) -> BaseModel:
            return _ProbeSeed()

        def resolve(self, seed: BaseModel) -> bytes:
            _ProbeHandler.resolved_on = threading.get_ident()
            return b"probe"

    monkeypatch.setitem(workspace_seeds._HANDLERS, "thread_probe", _ProbeHandler())

    class FakeProcess:
        returncode = 0

        def __init__(self, command: tuple[str, ...]) -> None:
            self.command = command

        async def communicate(self, input: bytes) -> tuple[bytes, bytes]:
            final_output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            final_output_path.write_text("ok", encoding="utf-8")
            return b"", b""

    async def fake_process_factory(*command: str, **kwargs: Any) -> FakeProcess:
        return FakeProcess(command)

    monkeypatch.setattr(codex_runtime.shutil, "which", lambda value: f"/bin/{value}")
    runtime = codex_runtime.CodexCliAgentRuntime(
        work_root=tmp_path / "codex",
        process_factory=fake_process_factory,
    )
    task = AgentEvalTask(
        id="probe", intent="probe", inputs={"instruction": "run", "files": {"p.txt": {"kind": "thread_probe"}}}
    )

    trials = await runtime.run_tasks([task])

    assert trials[0].status == "completed"
    assert _ProbeHandler.resolved_on is not None
    assert _ProbeHandler.resolved_on != threading.get_ident()


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
    assert trials[0].metadata["error_type"] == "WorkspaceSeedError"
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
