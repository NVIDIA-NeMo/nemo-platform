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
    Harness,
    ModelChoice,
    Scope,
)
from pydantic import ValidationError


def _valid_spec_kwargs(**overrides: Any) -> dict[str, Any]:
    """Build a kwargs dict for a fully-valid AgentSpec; overrides win."""

    base: dict[str, Any] = {
        "name": "it-helpdesk",
        "eval_command": "make eval",
        "role": "answer IT helpdesk questions about VPN, password reset, and software access",
        "purpose": "Help internal employees resolve common IT access issues quickly and escalate when needed.",
        "scope": Scope(
            audience="internal employees",
            categories=["vpn", "password reset", "software access"],
        ),
        "tools": "Prompt-only.",
        "model": ModelChoice(mode="cloud", family="Nemotron Super 49B"),
        "framework": Framework(resolution=FrameworkResolution.LANGGRAPH_NAT),
        "harness": Harness(
            description="NAT workflow harness with ReAct loop and platform-managed tool dispatch.",
            agent_loop="ReAct loop in NAT",
            tool_dispatch="NAT tool registry",
            runtime="NAT workflow",
        ),
        "behavior": "Give concise troubleshooting steps and escalate when account-specific access is required.",
        "success_criteria": "Employees resolve common IT issues or reach the right escalation path without sharing secrets.",
        "evaluation_setup": "Run `make eval`; it checks VPN, password reset, and software-access flows.",
    }
    base.update(overrides)
    return base


class TestValidSpec:
    def test_minimum_valid_spec_round_trips(self) -> None:
        spec = AgentSpec(**_valid_spec_kwargs())
        dumped = spec.model_dump()
        reloaded = AgentSpec.model_validate(dumped)
        assert reloaded == spec


class TestRoleValidation:
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
    def test_vague_roles_rejected(self, vague: str) -> None:
        # Some vague phrases are below the min-length floor; pad so the
        # validator hits the phrase check, not the length check.
        padded = f"   {vague}   " if len(vague.strip()) < 20 else vague
        with pytest.raises(ValidationError, match="too vague"):
            AgentSpec(**_valid_spec_kwargs(role=padded.ljust(25)))

    def test_role_short_after_strip_rejected(self) -> None:
        # Regression: Pydantic v2 ``min_length`` runs before the
        # ``@field_validator``, so a whitespace-padded short string passes the
        # built-in check. The validator must re-enforce the floor on the
        # stripped value.
        # Raw length 55 (passes ``min_length=20``); stripped form is "short" (5).
        padded_short = " " * 25 + "short" + " " * 25
        assert len(padded_short) > 20 and len(padded_short.strip()) < 20
        with pytest.raises(ValidationError, match="at least 20 characters"):
            AgentSpec(**_valid_spec_kwargs(role=padded_short))


class TestScopeValidation:
    def test_empty_category_rejected(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            AgentSpec(
                **_valid_spec_kwargs(
                    scope=Scope(
                        audience="internal employees",
                        categories=["vpn", "", "software"],
                    )
                )
            )


class TestExtraFieldsForbidden:
    def test_unknown_top_level_field_rejected(self) -> None:
        # Load-bearing: ``extra="forbid"`` is what makes the markdown
        # round-trip in :mod:`spec_render` safe. If someone relaxes it, the
        # parser will silently swallow typoed sections.
        with pytest.raises(ValidationError, match="extra"):
            AgentSpec(**_valid_spec_kwargs(known_issues=["foo"]))
