# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse the shared Harbor and remote-Harbor entrypoint contract."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--trace-path", type=Path, default=Path("/app/traces/trace.jsonl"))
    return parser.parse_args()


def prompt_from_args(args: argparse.Namespace) -> str:
    return args.prompt_file.read_text(encoding="utf-8")


if __name__ == "__main__":
    args = parse_args()
    os.environ["TRACE_DIR"] = str(args.trace_path.parent)
    from agent import Codeact  # noqa: PLC0415

    agent = Codeact()
    asyncio.run(agent.solve(prompt_from_args(args)))
