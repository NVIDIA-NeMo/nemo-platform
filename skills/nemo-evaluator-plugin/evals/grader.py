#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic custom grader for ported Evaluator CLI agentic-use tasks.

ASE overwrites Harbor ``tests/test.sh`` in ``aces_plus_custom`` mode, so the
ported CLI tasks need a Python grader that invokes the original pytest verifier.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(os.environ.get("HARBOR_TESTS_DIR", "/tests"))
VERIFIER_LOG_DIR = Path(os.environ.get("HARBOR_VERIFIER_DIR", "/logs/verifier"))
REWARD_JSON = VERIFIER_LOG_DIR / "reward.json"
PYTEST_TIMEOUT_SEC = int(os.environ.get("EVALUATOR_CLI_PYTEST_TIMEOUT_SEC", "300"))


def main() -> None:
    VERIFIER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    test_file = TESTS_DIR / "test_outputs.py"
    if not test_file.is_file():
        _write_reward(
            passed=False,
            details={"reason": f"Missing pytest verifier at {test_file}"},
        )
        return

    env = os.environ.copy()
    env.setdefault("NMP_BASE_URL", "http://localhost:8080")
    py_paths = [
        str(TESTS_DIR),
        str(TESTS_DIR / "shared"),
        "/app/tests/agentic-use/shared",
        "/app/packages/nemo_evaluator_sdk/src",
        env.get("PYTHONPATH", ""),
    ]
    env["PYTHONPATH"] = os.pathsep.join(path for path in py_paths if path)

    command = [sys.executable, "-m", "pytest", str(test_file), "-rA", "-v"]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            cwd=TESTS_DIR,
            env=env,
            timeout=PYTEST_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(
            args=exc.cmd or command,
            returncode=124,
            stdout=_timeout_text(exc.stdout),
            stderr=_timeout_text(exc.stderr, fallback="pytest verifier timed out"),
        )

    (VERIFIER_LOG_DIR / "pytest_stdout.txt").write_text(result.stdout, encoding="utf-8")
    (VERIFIER_LOG_DIR / "pytest_stderr.txt").write_text(result.stderr, encoding="utf-8")
    _write_reward(
        passed=result.returncode == 0,
        details={
            "pytest": {
                "command": command,
                "returncode": result.returncode,
                "stdout_path": "pytest_stdout.txt",
                "stderr_path": "pytest_stderr.txt",
            }
        },
    )


def _write_reward(*, passed: bool, details: dict[str, object]) -> None:
    REWARD_JSON.write_text(
        json.dumps(
            {
                "custom_metrics": {
                    "evaluator_pytest_verifier_pass": float(passed),
                },
                "details": details,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _timeout_text(value: str | bytes | None, *, fallback: str = "") -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return fallback


if __name__ == "__main__":
    main()
