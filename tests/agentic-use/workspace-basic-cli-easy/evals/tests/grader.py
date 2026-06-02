#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run the NeMo Platform pytest verifier as an ACES custom metric."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LOG_DIR = Path("/logs/verifier")
REWARD_JSON = LOG_DIR / "reward.json"
REWARD_TXT = LOG_DIR / "reward.txt"
PYTEST_LOG = LOG_DIR / "nemo_workspace_pytest.log"


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["/app/.venv/bin/python", "-m", "pytest", "/tests/test_outputs.py", "-rA"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    PYTEST_LOG.write_text(
        f"$ /app/.venv/bin/python -m pytest /tests/test_outputs.py -rA\n"
        f"exit_code={result.returncode}\n\n"
        f"--- stdout ---\n{result.stdout}\n\n"
        f"--- stderr ---\n{result.stderr}\n",
        encoding="utf-8",
    )

    score = 1.0 if result.returncode == 0 else 0.0
    reward = {
        "overall": score,
        "custom_metrics": {
            "nemo_workspace_pytest": score,
        },
        "details": {
            "nemo_workspace_pytest": {
                "score": score,
                "reason": (
                    "Pytest verifier confirmed the expected NeMo workspace state."
                    if score == 1.0
                    else "Pytest verifier failed; see /logs/verifier/nemo_workspace_pytest.log."
                ),
                "exit_code": result.returncode,
                "log": str(PYTEST_LOG),
            },
        },
    }
    REWARD_JSON.write_text(json.dumps(reward, indent=2), encoding="utf-8")
    REWARD_TXT.write_text(str(score), encoding="utf-8")


if __name__ == "__main__":
    main()
