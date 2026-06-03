# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parse and lightly validate AGENT-SPEC.md.

This module intentionally does not model every markdown section as structured
Python. It validates the machine-readable front matter and the required section
outline, then returns raw markdown sections for humans and agents to consume.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import yaml
from nemo_agents_plugin.spec import AGENT_SPEC_SECTION_TITLES, AgentSpec


class SpecParseError(ValueError):
    """Raised when AGENT-SPEC.md cannot be parsed or fails lightweight validation."""


_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)


def parse_spec(markdown: str) -> AgentSpec:
    """Parse AGENT-SPEC.md into front matter plus raw markdown sections."""

    front_match = _FRONT_MATTER_RE.match(markdown)
    if front_match is None:
        raise SpecParseError("missing YAML front matter")

    front = yaml.safe_load(front_match.group(1)) or {}
    if not isinstance(front, dict):
        raise SpecParseError("YAML front matter must be a mapping")

    sections = _split_sections(markdown[front_match.end() :])
    _validate_required_sections(sections)

    framework = sections["Framework"].strip()
    if not framework or framework == "_(none)_":
        raise SpecParseError("framework section must be resolved")

    return AgentSpec(
        name=_required_str(front, "name"),
        created_timestamp=_required_datetime(front, "created_timestamp"),
        author=_required_str(front, "author"),
        sections=sections,
    )


def _required_str(front: dict[str, Any], key: str) -> str:
    value = front.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecParseError(f"front matter field {key!r} is required")
    return value.strip()


def _required_datetime(front: dict[str, Any], key: str) -> datetime:
    value = front.get(key)
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise SpecParseError(f"front matter field {key!r} is required")
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpecParseError(f"front matter field {key!r} must be an ISO 8601 datetime") from exc


def _split_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(body))
    for i, match in enumerate(matches):
        header = match.group(1).strip()
        if header in sections:
            raise SpecParseError(f"duplicate section: ## {header}")
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[header] = body[start:end].strip("\n")
    return sections


def _validate_required_sections(sections: dict[str, str]) -> None:
    for title in AGENT_SPEC_SECTION_TITLES:
        if title not in sections:
            raise SpecParseError(f"missing section: ## {title}")
