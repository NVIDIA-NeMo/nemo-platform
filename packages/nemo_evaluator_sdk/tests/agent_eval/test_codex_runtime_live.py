# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live Docker regressions for host-readable Codex CLI evidence."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import CodexDockerCliAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask

_IMAGE = "node:22-alpine"
_FAKE_PACKAGE_JSON = """{
  "name": "fake-codex",
  "version": "1.0.0",
  "bin": {"fake-codex": "fake-codex.js"}
}
"""
_FAKE_CODEX_JS = """#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function argumentValue(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index + 1 >= process.argv.length) {
    throw new Error(`missing ${name}`);
  }
  return process.argv[index + 1];
}

const workspace = argumentValue("--cd");
const finalOutput = argumentValue("--output-last-message");
const cacheDir = path.join(workspace, "__pycache__");
const cacheFile = path.join(cacheDir, "probe.pyc");
fs.mkdirSync(cacheDir, {recursive: true});
fs.writeFileSync(cacheFile, "fake bytecode");
fs.writeFileSync(finalOutput, "fake codex answer");
fs.symlinkSync("/etc/passwd", path.join(workspace, "host-link"));
fs.chmodSync(cacheFile, 0o000);
fs.chmodSync(cacheDir, 0o000);
fs.chmodSync(finalOutput, 0o000);

const exitCodePath = path.join(workspace, "exit-code.txt");
const exitCode = fs.existsSync(exitCodePath) ? Number(fs.readFileSync(exitCodePath, "utf8")) : 0;
process.exit(exitCode);
"""


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except subprocess.TimeoutExpired:
        return False


pytestmark = pytest.mark.skipif(not _docker_ready(), reason="docker daemon not available")


def _fake_codex_task(task_id: str, *, exit_code: int | None = None) -> AgentEvalTask:
    files = {
        "package.json": _FAKE_PACKAGE_JSON,
        "fake-codex.js": _FAKE_CODEX_JS,
    }
    if exit_code is not None:
        files["exit-code.txt"] = str(exit_code)
    return AgentEvalTask(
        id=task_id,
        intent="Exercise Docker evidence permissions.",
        inputs={"instruction": "Create restrictive evidence.", "files": files},
    )


def _assert_tree_host_private(root: Path) -> None:
    assert root.is_dir()
    for path in (root, *root.rglob("*")):
        if path.is_symlink():
            continue
        path_stat = path.stat()
        mode = stat.S_IMODE(path_stat.st_mode)
        assert path_stat.st_uid == os.getuid(), f"artifact is not owned by the host user: {path}"
        assert mode & 0o077 == 0, f"artifact is accessible to group or other users: {path} ({mode:o})"
        if path.is_dir():
            assert mode & 0o700 == 0o700, f"directory is not accessible to the host user: {path} ({mode:o})"
            assert os.access(path, os.R_OK | os.W_OK | os.X_OK)
        elif path.is_file():
            assert mode & 0o600 == 0o600, f"file is not readable and writable by the host user: {path} ({mode:o})"
            assert os.access(path, os.R_OK | os.W_OK)
            path.read_bytes()


async def test_codex_docker_normalizes_concurrent_workspace_and_evidence_trees(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{}", encoding="utf-8")
    work_root = tmp_path / "codex-docker"
    runtime = CodexDockerCliAgentRuntime(
        work_root=work_root,
        image=_IMAGE,
        codex_package="/workspace",
        auth_path=auth_path,
    )

    trials = await runtime.run_tasks(
        [_fake_codex_task("success-a"), _fake_codex_task("success-b")],
        AgentEvalRunConfig(parallelism=2),
    )

    assert [trial.status for trial in trials] == ["completed", "completed"]
    for trial in trials:
        assert trial.output is not None
        assert trial.output.output_text == "fake codex answer"
        assert trial.evidence is not None
        workspace = await trial.evidence.filesystem("workspace")
        verifier = await workspace.run_verifier(["test", "!", "-e", "host-link"])
        assert verifier.ok

        evidence_dir = Path(trial.output.metadata["evidence_dir"])
        _assert_tree_host_private(evidence_dir / "workspace")
        _assert_tree_host_private(evidence_dir)
        copy = tmp_path / "copies" / trial.task_id
        shutil.copytree(evidence_dir, copy, symlinks=True)
        assert (copy / "workspace" / "host-link").is_symlink()

    assert stat.S_IMODE(work_root.stat().st_mode) == 0o700


async def test_codex_docker_preserves_failure_status_after_permission_normalization(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{}", encoding="utf-8")
    work_root = tmp_path / "codex-docker"
    runtime = CodexDockerCliAgentRuntime(
        work_root=work_root,
        image=_IMAGE,
        codex_package="/workspace",
        auth_path=auth_path,
    )

    (trial,) = await runtime.run_tasks([_fake_codex_task("failure", exit_code=23)])

    assert trial.status == "failed"
    assert trial.metadata["agent_ok"] is False
    assert "status 23" in trial.metadata["error"]
    assert "permission_cleanup_error" not in trial.metadata
    evidence_dir = work_root / "000000-failure"
    _assert_tree_host_private(evidence_dir / "workspace")
    _assert_tree_host_private(evidence_dir)
    assert (evidence_dir / "final_output.txt").read_text(encoding="utf-8") == "fake codex answer"
