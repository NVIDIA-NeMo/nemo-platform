# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared Ctrl-C handling for the walkthrough quick-start CLI."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents import AgentProcess

INTERRUPT_POLL_SEC = 0.1


class WalkthroughInterrupted(Exception):
    """The operator interrupted the walkthrough with Ctrl-C."""

    def __init__(self, *, phase: str | None = None) -> None:
        self.phase = phase
        super().__init__(phase or "interrupted")


def interruptible_sleep(seconds: float) -> None:
    """Sleep in short slices so Ctrl-C is felt quickly."""
    if seconds <= 0:
        return
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(INTERRUPT_POLL_SEC, remaining))


def terminate_agent(agent: AgentProcess | None) -> None:
    """Stop a background coding-agent subprocess when present."""
    if agent is not None:
        agent.terminate()


def interrupt_message(*, phase: str | None = None) -> str:
    """Return a single-line status message for Ctrl-C."""
    if phase:
        return f"Interrupted during {phase}."
    return "Interrupted."
