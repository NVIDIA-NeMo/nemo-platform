# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin manifest — lightweight identity record derived by the platform."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PluginManifest:
    """Lightweight identity record for an installed NeMo Platform plugin.

    The platform derives one manifest per installed plugin by scanning all
    known surface entry-point groups (``nemo.services``, ``nemo.cli``, etc.).
    Plugin authors do **not** declare this — it is assembled automatically
    from the installing distribution's package metadata.

    Attributes:
        name: Entry-point key (e.g. ``"example"``).
        version: Distribution ``Version`` field, or ``""`` if unavailable.
        description: Distribution ``Summary`` field, or ``""`` if unavailable.
        surfaces: Sorted list of surface labels this plugin contributes to
            (e.g. ``["cli", "mcp", "service"]``).
    """

    name: str
    version: str
    description: str = field(default="")
    surfaces: list[str] = field(default_factory=list)
