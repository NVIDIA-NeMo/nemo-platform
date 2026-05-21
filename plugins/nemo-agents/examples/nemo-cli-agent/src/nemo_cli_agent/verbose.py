# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Opt-in middleware that dumps the rendered system prompt.

Isolated from :mod:`nemo_cli_agent.utils` so the ``from
langchain.agents.middleware.types import AgentMiddleware`` import stays out
of the entry-point load path. ``utils`` is imported by NAT at startup
(it registers the workflow type), and pulling ``langchain.agents`` in
there transitively imports ``langgraph`` *before* any of our warning
filters run, which is what re-introduced the
``LangChainPendingDeprecationWarning`` chatter on every ``nemo ask``.

This module is imported only when ``--verbose`` is set, so the default
``nemo ask`` path never touches ``langchain.agents``.
"""

from __future__ import annotations

from typing import Any

# Importing ``langchain.agents.middleware.types`` here pulls in
# ``langgraph.checkpoint.serde.encrypted`` for the first time on the
# ``--verbose`` path, which emits a one-shot
# ``LangChainPendingDeprecationWarning``. We deliberately don't try to
# silence it: ``langchain_core``'s import-time
# ``surface_langchain_deprecation_warnings`` re-enables the category
# *after* any filter we set here, so suppression would require ugly
# stderr/fd workarounds. ``--verbose`` is a debug mode and the single
# benign warning is an acceptable trade-off for keeping the default
# (non-verbose) ``nemo ask`` path warning-free.
from langchain.agents.middleware.types import AgentMiddleware
from rich.console import Console
from rich.panel import Panel

_console = Console()


def _print_system_prompt(system_message: Any) -> None:
    """Render the final system prompt (post-middleware) to the local console.

    Used by :class:`SystemPromptDumpMiddleware` so the operator can
    confirm that skills (and any other middleware-injected context)
    actually reached the model.
    """
    if system_message is None:
        text = "(no system message)"
    elif isinstance(system_message, str):
        text = system_message
    else:
        # Cover both ``SystemMessage`` and any other LangChain message
        # shape that exposes ``.text`` or string-coercible ``.content``.
        text = getattr(system_message, "text", None)
        if not text:
            content = getattr(system_message, "content", system_message)
            text = content if isinstance(content, str) else str(content)
    _console.print()
    _console.print(Panel(text, title="system prompt", border_style="magenta", expand=False))


class SystemPromptDumpMiddleware(AgentMiddleware):
    """Print the post-middleware system prompt once per agent run.

    DeepAgents' ``SkillsMiddleware`` injects the skill catalog into the
    system message via ``modify_request`` / ``wrap_model_call``;
    inserting this middleware *after* the SkillsMiddleware in the stack
    therefore lets us see the exact string the model receives, including
    the ``Available Skills:`` block, before the first model call.
    """

    def __init__(self) -> None:
        super().__init__()
        self._dumped = False

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        if not self._dumped:
            self._dumped = True
            _print_system_prompt(getattr(request, "system_message", None))
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        if not self._dumped:
            self._dumped = True
            _print_system_prompt(getattr(request, "system_message", None))
        return await handler(request)
