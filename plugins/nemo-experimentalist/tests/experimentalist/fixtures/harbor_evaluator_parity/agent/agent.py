# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The deterministic agent used by the Harbor parity fixture."""

from __future__ import annotations

import re

GREETING_RE = re.compile(r"\bhello,\s*([A-Za-z0-9 _-]+)!", re.IGNORECASE)
FALLBACK = "I do not know how to answer that."


class HelloAgent:
    """Route a task instruction to a handler and return the answer line."""

    def solve(self, instruction: str) -> str:
        answer = self.handle_greeting(instruction)
        return answer if answer is not None else FALLBACK

    def handle_greeting(self, instruction: str) -> str | None:
        """Echo a ``Hello, <target>!`` line quoted in the instruction."""
        match = GREETING_RE.search(instruction)
        if match is None:
            return None
        return f"Hello, {match.group(1).strip()}!"
