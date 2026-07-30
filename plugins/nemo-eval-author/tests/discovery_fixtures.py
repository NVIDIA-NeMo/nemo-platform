# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Builders for real Harbor task directories, plus a stub platform client.

The discovery tests assert against Harbor's actual validators rather than against our
reading of them, which only works if the fixtures are things Harbor genuinely accepts. So
these write the same layout ``harbor task create`` produces — ``task.toml``,
``instruction.md``, ``environment/Dockerfile``, ``tests/test.sh``, ``solution/solve.sh`` —
and the interesting cases are departures from it.

Imported as a module rather than declared as fixtures in ``conftest.py`` because the
builders take arguments; a test that needs a Windows task with no reward script should say
so at the call site instead of composing four fixtures to get there.
"""

import json
from pathlib import Path
from typing import Any

WRITES_REWARD = "#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n"

# What Harbor's own template ships: a comment telling the author to write a reward, and no
# code that does. A task scaffolded and abandoned looks exactly like this.
MENTIONS_REWARD_IN_COMMENT = "#!/bin/bash\n\n# Make sure to output a reward to /logs/verifier/reward.txt.\n"

_DOCKERFILE = "FROM ubuntu:24.04\n\nWORKDIR /app\n"
_SOLVE = "#!/bin/bash\necho solved\n"


def write_task(
    task_dir: Path,
    *,
    task_toml: str = "",
    instruction: str | None = "Do the thing.\n",
    test_script: str | None = WRITES_REWARD,
    test_name: str = "test.sh",
    environment: bool = True,
    steps: dict[str, dict[str, str | None]] | None = None,
) -> Path:
    """Write a Harbor task directory, defaulting to one Harbor accepts.

    Args:
        task_toml: TOML appended after the version line. The baseline deliberately declares
            no sections, so a caller can add ``[environment]`` or ``[verifier]`` without
            colliding with a duplicate table.
        instruction: Root ``instruction.md`` contents; ``None`` to omit it.
        test_script: Root ``tests/`` script contents; ``None`` to omit it.
        test_name: Root test filename, so a Windows task can ask for ``test.bat``.
        environment: Whether to write ``environment/Dockerfile``.
        steps: Multi-step layout as ``{step_name: {"instruction": ..., "test": ...}}``,
            where a ``None`` value omits that file.
    """
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(f'version = "1.0"\n{task_toml}', encoding="utf-8")

    if instruction is not None:
        (task_dir / "instruction.md").write_text(instruction, encoding="utf-8")
    if environment:
        (task_dir / "environment").mkdir(exist_ok=True)
        (task_dir / "environment" / "Dockerfile").write_text(_DOCKERFILE, encoding="utf-8")
    if test_script is not None:
        (task_dir / "tests").mkdir(exist_ok=True)
        (task_dir / "tests" / test_name).write_text(test_script, encoding="utf-8")

    (task_dir / "solution").mkdir(exist_ok=True)
    (task_dir / "solution" / "solve.sh").write_text(_SOLVE, encoding="utf-8")

    for name, files in (steps or {}).items():
        step_dir = task_dir / "steps" / name
        step_dir.mkdir(parents=True, exist_ok=True)
        if files.get("instruction") is not None:
            (step_dir / "instruction.md").write_text(str(files["instruction"]), encoding="utf-8")
        if files.get("test") is not None:
            (step_dir / "tests").mkdir(exist_ok=True)
            (step_dir / "tests" / "test.sh").write_text(str(files["test"]), encoding="utf-8")
    return task_dir


def write_dataset(root: Path, *, count: int = 2, test_script: str = WRITES_REWARD) -> Path:
    """A directory of sibling task dirs, which is what Harbor treats as a dataset."""
    for index in range(count):
        write_task(root / f"task-{index}", test_script=test_script)
    return root


def write_wrapper(repo_root: Path, *, class_name: str = "WrappedAgent", base: str = "BaseAgent") -> Path:
    """A ``harbor_wrapper.py`` holding a real ``BaseAgent`` subclass."""
    path = repo_root / "harbor_wrapper.py"
    path.write_text(
        f"from harbor.agents.base import {base}\n\n\n"
        f"class {class_name}({base}):\n"
        "    @staticmethod\n"
        "    def name() -> str:\n"
        f"        return {class_name.lower()!r}\n\n"
        "    async def setup(self, environment):\n"
        "        return None\n\n"
        "    async def run(self, instruction, environment):\n"
        "        return None\n",
        encoding="utf-8",
    )
    return path


def write_job_dir(root: Path, *, config: dict[str, Any], with_lock: bool = True) -> Path:
    """A completed Harbor job directory, which is a config Harbor already resolved."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    if with_lock:
        (root / "lock.json").write_text(json.dumps({"harbor_version": "0.18.0"}), encoding="utf-8")
    return root


class StubFiles:
    """Records uploads and serves whatever was uploaded before, like the real thing."""

    def __init__(self, stored: dict[str, bytes] | None = None, fail: bool = False) -> None:
        self.stored: dict[str, bytes] = dict(stored or {})
        self.uploads: list[dict[str, Any]] = []
        self.fail = fail

    async def upload_content(self, *, content: bytes, remote_path: str, **kwargs: Any) -> None:
        if self.fail:
            raise RuntimeError("fileset unavailable")
        self.uploads.append({"remote_path": remote_path, "content": content, **kwargs})
        self.stored[remote_path] = content

    async def download_content(self, *, remote_path: str, **kwargs: Any) -> bytes:
        if remote_path not in self.stored:
            raise FileNotFoundError(remote_path)
        return self.stored[remote_path]


class StubClient:
    """The narrow slice of ``AsyncNeMoPlatform`` discovery touches."""

    def __init__(self, files: StubFiles | None = None, trace_total: int | None = 3) -> None:
        self.files = files or StubFiles()
        self.intake = _StubIntake(trace_total)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _StubIntake:
    def __init__(self, total: int | None) -> None:
        self.spans = _StubSpans(total)


class _StubSpans:
    def __init__(self, total: int | None) -> None:
        self.groups = _StubGroups(total)


class _StubGroups:
    def __init__(self, total: int | None) -> None:
        self._total = total

    async def list(self, **kwargs: Any) -> Any:
        if self._total is None:
            raise RuntimeError("intake unreachable")
        return _StubPage(self._total)


class _StubPage:
    def __init__(self, total: int) -> None:
        self.data = [object()] * min(total, 1)
        self.pagination = _StubPagination(total)


class _StubPagination:
    def __init__(self, total: int) -> None:
        self.total_results = total
