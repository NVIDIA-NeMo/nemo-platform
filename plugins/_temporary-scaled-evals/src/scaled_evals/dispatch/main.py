# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI entrypoint for the durable evaluation dispatch worker."""

from __future__ import annotations

import logging
import os

from scaled_evals.dispatch.worker import Dispatcher


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    if evaluation_id := os.getenv("SCALED_EVALS_EVALUATION_ID"):
        execution_number = int(os.getenv("SCALED_EVALS_EXECUTION_NUMBER", "1"))
        Dispatcher().run(
            evaluation_id,
            expected_execution_number=execution_number,
        )
        return
    idle_sleep = float(os.getenv("DISPATCH_WORKER_IDLE_SLEEP_SECONDS", "2"))
    Dispatcher().work_forever(idle_sleep=idle_sleep)


if __name__ == "__main__":
    main()
