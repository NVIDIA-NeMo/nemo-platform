# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Container entrypoint for evaluator plugin bundle-native jobs."""

from __future__ import annotations

import logging
import signal
import sys
from enum import IntEnum
from types import FrameType

from nemo_evaluator.jobs.evaluate import EvaluateJob
from nemo_platform_plugin.tasks.dispatcher import run_task
from nmp.common.sdk_factory import get_task_sdk

logger = logging.getLogger(__name__)


class EvaluateTaskExitCode(IntEnum):
    """Evaluator task setup exit codes."""

    SDK_INITIALIZATION_FAILED = 2


def _shutdown_handler(signum: int, frame: FrameType | None) -> None:
    logger.warning("Received shutdown signal (%d). Exiting.", signum)
    raise SystemExit(128 + signum)


def main() -> int:
    """Build the task SDK and dispatch to the evaluator plugin job."""
    signal.signal(signal.SIGTERM, _shutdown_handler)
    try:
        sdk = get_task_sdk("evaluator")
    except Exception:
        logger.exception("Failed to build task SDK for evaluator")
        return EvaluateTaskExitCode.SDK_INITIALIZATION_FAILED
    return run_task(EvaluateJob, sdk=sdk)


if __name__ == "__main__":
    sys.exit(main())
