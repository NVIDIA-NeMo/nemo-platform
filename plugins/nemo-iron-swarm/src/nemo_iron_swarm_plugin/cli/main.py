# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``nemo iron-swarm ...`` — registered under ``nemo.cli``.

Wiring only: the commands live in sibling modules grouped by what they act on — :mod:`lifecycle`
(host provisioning and the saved target), :mod:`war_game` (the attack/defend/validate cycle), and
:mod:`manifest` (a saved manifest's stored defaults). Shared preamble and option parsing are in
:mod:`_shared`; each command's docstring is its ``--help`` text.
"""

from __future__ import annotations

import typer
from nemo_iron_swarm_plugin.cli import lifecycle, manifest, war_game
from nemo_platform_plugin.cli import NemoCLI


class IronSwarmCLI(NemoCLI):
    """Exposes plugin commands as ``nemo iron-swarm ...``."""

    name = "iron-swarm"
    description = "Red-team and harden deployed NAT agents with Iron Swarm."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True, add_completion=False)
        lifecycle.register(app)
        war_game.register(app)
        app.add_typer(manifest.build_app(), name="manifest")
        return app
