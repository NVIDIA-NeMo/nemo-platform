# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local ClickHouse lifecycle sidecar for ``nemo services`` source checkouts."""

import subprocess
import threading
from pathlib import Path

_SCRIPT = Path("services/intake/scripts/spans/run_clickhouse.sh")


def _find_start_script() -> Path:
    for start in (Path.cwd().resolve(), Path(__file__).resolve()):
        for candidate in (start, *start.parents):
            script = candidate / _SCRIPT
            if script.is_file():
                return script
    raise RuntimeError(
        f"The Intake ClickHouse sidecar requires a NeMo Platform source checkout; could not find {_SCRIPT}"
    )


def run(stop_signal: threading.Event) -> None:
    """Ensure the persistent local ClickHouse container is running."""
    script = _find_start_script()
    completed = subprocess.run([str(script)], check=False)  # noqa: S603
    if completed.returncode != 0:
        raise RuntimeError(f"Could not start Intake ClickHouse with {script}")
    stop_signal.wait()
