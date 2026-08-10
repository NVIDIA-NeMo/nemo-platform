# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
import json
from pathlib import Path

from agent import solve
from tracing import setup_tracing


async def _run(prompt: str, trace_path: Path, summary_path: Path) -> None:
    provider = setup_tracing(trace_path)
    summary: dict[str, object] = {}
    try:
        answer, usage = await solve(prompt)
        summary = {"answer": answer, "usage": usage}
        print(answer)
    finally:
        provider.force_flush(timeout_millis=5_000)
        provider.shutdown()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    """Run one Terminal-Bench instruction."""
    parser = argparse.ArgumentParser()
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt")
    prompt_group.add_argument("--prompt-file", type=Path)
    parser.add_argument("--trace-path", type=Path, default=Path("/logs/artifacts/traces/trace.jsonl"))
    parser.add_argument("--summary-path", type=Path, default=Path("/logs/agent/summary.json"))
    args = parser.parse_args()

    prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8")
    asyncio.run(_run(prompt, args.trace_path, args.summary_path))


if __name__ == "__main__":
    main()
