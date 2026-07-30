# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The agent under optimization.

Deliberately simple and deterministic: no LLM, no network, standard library
only. The Experimentalist treats this file as the thing to mutate, so what
matters is that it has an obvious capability gap (it can greet, but it cannot do
arithmetic) for the loop to discover and close.
"""

from __future__ import annotations

import re

GREETING_RE = re.compile(r"\bhello,\s*([A-Za-z0-9 _-]+)!", re.IGNORECASE)

FALLBACK = "I do not know how to answer that."


class HelloAgent:
    """Route a task instruction to a handler and return the answer line."""

    def solve(self, instruction: str) -> str:
        """Return the single output line this agent believes the task wants.

        Args:
            instruction: The full task instruction text.

        Returns:
            The answer line to write to the output file.
        """
        # Intentionally a one-element tuple: the arithmetic gap this leaves is the
        # example's whole point, and adding a `handle_sum` node here is precisely
        # the round-1 improvement the Proposer and Coder are supposed to discover.
        # Do not "fix" the baseline — see README.md, "The deliberate capability gap".
        for handler in (self.handle_greeting,):
            answer = handler(instruction)
            if answer is not None:
                return answer
        return FALLBACK

    def handle_greeting(self, instruction: str) -> str | None:
        """Echo back a `Hello, <target>!` line quoted in the instruction.

        Args:
            instruction: The full task instruction text.

        Returns:
            The greeting line, or None when the instruction is not a greeting task.
        """
        match = GREETING_RE.search(instruction)
        if match is None:
            return None
        return f"Hello, {match.group(1).strip()}!"
