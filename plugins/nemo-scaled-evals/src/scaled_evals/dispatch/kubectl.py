# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Low-level kubectl execution without provider-specific failure policy."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_DEFAULT_TIMEOUT_SECONDS = 120.0
# Matches the shell convention for a command killed by `timeout`.
_TIMEOUT_RETURNCODE = 124


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
    # Bounded by default: a hung `kubectl` on an unreachable API server would otherwise
    # block the calling dispatch worker until it is restarted, so the evaluation it was
    # tearing down never finalizes. Callers that need longer pass their own value.
    timeout_seconds: float | None = _DEFAULT_TIMEOUT_SECONDS,
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
    try:
        completed = runner(args, **kwargs)
    except subprocess.TimeoutExpired:
        # Reported as a failed command rather than raised. Callers branch on returncode and
        # the sandbox cleanup path only catches RuntimeError, so a raised TimeoutExpired
        # would escape and take the worker down instead of failing this one teardown.
        return KubectlResult(
            returncode=_TIMEOUT_RETURNCODE,
            stdout="",
            stderr=f"kubectl timed out after {timeout_seconds}s",
        )
    return KubectlResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
