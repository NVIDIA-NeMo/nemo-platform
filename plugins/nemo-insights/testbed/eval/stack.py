# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Self-contained Intake stack (ClickHouse + auth, entities, intake on :8080).

State lives under $RUNNER_TEMP/state.
`--verify` only re-checks both health endpoints and writes the summary line.
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[4]


def _wait(url: str, attempts: int, delay: float) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=5):
                return True
        except OSError:
            time.sleep(delay)
    return False


def _fail_with_log(log: Path, message: str) -> None:
    print(message)
    if log.exists():
        print("".join(log.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-50:]))
    sys.exit(1)


def verify() -> None:
    for url in ("http://localhost:8123/ping", "http://localhost:8080/health/ready"):
        if not _wait(url, attempts=1, delay=0):
            sys.exit(f"verify failed: {url}")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
        fh.write("### stack-check ✓ ClickHouse + platform ready\n")


def main() -> None:
    if "--verify" in sys.argv[1:]:
        verify()
        return
    runner_temp = Path(os.environ["RUNNER_TEMP"])
    state = runner_temp / "state"
    (state / "clickhouse").mkdir(parents=True, exist_ok=True)
    (state / "nmp").mkdir(parents=True, exist_ok=True)
    log = runner_temp / "platform.log"

    subprocess.run(
        [str(PLATFORM_ROOT / "services/intake/scripts/spans/run_clickhouse.sh")],
        check=True,
        env={**os.environ, "CLICKHOUSE_DATA_DIR": str(state / "clickhouse")},
    )
    if not _wait("http://localhost:8123/ping", attempts=30, delay=2):
        sys.exit("ClickHouse never became ready")
    subprocess.run(
        ["docker", "exec", "nmp-intake-clickhouse", "clickhouse-client", "--query", "SYSTEM STOP TTL MERGES"],
        check=True,
    )

    subprocess.run(["uv", "sync"], check=True, cwd=PLATFORM_ROOT)
    with open(log, "ab") as fh:
        subprocess.Popen(
            [
                "uv",
                "run",
                "nemo",
                "services",
                "run",
                "--services",
                "auth,entities,intake",
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
            ],
            cwd=PLATFORM_ROOT,
            env={**os.environ, "NMP_DATA_DIR": str(state / "nmp")},
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    if not _wait("http://localhost:8080/health/ready", attempts=60, delay=5):
        _fail_with_log(log, "platform never became ready; last log lines:")


if __name__ == "__main__":
    main()
