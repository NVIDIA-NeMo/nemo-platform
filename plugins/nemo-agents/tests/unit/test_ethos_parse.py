# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for lightweight ETHOS.md parsing."""

from __future__ import annotations

from nemo_agents_plugin.ethos import ETHOS_SECTION_TITLES
from nemo_agents_plugin.ethos_parse import parse_ethos


def _spec_md(**sections: str) -> str:
    front = "---\nname: it-helpdesk\ncreated_timestamp: '2026-01-02T03:04:05+00:00'\nauthor: agent-1\n---"
    defaults = {title: f"{title} content" for title in ETHOS_SECTION_TITLES}
    defaults["Role"] = "help users with IT issues"
    defaults["Framework"] = "- Resolution: langgraph-nat"
    defaults.update(sections)
    body = "\n\n".join(f"## {title}\n\n{defaults[title]}" for title in ETHOS_SECTION_TITLES)
    return f"{front}\n\n# Ethos: it-helpdesk\n\n{body}\n"


def test_valid_ethos_parses_to_metadata_and_sections() -> None:
    ethos = parse_ethos(_spec_md())

    assert ethos.name == "it-helpdesk"
    assert ethos.author == "agent-1"
    assert ethos.role == "help users with IT issues"
    assert ethos.sections["Framework"] == "- Resolution: langgraph-nat"


def test_missing_required_section_rejected() -> None:
    md = _spec_md().replace("## Purpose\n\nPurpose content\n\n", "")

    try:
        parse_ethos(md)
    except ValueError as exc:
        assert "missing section: ## Purpose" in str(exc)
    else:
        raise AssertionError("missing Purpose section was accepted")
