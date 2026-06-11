# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Default entrypoint for the nmp-automodel-tasks image (help / task listing).

Production job steps invoke a specific module directly, e.g.
``python -m nmp.automodel.tasks.file_io``.
"""

from __future__ import annotations

import argparse
import sys

_TASK_MODULES = (
    ("file_io", "nmp.automodel.tasks.file_io", "Download/upload model and dataset files"),
    ("model_entity", "nmp.automodel.tasks.model_entity", "Create output model entity"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m nmp.automodel.tasks",
        description="NeMo Automodel CPU task image. The jobs compiler runs one module per step.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  python -m nmp.automodel.tasks --help\n"
        "  python -m nmp.automodel.tasks.file_io\n"
        "  python -m nmp.automodel.tasks.model_entity\n\n"
        "GPU training uses the nmp-automodel-training image:\n"
        "  python -m nmp.automodel.tasks.training\n",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List task modules and exit (default when no job config is provided).",
    )
    args = parser.parse_args(argv)
    if args.list or len(argv or sys.argv[1:]) == 0:
        print("Task modules:\n")
        for name, module, summary in _TASK_MODULES:
            print(f"  {name:14}  {module}")
            print(f"                  {summary}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
