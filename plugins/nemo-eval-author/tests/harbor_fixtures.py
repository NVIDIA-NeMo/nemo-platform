# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor task builders and platform stubs."""

from pathlib import Path
from typing import Any

import yaml


def read_front_matter(text: str | bytes) -> dict[str, Any]:
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    assert text.startswith("---\n"), f"no front matter in {text[:40]!r}"
    payload = yaml.safe_load(text[4:].partition("\n---\n")[0])
    assert isinstance(payload, dict)
    return payload


def write_task(
    task_dir: Path,
    *,
    task_toml: str = "",
    instruction: str | None = "Do the thing.\n",
) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(f'version = "1.0"\n{task_toml}', encoding="utf-8")

    if instruction is not None:
        (task_dir / "instruction.md").write_text(instruction, encoding="utf-8")
    (task_dir / "environment").mkdir(exist_ok=True)
    (task_dir / "environment" / "Dockerfile").write_text("FROM ubuntu:24.04\n\nWORKDIR /app\n", encoding="utf-8")
    (task_dir / "tests").mkdir(exist_ok=True)
    (task_dir / "tests" / "test.sh").write_text("#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n", encoding="utf-8")


def write_dataset(root: Path, *, count: int = 2) -> Path:
    for index in range(count):
        write_task(root / f"task-{index}")
    return root


def write_wrapper(wrapper_dir: Path, *, class_name: str = "WrappedAgent") -> None:
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    (wrapper_dir / "harbor_wrapper.py").write_text(
        f"from harbor.agents.base import BaseAgent\n\n\nclass {class_name}(BaseAgent):\n    pass\n",
        encoding="utf-8",
    )


def write_job_config(path: Path, *, dataset: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agents": [{"name": "oracle"}], "datasets": [{"path": dataset}]}
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


class StubFiles:
    def __init__(self, fail: bool = False) -> None:
        self.stored: dict[str, bytes] = {}
        self.uploads: list[dict[str, Any]] = []
        self.fail = fail

    async def upload_content(self, *, content: bytes, remote_path: str, **kwargs: Any) -> None:
        if self.fail:
            raise RuntimeError("fileset unavailable")
        self.uploads.append({"remote_path": remote_path, "content": content, **kwargs})
        self.stored[remote_path] = content


class StubClient:
    def __init__(self, files: StubFiles | None = None) -> None:
        self.files = files or StubFiles()
        self.closed = False

    async def close(self) -> None:
        self.closed = True
