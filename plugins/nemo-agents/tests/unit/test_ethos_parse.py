# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for lightweight ETHOS.md parsing."""

from __future__ import annotations

import pytest
from nemo_agents_plugin.ethos import (
    CORE_SECTION_TITLES,
    ETHOS_SECTION_TITLES,
    ETHOS_V1_SECTION_TITLES,
    INTENT_SECTION_TITLES,
    OPTIONAL_SECTION_TITLES,
    RETIRED_SECTION_TITLES,
)
from nemo_agents_plugin.ethos_parse import EthosParseError, parse_ethos

_DEFAULT_OVERRIDES = {
    "Role": "help users with IT issues",
    "Framework": "- Resolution: langgraph-nat",
}


def _ethos_md(
    *,
    version: int | None = 2,
    titles: tuple[str, ...] | None = None,
    extra_front: str = "",
    sections: dict[str, str] | None = None,
) -> str:
    titles = (
        titles
        if titles is not None
        else (ETHOS_SECTION_TITLES if version and version >= 2 else ETHOS_V1_SECTION_TITLES)
    )
    front_lines = ["name: it-helpdesk", "created_timestamp: '2026-01-02T03:04:05+00:00'", "author: agent-1"]
    if version is not None:
        front_lines.append(f"schema_version: {version}")
    if extra_front:
        front_lines.append(extra_front)
    front = "---\n" + "\n".join(front_lines) + "\n---"

    bodies = {title: f"{title} content" for title in titles}
    bodies.update({k: v for k, v in _DEFAULT_OVERRIDES.items() if k in bodies})
    bodies.update(sections or {})
    body = "\n\n".join(f"## {title}\n\n{bodies[title]}" for title in titles)
    return f"{front}\n\n# Ethos: it-helpdesk\n\n{body}\n"


def test_valid_ethos_parses_to_metadata_and_sections() -> None:
    ethos = parse_ethos(_ethos_md())

    assert ethos.name == "it-helpdesk"
    assert ethos.author == "agent-1"
    assert ethos.role == "help users with IT issues"
    assert ethos.schema_version == 2
    assert ethos.warnings == ()


def test_missing_required_section_rejected() -> None:
    md = _ethos_md(version=1).replace("## Purpose\n\nPurpose content\n\n", "")

    with pytest.raises(EthosParseError, match=r"missing section: ## Purpose"):
        parse_ethos(md)


def test_v1_file_parses_without_intent_sections() -> None:
    """A version 1 contract keeps working untouched, warnings and all."""
    ethos = parse_ethos(_ethos_md(version=1))

    assert ethos.schema_version == 1
    assert ethos.warnings == ()
    assert "Business Objectives" not in ethos.sections


def test_absent_version_parses_as_v1_and_warns() -> None:
    ethos = parse_ethos(_ethos_md(version=None, titles=ETHOS_V1_SECTION_TITLES))

    assert ethos.schema_version == 1
    assert len(ethos.warnings) == 1
    assert "no 'schema_version'" in ethos.warnings[0]


def test_v2_missing_core_section_is_an_error() -> None:
    titles = tuple(t for t in ETHOS_SECTION_TITLES if t != "Success Criteria")

    with pytest.raises(EthosParseError, match=r"missing section: ## Success Criteria"):
        parse_ethos(_ethos_md(titles=titles))


def test_v2_missing_intent_section_warns_but_parses() -> None:
    titles = tuple(t for t in ETHOS_SECTION_TITLES if t != "Principles")

    ethos = parse_ethos(_ethos_md(titles=titles))

    assert ethos.warnings == ("missing intent section: ## Principles",)


def test_v2_missing_intent_section_errors_under_strict() -> None:
    titles = tuple(t for t in ETHOS_SECTION_TITLES if t != "Principles")

    with pytest.raises(EthosParseError, match=r"missing intent section: ## Principles"):
        parse_ethos(_ethos_md(titles=titles), strict=True)


