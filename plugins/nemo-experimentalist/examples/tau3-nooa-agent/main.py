# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
import json
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Accept both direct and Harbor bridge invocation contracts."""
    parser = argparse.ArgumentParser()
    prompt_source = parser.add_mutually_exclusive_group(required=True)
    prompt_source.add_argument("--prompt", type=str)
    prompt_source.add_argument("--prompt-file", type=Path)
    # The bridge supplies these standard artifact paths. Codeact already writes
    # traces below /app/traces; accepting the paths keeps this entrypoint
    # compatible with the evaluator contract.
    parser.add_argument("--trace-path", type=Path)
    parser.add_argument("--summary-path", type=Path)
    return parser.parse_args()


def prompt_from_args(args: argparse.Namespace) -> str:
    if args.prompt_file is not None:
        return args.prompt_file.read_text(encoding="utf-8")
    return args.prompt


if __name__ == "__main__":
    args = parse_args()
    if args.trace_path is not None:
        os.environ["TRACE_DIR"] = str(args.trace_path.parent)
    from agent import Codeact  # noqa: PLC0415

    agent = Codeact()
    asyncio.run(agent.solve(prompt_from_args(args)))
    if args.summary_path is not None:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(json.dumps({}), encoding="utf-8")
