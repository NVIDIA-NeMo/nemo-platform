# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
import threading
from pathlib import Path

import pytest
from nmp.intake.sidecars import clickhouse


def test_clickhouse_sidecar_starts_then_waits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = tmp_path / "run_clickhouse.sh"
    script.touch()
    stop_signal = threading.Event()
    calls: list[list[str]] = []

    monkeypatch.setattr(clickhouse, "_find_start_script", lambda: script)
    monkeypatch.setattr(
        clickhouse.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(argv) or subprocess.CompletedProcess(argv, returncode=0),
    )
    stop_signal.set()

    clickhouse.run(stop_signal)

    assert calls == [[str(script)]]


def test_clickhouse_sidecar_surfaces_start_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = tmp_path / "run_clickhouse.sh"
    script.touch()
    monkeypatch.setattr(clickhouse, "_find_start_script", lambda: script)
    monkeypatch.setattr(
        clickhouse.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, returncode=1),
    )

    with pytest.raises(RuntimeError, match="Could not start Intake ClickHouse"):
        clickhouse.run(threading.Event())
