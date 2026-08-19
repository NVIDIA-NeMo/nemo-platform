# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Container entry point: solve one task and write the answer line."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", "/app/artifacts"))
OUTPUT_PATH = ARTIFACTS_DIR / "output.txt"


def parse_args() -> argparse.Namespace:
    """Parse the shared Harbor and remote-Harbor entrypoint contract."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--trace-path", type=Path, default=Path("/app/traces/trace.jsonl"))
    return parser.parse_args()


def prompt_from_args(args: argparse.Namespace) -> str:
    return args.prompt_file.read_text(encoding="utf-8")


def main() -> None:
    """Run one prompt and write the task result."""

    args = parse_args()
    os.environ["TRACE_DIR"] = str(args.trace_path.parent)

    # Import only after TRACE_DIR is set: agent.py configures the JSONL exporter
    # at import time.
    from agent import ReportAgent  # noqa: PLC0415

    answer = ReportAgent().solve(prompt_from_args(args))

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(answer + "\n", encoding="utf-8")
    print(f"answer={answer!r} output={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
