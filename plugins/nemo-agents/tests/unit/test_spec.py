# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the AgentSpec Pydantic schema."""

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

    def test_defaults(self) -> None:
        spec = AgentSpec(**_valid_spec_kwargs())
        assert spec.constraints == []
        assert spec.open_questions == []
        assert spec.feedback_signals is None
        assert spec.eval_command_notes is None
        assert spec.allowed_changes == AllowedChanges()

    def test_allowed_changes_defaults_match_por(self) -> None:
        ac = AllowedChanges()
        assert ac.system_prompt is True
        assert ac.tools is True
        assert ac.middleware is True
        assert ac.inference_params is True
        assert ac.model_swap_within_mode is True
        assert ac.skills is True
        assert ac.fine_tuning is False


class TestJobValidation:
    def test_missing_job_rejected(self) -> None:
        kwargs = _valid_spec_kwargs()
        del kwargs["job"]
        with pytest.raises(ValidationError, match="job"):
            AgentSpec(**kwargs)

    def test_too_short_job_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentSpec(**_valid_spec_kwargs(job="short"))

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
        # Some vague phrases are below the min-length floor; force a long
        # surrounding string so we're testing the phrase check, not the length.
        # We pad with spaces so .strip() leaves the original phrase intact.
        padded = f"   {vague}   " if len(vague.strip()) < 20 else vague
        with pytest.raises(ValidationError, match="too vague"):
            AgentSpec(**_valid_spec_kwargs(job=padded.ljust(25)))

    def test_job_is_stripped(self) -> None:
        spec = AgentSpec(**_valid_spec_kwargs(job="  answer IT helpdesk questions for staff  "))
        assert spec.job == "answer IT helpdesk questions for staff"


class TestFrameworkValidation:
    def test_missing_framework_rejected(self) -> None:
        kwargs = _valid_spec_kwargs()
        del kwargs["framework"]
        with pytest.raises(ValidationError, match="framework"):
            AgentSpec(**kwargs)

    def test_needs_wrapper_with_source(self) -> None:
        spec = AgentSpec(
            **_valid_spec_kwargs(
                framework=Framework(
                    resolution=FrameworkResolution.NEEDS_WRAPPER,
                    source_framework="crewai",
                    notes="wrap CrewAI agents in a NAT workflow",
                )
            )
        )
        assert spec.framework.resolution is FrameworkResolution.NEEDS_WRAPPER
        assert spec.framework.source_framework == "crewai"

    def test_framework_resolution_values(self) -> None:
        assert FrameworkResolution.LANGGRAPH_NAT.value == "langgraph-nat"
        assert FrameworkResolution.NEEDS_WRAPPER.value == "needs-wrapper"

    def test_framework_field_marks_planned_deprecation(self) -> None:
        schema = AgentSpec.model_json_schema()
        assert schema["properties"]["framework"]["x-planned-deprecation"] == ("tracked under FP-161")


class TestCategoriesValidation:
    def test_too_few_categories_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentSpec(**_valid_spec_kwargs(categories=["a", "b"]))

    def test_too_many_categories_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentSpec(**_valid_spec_kwargs(categories=["a", "b", "c", "d", "e", "f", "g"]))

    def test_empty_category_rejected(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            AgentSpec(**_valid_spec_kwargs(categories=["vpn", "", "software"]))

    def test_categories_are_stripped(self) -> None:
        spec = AgentSpec(**_valid_spec_kwargs(categories=["  vpn  ", " reset ", "software"]))
        assert spec.categories == ["vpn", "reset", "software"]


class TestModelChoiceValidation:
    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelChoice(mode="onprem", family="Nemotron")  # type: ignore[arg-type]

    def test_empty_family_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelChoice(mode="cloud", family="")


class TestExtraFieldsForbidden:
    def test_unknown_top_level_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            AgentSpec(**_valid_spec_kwargs(known_issues=["foo"]))

    def test_unknown_framework_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Framework(
                resolution=FrameworkResolution.LANGGRAPH_NAT,
                version="0.1",  # type: ignore[call-arg]
            )


class TestSuccessCriteriaValidation:
    def test_empty_success_criteria_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentSpec(**_valid_spec_kwargs(success_criteria=[]))


class TestJsonSchemaExport:
    def test_exports_clean_json_schema(self) -> None:
        schema = AgentSpec.model_json_schema()
        assert schema["type"] == "object"
        # Sanity-check that every body field is present.
        for field in (
            "name",
            "job",
            "audience",
            "categories",
            "tools",
            "model",
            "framework",
            "constraints",
            "success_criteria",
            "allowed_changes",
            "feedback_signals",
            "eval_command_notes",
            "open_questions",
        ):
            assert field in schema["properties"], field