def test_v2_optional_section_may_be_omitted_silently() -> None:
    titles = tuple(t for t in ETHOS_SECTION_TITLES if t != "Metric Semantics")

    ethos = parse_ethos(_ethos_md(titles=titles))

    assert ethos.warnings == ()


def test_unsupported_future_version_rejected() -> None:
    with pytest.raises(EthosParseError, match=r"schema version 99"):
        parse_ethos(_ethos_md(version=99))


def test_optional_front_matter_fields_are_parsed() -> None:
    ethos = parse_ethos(_ethos_md(extra_front="owner: platform-team\nupdated_timestamp: '2026-03-04T05:06:07+00:00'"))

    assert ethos.owner == "platform-team"
    assert ethos.updated_timestamp is not None
    assert ethos.updated_timestamp.year == 2026


def test_change_scope_levers_recognize_with_approval() -> None:
    change_scope = "\n".join(
        [
            "- System prompt: yes",
            "- Fine-tuning: no",
            "- Model swap (within mode): with-approval",
            "- Tools: **allowed**",
            "- Notes: escalate before broadening destructive capabilities",
        ]
    )

    ethos = parse_ethos(_ethos_md(sections={"Change Scope": change_scope}))

    assert ethos.change_scope_levers == {
        "System prompt": "yes",
        "Fine-tuning": "no",
        "Model swap (within mode)": "with-approval",
    }


def test_v2_drops_optimizer_run_configuration() -> None:
    """Budget was cut: Ethos records durable intent, not per-run limits."""
    assert "Budget" not in ETHOS_SECTION_TITLES


def test_v2_tiers_partition_the_section_list() -> None:
    """Every v2 section sits in exactly one tier, and the tiers add nothing extra."""
    tiered = CORE_SECTION_TITLES + INTENT_SECTION_TITLES + OPTIONAL_SECTION_TITLES

    assert len(tiered) == len(set(tiered))
    assert set(tiered) == set(ETHOS_SECTION_TITLES)


def test_v2_retirements_are_declared() -> None:
    """Whatever v2 gives up is listed, so a drop can't happen silently."""
    assert set(ETHOS_V1_SECTION_TITLES) - set(ETHOS_SECTION_TITLES) == set(RETIRED_SECTION_TITLES)


def test_retired_sections_are_gone_from_v2() -> None:
    assert not set(RETIRED_SECTION_TITLES) & set(ETHOS_SECTION_TITLES)


def test_purpose_merged_into_outcomes() -> None:
    """v1's Purpose became Purpose & Outcomes, so mission and result stay together."""
    assert "Purpose" not in ETHOS_SECTION_TITLES
    assert "Purpose & Outcomes" in CORE_SECTION_TITLES


def test_v2_tolerates_leftover_retired_sections() -> None:
    """A file mid-upgrade keeps parsing: retired sections are carried, not rejected."""
    at = ETHOS_SECTION_TITLES.index("Tools") + 1
    titles = ETHOS_SECTION_TITLES[:at] + RETIRED_SECTION_TITLES + ETHOS_SECTION_TITLES[at:]

    ethos = parse_ethos(
        _ethos_md(titles=titles, sections={"Framework": "- Resolution: langgraph-nat"}),
        strict=True,
    )

    assert ethos.warnings == ()
    assert ethos.sections["Framework"] == "- Resolution: langgraph-nat"
    assert ethos.sections["Signals"] == "Signals content"


def test_vision_is_optional() -> None:
    titles = tuple(t for t in ETHOS_SECTION_TITLES if t != "Vision")

    assert parse_ethos(_ethos_md(titles=titles), strict=True).warnings == ()


def test_v2_drops_framework() -> None:
    """Nothing read the section's value; the container label comes from agent.yaml."""
    assert "Framework" not in ETHOS_SECTION_TITLES
    assert "Framework" in ETHOS_V1_SECTION_TITLES


def test_v1_still_enforces_resolved_framework() -> None:
    """v1 behavior is unchanged, including the resolution gate."""
    with pytest.raises(EthosParseError, match="framework section must be resolved"):
        parse_ethos(_ethos_md(version=1, sections={"Framework": "_(none)_"}))
