# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the AgentSpec <-> markdown round-trip."""

from __future__ import annotations

from typing import Any

import pytest
from nemo_agents_plugin.spec import (
    AgentSpec,
    AllowedChanges,
    Framework,
    FrameworkResolution,
    ModelChoice,
)
from nemo_agents_plugin.spec_render import (
    SpecRenderError,
    parse_spec,
    render_spec,
)
from pydantic import ValidationError


def _minimal_spec(**overrides: Any) -> AgentSpec:
    base: dict[str, Any] = {
        "name": "it-helpdesk",
        "eval_command": "make eval",
        "job": "answer IT helpdesk questions about VPN, password reset, and software access",
        "audience": "internal employees",
        "categories": ["vpn", "password reset", "software access"],
        "tools": "Prompt-only.",
        "model": ModelChoice(mode="cloud", family="Nemotron Super 49B"),
        "framework": Framework(resolution=FrameworkResolution.LANGGRAPH_NAT),
        "success_criteria": ["VPN troubleshooting reaches resolution or escalation"],
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
        out = render_spec(_minimal_spec())
        constraints_section = out.split("## Constraints", 1)[1].split("##", 1)[0]
        assert "_(none)_" in constraints_section


class TestRoundTrip:
    def test_minimal_spec_round_trips(self) -> None:
        spec = _minimal_spec()
        assert parse_spec(render_spec(spec)) == spec

    def test_spec_with_all_optional_fields_round_trips(self) -> None:
        spec = _minimal_spec(
            constraints=["never give medical advice", "max 200 tokens"],
            feedback_signals="prioritize thumbs-down on escalation flows",
            eval_command_notes="evals not yet wired; baseline TBD",
            open_questions=["SLA for after-hours escalation?"],
            allowed_changes=AllowedChanges(
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

    def test_needs_wrapper_framework_round_trips(self) -> None:
        spec = _minimal_spec(
            framework=Framework(
                resolution=FrameworkResolution.NEEDS_WRAPPER,
                source_framework="autogen",
                notes="needs NAT wrapper",
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
            parse_spec("# Agent Spec\n\n## Job\n\nsomething\n")

    def test_missing_required_section(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace("## Audience\n\ninternal employees\n", "")
        with pytest.raises(SpecRenderError, match=r"missing section.*Audience"):
            parse_spec(md)

    def test_unknown_section_rejected(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec) + "\n## Known Issues\n\n- something\n"
        with pytest.raises(SpecRenderError, match="unknown section"):
            parse_spec(md)

    def test_duplicate_section_rejected(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec) + "\n## Job\n\nduplicate\n"
        with pytest.raises(SpecRenderError, match="duplicate section"):
            parse_spec(md)

    def test_unknown_framework_resolution(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace("- Resolution: langgraph-nat", "- Resolution: bespoke")
        with pytest.raises(SpecRenderError, match="framework resolution"):
            parse_spec(md)

    def test_unknown_allowed_changes_label(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace("- System prompt: yes", "- System prompt: yes\n- Mystery field: no")
        with pytest.raises(SpecRenderError, match="allowed-changes label"):
            parse_spec(md)

    def test_non_bullet_in_list_section_rejected(self) -> None:
        spec = _minimal_spec()
        # Replace categories bullets with a paragraph.
        md = render_spec(spec).replace(
            "- vpn\n- password reset\n- software access",
            "vpn, password reset, software access",
        )
        with pytest.raises(SpecRenderError, match="expected bullet"):
            parse_spec(md)

    def test_validation_error_propagates(self) -> None:
        spec = _minimal_spec()
        md = render_spec(spec).replace(
            "- vpn\n- password reset\n- software access",
            "- vpn",
        )
        with pytest.raises(ValidationError):
            parse_spec(md)
