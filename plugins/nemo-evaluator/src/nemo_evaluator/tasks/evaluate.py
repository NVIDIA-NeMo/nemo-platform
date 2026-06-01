# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Container entrypoint for evaluator plugin bundle-native jobs."""

from __future__ import annotations

from nemo_evaluator.jobs.evaluate import EvaluateJob
from nemo_platform_plugin.tasks.dispatcher import run_task
from nmp.common.sdk_factory import get_task_sdk


def main() -> int:
    """Run the evaluator job in a platform-spawned task process."""
    return run_task(EvaluateJob, sdk=get_task_sdk("evaluator"))


if __name__ == "__main__":
    raise SystemExit(main())
