# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio

from agent import Codeact, ConversationEnded


async def run(prompt: str) -> None:
    agent = Codeact()
    try:
        await agent.solve(prompt)
    except ConversationEnded:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, required=True)
    args = parser.parse_args()

    asyncio.run(run(args.prompt))
