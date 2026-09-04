# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("scaled_evals")

from scaled_evals.api.build import main


def test_main_configures_and_starts_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("BUILD_WORKER_CLAIM_TIMEOUT_SECONDS", "120.5")
    monkeypatch.setenv("BUILD_WORKER_HEARTBEAT_SECONDS", "20")
    monkeypatch.setenv("BUILD_WORKER_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("BUILD_WORKER_RETRY_DELAY_SECONDS", "45.5")
    monkeypatch.setenv("BUILD_WORKER_IDLE_SLEEP_SECONDS", "3.5")
    worker = MagicMock()
    factory = MagicMock(return_value=worker)
    monkeypatch.setattr(main, "TaskBuildWorker", factory)
    basic_config = MagicMock()
    monkeypatch.setattr(main.logging, "basicConfig", basic_config)

    main.main()

    basic_config.assert_called_once_with(level="DEBUG")
    factory.assert_called_once_with(
        claim_timeout=120.5,
        heartbeat_interval=20.0,
        max_attempts=5,
        retry_delay=45.5,
    )
    worker.work_forever.assert_called_once_with(idle_sleep=3.5)
