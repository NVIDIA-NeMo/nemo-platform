# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker CLI helpers for agent-eval runtimes.

These shell out to the ``docker`` CLI (stdlib ``subprocess`` only), so importing
this module does not require the ``agent-runtimes`` extra — only a working
``docker`` binary at call time.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence


def redact_cmd_for_logging(cmd: Sequence[str]) -> list[str]:
    """Redact secret values in command logs."""
    redacted: list[str] = []
    sensitive_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    for token in cmd:
        if "=" not in token:
            redacted.append(token)
            continue
        left, right = token.split("=", 1)
        env_key = left.split()[-1] if left else left
        if any(marker in env_key.upper() for marker in sensitive_markers):
            redacted.append(f"{left}=***REDACTED***")
        else:
            redacted.append(f"{left}={right}")
    return redacted


def docker_run(
    image: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    mounts: list[tuple[str, str]] | None = None,
    workdir: str | None = None,
    remove: bool = True,
    timeout: int | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command inside a Docker container."""
    cmd = ["docker", "run"]
    if remove:
        cmd.append("--rm")
    if workdir:
        cmd += ["-w", workdir]

    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]

    for host_path, container_path in mounts or []:
        cmd += ["-v", f"{host_path}:{container_path}"]

    docker_extra = (extra_args or []) + (os.environ.get("DOCKER_EXTRA_ARGS", "").split() or [])
    cmd += docker_extra
    cmd.append(image)
    cmd += command

    print(f"[agent-eval-runtime] $ {' '.join(redact_cmd_for_logging(cmd))}")
    return subprocess.run(cmd, check=False, text=True, timeout=timeout)


def docker_image_exists(tag: str) -> bool:
    """Return True when a Docker image tag exists locally."""
    result = subprocess.run(["docker", "image", "inspect", tag], capture_output=True, text=True, check=False)
    return result.returncode == 0


def build_dockerfile(dockerfile: os.PathLike[str], context_dir: os.PathLike[str], tag: str) -> None:
    """Build a Docker image from an explicit Dockerfile + build context."""
    cmd = ["docker", "build", "-f", str(dockerfile), "-t", tag, str(context_dir)]
    print(f"[agent-eval-runtime] $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def build_task_image(task_dir: os.PathLike[str], tag: str) -> None:
    """Build a task-specific Docker image from ``environment/Dockerfile``."""
    from pathlib import Path

    root = Path(task_dir)
    env_dockerfile = root / "environment" / "Dockerfile"
    if not env_dockerfile.exists():
        raise FileNotFoundError(f"No environment/Dockerfile found in {root}")
    build_dockerfile(env_dockerfile, env_dockerfile.parent, tag)
