# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI entrypoint for the durable task image build worker."""

from __future__ import annotations

import logging
import os

from scaled_evals.api.build.queue_worker import TaskBuildWorker


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    TaskBuildWorker(
        claim_timeout=float(os.getenv("BUILD_WORKER_CLAIM_TIMEOUT_SECONDS", "90")),
        heartbeat_interval=float(os.getenv("BUILD_WORKER_HEARTBEAT_SECONDS", "15")),
        max_attempts=int(os.getenv("BUILD_WORKER_MAX_ATTEMPTS", "3")),
        retry_delay=float(os.getenv("BUILD_WORKER_RETRY_DELAY_SECONDS", "30")),
    ).work_forever(idle_sleep=float(os.getenv("BUILD_WORKER_IDLE_SLEEP_SECONDS", "2")))


if __name__ == "__main__":
    main()
