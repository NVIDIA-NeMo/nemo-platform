# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lightweight AGENTSpec.md contract.

The spec is a human-readable markdown file stored locally at
``agents/<name>-spec/AGENTSpec.md`` and canonically in Filesets as
``<workspace>/<name>-spec#AGENTSpec.md``.

Only the front matter and section outline are machine-validated here. The
section bodies remain markdown for humans and agents to read directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

_MIN_ROLE_LENGTH = 20
_VAGUE_ROLE_PHRASES = frozenset(
    {
        "help with stuff",
        "help users",
        "answer questions",
        "do things",
        "be helpful",
        "assist users",
    }
)

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
    "Unresolved Questions",
)
"""Required ``##`` section headings, in canonical order."""


@dataclass(frozen=True)
class AgentSpec:
    """Parsed AGENTSpec.md document.

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


def validate_role(role: str) -> str:
    """Return a normalized role or raise ``ValueError`` for vague input."""

    stripped = role.strip()
    if stripped.lower() in _VAGUE_ROLE_PHRASES:
        raise ValueError(
            f"'role' is too vague ({stripped!r}). Write one concrete sentence "
            "describing the role this agent plays for its users."
        )
    if len(stripped) < _MIN_ROLE_LENGTH:
        raise ValueError(
            f"'role' must be at least {_MIN_ROLE_LENGTH} characters after trimming "
            f"(got {len(stripped)}). Write one concrete sentence describing what "
            "role the agent plays."
        )
    return stripped
