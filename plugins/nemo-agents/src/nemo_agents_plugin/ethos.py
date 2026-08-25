# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lightweight ETHOS.md contract.

Ethos is a human-readable markdown file stored locally at
``agents/<name>-ethos/ETHOS.md`` and canonically in Filesets as
``<workspace>/<name>-ethos#ETHOS.md``.

Only the front matter and section outline are machine-validated here. The
section bodies remain markdown for humans and agents to read directly.

Schema version 2 trades description for intent. It adds how to weigh competing
wins (``Trade-offs``), what no change may cross (``Constraints``), how to decide
when no rule covers the case (``Principles``), what the telemetry actually means
(``Metric Semantics``), and where the agent is headed (``Vision``). It merges
version 1's ``Purpose`` with the outcome the agent is accountable for into
``Purpose & Outcomes``, so mission and measurable result are stated together
instead of drifting apart in two sections.

Version 2 is also smaller than version 1, because a section nothing consumes is
worse than a missing one: it trains readers to skim. Four sections came out.

- ``Framework`` had no reader at all, and the container's framework label comes
  from ``agent.yaml``. Its one useful datum moved to ``Harness``.
- ``Model`` restated implementation the config already carries and went stale on
  the first model swap. Which models are *allowed* is a ``Constraints`` entry;
  whether the loop may swap them is a ``Change Scope`` lever.
- ``Signals`` was a single consumer's configuration wearing a schema section.
  The Analyst now carries its own evidence defaults.
- ``Purpose`` merged into ``Purpose & Outcomes``.

The same rule retired a drafted ``Budget`` section before it shipped: anything
that only configures one optimization run belongs to the tool running it, or
this file becomes a dumping ground that rots between runs.

Version 1 keeps every section it ever had, including the ``Framework``
resolution gate. Tiering is what makes that affordable: version 1 required all
thirteen of its sections, which made every schema change breaking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

ETHOS_SCHEMA_VERSION = 2
"""Schema version written by current tooling."""

ETHOS_V1_SECTION_TITLES: tuple[str, ...] = (
    "Role",
    "Purpose",
    "Scope",
    "Tools",
    "Model",
    "Framework",
    "Harness",
    "Behavior",
    "Success Criteria",
    "Evaluation Setup",
    "Change Scope",
    "Signals",
    "Open Questions",
)
"""Version 1 sections. All were required; kept so v1 files still parse."""

CORE_SECTION_TITLES: tuple[str, ...] = (
    "Role",
    "Purpose & Outcomes",
    "Scope",
    "Tools",
    "Behavior",
    "Success Criteria",
    "Change Scope",
)
"""Version 2 core tier: what the agent is. Missing one is an error."""

INTENT_SECTION_TITLES: tuple[str, ...] = (
    "Principles",
    "Trade-offs",
    "Constraints",
    "Evaluation Setup",
)
"""Version 2 intent tier: what winning means and what bounds the search.

Missing one is a warning, or an error under ``strict``. An optimizer that
cannot read these is guessing at the developer's intent.
"""

OPTIONAL_SECTION_TITLES: tuple[str, ...] = (
    "Harness",
    "Metric Semantics",
    "Vision",
    "Open Questions",
)
"""Version 2 optional tier: valuable when present, safe to omit."""

ETHOS_SECTION_TITLES: tuple[str, ...] = (
    "Role",
    "Purpose & Outcomes",
    "Scope",
    "Tools",
    "Harness",
    "Behavior",
    "Principles",
    "Success Criteria",
    "Trade-offs",
    "Constraints",
    "Evaluation Setup",
    "Metric Semantics",
    "Change Scope",
    "Vision",
    "Open Questions",
)
"""Every version 2 ``##`` heading, in canonical reading order.

The order tells a story: who the agent is, what it is today, how to judge it,
what may change, and where it is going. ``Principles`` follows ``Behavior``
because the pair reads as the concrete rules and then what to do when the rules
run out. ``Vision`` follows ``Change Scope`` so today's permissions and
tomorrow's direction sit together.
"""

RETIRED_SECTION_TITLES: tuple[str, ...] = ("Framework", "Model", "Signals", "Purpose")
"""Version 1 sections with no version 2 equivalent, kept for recognition only.

A file mid-upgrade may still carry these. The parser neither requires nor
rejects them, so they survive in :attr:`Ethos.sections` for a human to read
while nothing downstream is asked to interpret them.
"""

CHANGE_SCOPE_LEVER_VALUES: tuple[str, ...] = ("yes", "no", "with-approval")
"""Recognized ``Change Scope`` lever values.

``with-approval`` is new in version 2. Version 1 offered only yes or no, which
pushed every conditional permission into the section's prose ``Notes`` line
where no consumer could act on it.
"""

_LEVER_RE = re.compile(r"^-\s*([^:]+?)\s*:\s*(.+?)\s*$", re.MULTILINE)


def required_sections(version: int) -> tuple[str, ...]:
    """Sections that must be present for ``version`` to parse at all."""
    return ETHOS_V1_SECTION_TITLES if version < 2 else CORE_SECTION_TITLES


def known_sections(version: int) -> tuple[str, ...]:
    """Every section ``version`` defines, in canonical order."""
    return ETHOS_V1_SECTION_TITLES if version < 2 else ETHOS_SECTION_TITLES


@dataclass(frozen=True)
class Ethos:
    """Parsed ETHOS.md document.

    ``sections`` stores raw markdown by heading title. Downstream agents should
    read that markdown rather than relying on a bespoke nested Python schema.
    """

    name: str
    created_timestamp: datetime
    author: str
    sections: dict[str, str]
    schema_version: int = 1
    updated_timestamp: datetime | None = None
    owner: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def role(self) -> str:
        return self.sections["Role"]

    @property
    def change_scope_levers(self) -> dict[str, str]:
        """``Change Scope`` levers whose value is a recognized permission.

        Lenient by design: the section body is free-form markdown in practice,
        so anything that is not a plain ``- Label: yes|no|with-approval`` line
        is skipped rather than reported. Read the raw section for the rest.
        """
        levers: dict[str, str] = {}
        for label, value in _LEVER_RE.findall(self.sections.get("Change Scope", "")):
            normalized = value.strip().strip("*`").lower()
            if normalized in CHANGE_SCOPE_LEVER_VALUES:
                levers[label.strip()] = normalized
        return levers
