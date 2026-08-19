# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
from pathlib import Path

from agent import solve
from tracing import setup_tracing


async def _run(prompt: str, trace_path: Path) -> None:
    provider = setup_tracing(trace_path)
    try:
        answer, _usage = await solve(prompt)
        print(answer)
    finally:
        provider.force_flush(timeout_millis=5_000)
        provider.shutdown()


def main() -> None:
    """Run one Terminal-Bench instruction."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--trace-path", type=Path, default=Path("/app/traces/trace.jsonl"))
    args = parser.parse_args()

    prompt = args.prompt_file.read_text(encoding="utf-8")
    asyncio.run(_run(prompt, args.trace_path))


if __name__ == "__main__":
    main()
