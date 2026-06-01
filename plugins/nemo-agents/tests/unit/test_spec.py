# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the AgentSpec Pydantic schema.

Coverage philosophy: lock product behavior that lives in this module's code
(validators, cleanup logic, the ``extra="forbid"`` posture that protects
round-tripping with :mod:`spec_render`). Tests that merely re-state
``Field(...)`` declarations or assert that Pydantic does what its docs say
are intentionally omitted.
"""

from __future__ import annotations

from typing import Any

import pytest
from nemo_agents_plugin.spec import (
    AgentSpec,
    Framework,
    FrameworkResolution,
    ModelChoice,
)
from pydantic import ValidationError


def _valid_spec_kwargs(**overrides: Any) -> dict[str, Any]:
    """Build a kwargs dict for a fully-valid AgentSpec; overrides win."""

    base: dict[str, Any] = {
        "name": "it-helpdesk",
        "eval_command": "make eval",
        "job": "answer IT helpdesk questions about VPN, password reset, and software access",
        "audience": "internal employees",
        "categories": ["vpn", "password reset", "software access"],
        "tools": "Prompt-only.",
        "model": ModelChoice(mode="cloud", family="Nemotron Super 49B"),
        "framework": Framework(resolution=FrameworkResolution.LANGGRAPH_NAT),
        "success_criteria": ["VPN troubleshooting reaches a resolution or escalation"],
    }
    base.update(overrides)
    return base


class TestValidSpec:
    def test_minimum_valid_spec_round_trips(self) -> None:
        spec = AgentSpec(**_valid_spec_kwargs())
        dumped = spec.model_dump()
        reloaded = AgentSpec.model_validate(dumped)
        assert reloaded == spec


class TestJobValidation:
    @pytest.mark.parametrize(
        "vague",
        [
            "help with stuff",
            "Help With Stuff",
            "  help users  ",
            "answer questions",
            "do things",
            "be helpful",
            "assist users",
        ],
    )
    def test_vague_jobs_rejected(self, vague: str) -> None:
        # Some vague phrases are below the min-length floor; pad so the
        # validator hits the phrase check, not the length check.
        padded = f"   {vague}   " if len(vague.strip()) < 20 else vague
        with pytest.raises(ValidationError, match="too vague"):
            AgentSpec(**_valid_spec_kwargs(job=padded.ljust(25)))

    def test_job_short_after_strip_rejected(self) -> None:
        # Regression: Pydantic v2 ``min_length`` runs before the
        # ``@field_validator``, so a whitespace-padded short string passes the
        # built-in check. The validator must re-enforce the floor on the
        # stripped value.
        # Raw length 55 (passes ``min_length=20``); stripped form is "short" (5).
        padded_short = " " * 25 + "short" + " " * 25
        assert len(padded_short) > 20 and len(padded_short.strip()) < 20
        with pytest.raises(ValidationError, match="at least 20 characters"):
            AgentSpec(**_valid_spec_kwargs(job=padded_short))


class TestFrameworkValidation:
    def test_missing_framework_rejected(self) -> None:
        # Framework is one of the two hard preconditions enforced by the
        # explore-first flow; without it the build skill has nothing to act on.
        kwargs = _valid_spec_kwargs()
        del kwargs["framework"]
        with pytest.raises(ValidationError, match="framework"):
            AgentSpec(**kwargs)


class TestCategoriesValidation:
    @pytest.mark.parametrize("categories", [["a", "b"], ["a", "b", "c", "d", "e", "f", "g"]])
    def test_category_count_out_of_range_rejected(self, categories: list[str]) -> None:
        # 3-6 is a real product contract from the explore skill, not just a
        # Field bound — worth pinning at the boundary.
        with pytest.raises(ValidationError):
            AgentSpec(**_valid_spec_kwargs(categories=categories))

    def test_empty_category_rejected(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            AgentSpec(**_valid_spec_kwargs(categories=["vpn", "", "software"]))


class TestExtraFieldsForbidden:
    def test_unknown_top_level_field_rejected(self) -> None:
        # Load-bearing: ``extra="forbid"`` is what makes the markdown
        # round-trip in :mod:`spec_render` safe. If someone relaxes it, the
        # parser will silently swallow typoed sections.
        with pytest.raises(ValidationError, match="extra"):
            AgentSpec(**_valid_spec_kwargs(known_issues=["foo"]))
