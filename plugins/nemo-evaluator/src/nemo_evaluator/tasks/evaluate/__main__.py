# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task entrypoint for the evaluator plugin evaluate job."""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

from nemo_evaluator.jobs.evaluate import EvaluateJob
from nemo_platform_plugin.tasks.dispatcher import run_task
from nmp.common.sdk_factory import get_task_sdk

logger = logging.getLogger(__name__)


def _shutdown_handler(signum: int, frame: FrameType | None) -> None:
    del frame
    logger.warning("Received shutdown signal (%d). Exiting.", signum)
    raise SystemExit(128 + signum)


def main() -> int:
    signal.signal(signal.SIGTERM, _shutdown_handler)
    try:
        sdk = get_task_sdk("evaluator")
    except Exception:
        logger.exception("Failed to build task SDK for evaluator")
        return 2
    return run_task(EvaluateJob, sdk=sdk)


if __name__ == "__main__":
    sys.exit(main())
