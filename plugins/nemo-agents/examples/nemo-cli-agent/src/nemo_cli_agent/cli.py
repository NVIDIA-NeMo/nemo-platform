# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``nemo ask`` shortcut for the nemo-cli-agent example.

Plugins cannot directly add root-level commands to the NeMo CLI; the
platform always mounts plugin contributions as top-level groups under
``nemo <entry-point-name>``. Registering this class under
``nemo.cli -> ask`` therefore creates the group ``nemo ask``, and we use
``invoke_without_command=True`` plus a callback positional argument so the
group behaves like a one-shot command from the user's perspective —
``nemo ask "list my workspaces"``.

The shortcut just dispatches to ``_local_invoke`` from the agents plugin
against the bundled ``nemo-cli-agent.yml``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

import typer
from nemo_platform_plugin.cli import NemoCLI

# Heavy imports (``nemo_cli_agent.agent``, ``nemo_agents_plugin.cli``,
# and transitively langgraph/langchain) are deferred to the ``ask``
# callback so the ``nemo`` CLI's entry-point discovery — which imports
# *this* module just to learn the command name — doesn't pull in the
# whole agent stack on every ``nemo`` invocation.


def _agent_config_path() -> Path:
    """Locate the bundled nemo-cli-agent NAT config."""
    # Resolves to ``examples/nemo-cli-agent`` from the source tree (and the
    # equivalent location in installed wheels via the hatch package layout).
    package_dir = Path(__file__).resolve().parent
    candidates = (
        package_dir / "nemo-cli-agent.yml",
        package_dir.parent.parent / "nemo-cli-agent.yml",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("nemo-cli-agent.yml not found. Tried: " + ", ".join(str(c) for c in candidates))


class AskCLI(NemoCLI):
    """``nemo ask "<question>"`` — shortcut for the nemo-cli-agent example."""

    name: ClassVar[str] = "ask"
    description: ClassVar[str] = "Ask the NeMo CLI agent (shortcut for the nemo-cli-agent example)."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(
            name=self.name,
            help=self.description,
            invoke_without_command=True,
            no_args_is_help=False,
            add_completion=False,
        )

        @app.callback(invoke_without_command=True)
        def ask(
            ctx: typer.Context,
            question: str = typer.Argument(..., help="Question for the NeMo CLI agent."),
            verbose: bool = typer.Option(
                False,
                "--verbose",
                "-v",
                help="Print the rendered system prompt (including the loaded skills catalog) before answering.",
            ),
        ) -> None:
            """Ask the NeMo CLI agent a question."""
            if ctx.invoked_subcommand is not None:
                return

            # Toggle the agent-side debug middleware via env var so the
            # flag flows through ``_local_invoke`` / NAT without needing
            # to widen its public signature.
            if verbose:
                from nemo_cli_agent.agent import VERBOSE_ENV_VAR

                os.environ[VERBOSE_ENV_VAR] = "1"

            from nemo_agents_plugin.cli import _local_invoke

            _local_invoke(_agent_config_path(), input=question, input_file=None)

        return app
