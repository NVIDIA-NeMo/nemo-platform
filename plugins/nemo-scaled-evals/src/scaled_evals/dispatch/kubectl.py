# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Low-level kubectl execution without provider-specific failure policy."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KubectlResult:
    returncode: int
    stdout: str
    stderr: str


def execute_kubectl(
    args: list[str],
    input_text: str | None = None,
    *,
    runner: Callable[..., Any] = subprocess.run,
    timeout_seconds: float | None = None,
) -> KubectlResult:
    """Execute kubectl argv and return raw output for the owning provider."""
    kwargs = {
        "input": input_text,
        "capture_output": True,
        "text": True,
        "check": False,
    }
    if timeout_seconds is not None:
        kwargs["timeout"] = timeout_seconds
    completed = runner(args, **kwargs)
    return KubectlResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
