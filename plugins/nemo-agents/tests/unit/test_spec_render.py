# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the AgentSpec <-> markdown round-trip."""

from __future__ import annotations

from typing import Any

import pytest
from nemo_agents_plugin.spec import (
    AgentSpec,
    ChangeScope,
    Framework,
    FrameworkResolution,
    Harness,
    ModelChoice,
    Scope,
)
from nemo_agents_plugin.spec_render import (
    SpecRenderError,
    parse_spec,
    render_spec,
)


def _minimal_spec(**overrides: Any) -> AgentSpec:
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
    return AgentSpec(**base)


class TestRender:
    # Most render shape is asserted by the round-trip tests below. The two
    # cases kept here are edge behaviors the round-trip can't observe:
    # eval_command omission from front matter, and the ``_(none)_``
    # placeholder for empty optional lists.

    def test_omits_eval_command_when_none(self) -> None:
        out = render_spec(_minimal_spec(eval_command=None))
        assert "eval_command" not in out.split("---", 2)[1]

    def test_empty_optional_lists_render_as_placeholder(self) -> None:
        out = render_spec(_minimal_spec(harness=None))
        harness_section = out.split("## Harness", 1)[1].split("##", 1)[0]
        assert "_(none)_" in harness_section
        questions_section = out.split("## Unresolved Questions", 1)[1].split("##", 1)[0]
        assert "_(none)_" in questions_section


class TestRoundTrip:
    def test_minimal_spec_round_trips(self) -> None:
        spec = _minimal_spec()
        assert parse_spec(render_spec(spec)) == spec

    def test_spec_without_harness_round_trips(self) -> None:
        spec = _minimal_spec(harness=None)
        assert parse_spec(render_spec(spec)) == spec

    def test_spec_with_all_optional_fields_round_trips(self) -> None:
        spec = _minimal_spec(
            scope=Scope(
                audience="internal employees",
                categories=["vpn", "password reset", "software access"],
                in_scope=["VPN troubleshooting", "password reset guidance"],
                out_of_scope=["hardware procurement approvals"],
            ),
            behavior="Never ask users to share passwords; escalate account-specific access changes.",
            success_criteria="Users should get accurate next steps, know when to escalate, and never be asked for secrets.",
            evaluation_setup=(
                "Run `make eval`; baseline is not yet established and escalation coverage is thin relative to success criteria."
            ),
            signals="prioritize thumbs-down on escalation flows",
            unresolved_questions=["SLA for after-hours escalation?"],
            change_scope=ChangeScope(
                system_prompt=True,
                tools=False,
                middleware=True,
                inference_params=True,
                model_swap_within_mode=False,
                skills=True,
                fine_tuning=False,
                notes="tools are pinned for compliance review",
            ),
        )
        assert parse_spec(render_spec(spec)) == spec

    def test_full_harness_details_round_trip(self) -> None:
        spec = _minimal_spec(
            harness=Harness(
                description="Custom service harness with tool execution and replay.",
                agent_loop="service-owned loop",
                tool_dispatch="validated HTTP tool calls",
                context_management="sliding conversation window",
                state_management="database-backed session state",
                guardrails="service-level policy middleware",
                observability="OTEL traces and replay logs",
                verification="post-run answer validator",
                runtime="custom service",
                notes="needs NAT wrapper for NeMo build path",
            )
        )
        assert parse_spec(render_spec(spec)) == spec

    def test_needs_wrapper_framework_round_trips(self) -> None:
        spec = _minimal_spec(
            framework=Framework(
                resolution=FrameworkResolution.NEEDS_WRAPPER,
                source_framework="autogen",
                notes="needs NAT wrapper for NeMo build path",
            )
        )
        assert parse_spec(render_spec(spec)) == spec

    def test_tools_table_round_trips(self) -> None:
        tools_md = (
            "| Tool | Purpose | Credentials needed |\n"
            "|---|---|---|\n"
            "| current_datetime | clock | none |\n"
            "| confluence_search | KB lookup | service account |"
        )
        spec = _minimal_spec(tools=tools_md)
        round_tripped = parse_spec(render_spec(spec))
        assert round_tripped.tools == tools_md


class TestParseErrors:
    def test_missing_front_matter(self) -> None:
        with pytest.raises(SpecRenderError, match="front matter"):
            parse_spec("# Agent Spec\n\n## Role\n\nsomething\n")

    def test_missing_required_section(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace(
            "## Purpose\n\nHelp internal employees resolve common IT access issues quickly and escalate when needed.\n",
            "",
        )
        with pytest.raises(SpecRenderError, match=r"missing section.*Purpose"):
            parse_spec(md)

    def test_unknown_section_rejected(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec) + "\n## Known Issues\n\n- something\n"
        with pytest.raises(SpecRenderError, match="unknown section"):
            parse_spec(md)

    def test_duplicate_section_rejected(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec) + "\n## Role\n\nduplicate\n"
        with pytest.raises(SpecRenderError, match="duplicate section"):
            parse_spec(md)

    def test_missing_harness_description(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace(
            "- Description: NAT workflow harness with ReAct loop and platform-managed tool dispatch.\n",
            "",
        )
        with pytest.raises(SpecRenderError, match="missing 'Description'"):
            parse_spec(md)

    def test_unknown_framework_resolution(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace("- Resolution: langgraph-nat", "- Resolution: bespoke")
        with pytest.raises(SpecRenderError, match="framework resolution"):
            parse_spec(md)

    def test_unknown_change_scope_label(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace("- System prompt: yes", "- System prompt: yes\n- Mystery field: no")
        with pytest.raises(SpecRenderError, match="change-scope label"):
            parse_spec(md)

    def test_non_bullet_in_list_section_rejected(self) -> None:
        spec = _minimal_spec()
        # Replace unresolved-question bullets with a paragraph.
        spec = _minimal_spec(unresolved_questions=["Who owns after-hours escalation?"])
        md = render_spec(spec).replace(
            "- Who owns after-hours escalation?",
            "Who owns after-hours escalation?",
        )
        with pytest.raises(SpecRenderError, match="expected bullet"):
            parse_spec(md)
