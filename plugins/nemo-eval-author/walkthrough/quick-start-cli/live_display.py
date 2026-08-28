# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live terminal layout for walkthrough workspace tables and agent output."""

from __future__ import annotations

import sys
import time
from collections import deque
from collections.abc import Iterable
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from display import AgentProfile
    from rich.console import Console

DEFAULT_AGENT_LOG_LINES = 10
SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class AgentLogPane:
    """Bounded scrolling buffer rendered as a bottom terminal panel."""

    def __init__(self, label: str, *, max_lines: int = DEFAULT_AGENT_LOG_LINES) -> None:
        self.label = label
        self.max_lines = max_lines
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._activity: str | None = None

    def append(self, line: str) -> None:
        self._lines.append(line)

    def extend(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.append(line)

    def set_activity(self, activity: str | None) -> None:
        self._activity = activity

    def render(self, *, pulse: int = 0) -> Panel:
        body_parts: list[RenderableType] = []
        if self._activity:
            frame = SPINNER_FRAMES[pulse % len(SPINNER_FRAMES)]
            body_parts.append(Text.assemble((frame + " ", "cyan"), (self._activity, "bold cyan")))
        if self._lines:
            body_parts.append(Text("\n").join(Text.from_markup(line) for line in self._lines))
        elif not self._activity:
            body = Text("Waiting for agent activity…", style="dim")
            return Panel(body, title=f"[cyan]{self.label}[/]", border_style="cyan", height=self.max_lines + 2)

        body: RenderableType = Group(*body_parts) if len(body_parts) > 1 else body_parts[0]
        return Panel(
            body,
            title=f"[cyan]{self.label}[/]",
            border_style="cyan",
            height=self.max_lines + 2,
        )


class WalkthroughLiveDisplay:
    """Refresh workspace tables in place and keep agent output in a bottom log pane."""

    def __init__(
        self,
        console: Console,
        profile: AgentProfile,
        *,
        agent_label: str,
        max_agent_lines: int = DEFAULT_AGENT_LOG_LINES,
        refresh_per_second: float = 4.0,
    ) -> None:
        self.console = console
        self.profile = profile
        self._agent = AgentLogPane(agent_label, max_lines=max_agent_lines)
        self._main: RenderableType = Text("Waiting for workspace artifacts…", style="dim")
        self._live: Live | None = None
        self._refresh_per_second = refresh_per_second
        self._started_at = time.monotonic()
        self._pulse = 0

    def __enter__(self) -> WalkthroughLiveDisplay:
        self._live = Live(
            self._compose(),
            console=self.console,
            refresh_per_second=self._refresh_per_second,
            transient=True,
            screen=True,
            auto_refresh=True,
        )
        self._live.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._live is not None:
            self._live.__exit__(exc_type, exc, tb)
            self._live = None

    @property
    def pulse(self) -> int:
        elapsed = time.monotonic() - self._started_at
        return int(elapsed * self._refresh_per_second)

    def _compose(self) -> Group:
        self._pulse = self.pulse
        return Group(self._main, self._agent.render(pulse=self._pulse))

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._compose())

    def set_main(self, renderable: RenderableType) -> None:
        self._main = renderable
        self._refresh()

    def set_agent_activity(self, activity: str | None) -> None:
        self._agent.set_activity(activity)
        self._refresh()

    def append_agent(self, line: str) -> None:
        self._agent.append(line)
        self._refresh()

    def extend_agent(self, lines: Iterable[str]) -> None:
        self._agent.extend(lines)
        self._refresh()

    def touch(self) -> None:
        """Force a visual refresh so spinners and progress bars animate."""
        self._refresh()

    def hold_until_enter(self, *, message: str = "Press ENTER to exit.") -> None:
        """Keep the final frame visible until the operator dismisses it."""
        self._agent.set_activity(None)
        if self._live is not None:
            self._live.transient = False
            self._refresh()
        if not sys.stdin.isatty():
            return
        try:
            input(f"\n{message}")
        except EOFError:
            return
