# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lightweight AGENT-SPEC.md contract.

The spec is a human-readable markdown file stored locally at
``agents/<name>-spec/AGENT-SPEC.md`` and canonically in Filesets as
``<workspace>/<name>-spec#AGENT-SPEC.md``.

Only the front matter and section outline are machine-validated here. The
section bodies remain markdown for humans and agents to read directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

AGENT_SPEC_SECTION_TITLES: tuple[str, ...] = (
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
"""Required ``##`` section headings, in canonical order."""


@dataclass(frozen=True)
class AgentSpec:
    """Parsed AGENT-SPEC.md document.

    ``sections`` stores raw markdown by heading title. Downstream agents should
    read that markdown rather than relying on a bespoke nested Python schema.
    """

    name: str
    created_timestamp: datetime
    author: str
    sections: dict[str, str]

    @property
    def role(self) -> str:
        return self.sections["Role"]
