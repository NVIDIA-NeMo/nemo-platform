# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights plugin entity definitions — stored in the NeMo Platform entity store.

Three entities live here:

* :class:`AgentRegistration` — the registered agent under test (AUT). Created via the
  ``AGENT_DESCRIPTION.md`` setup skill. ``name`` is the canonical agent identifier
  and must match the ``agent_id`` span attribute emitted into intake.

* :class:`Insight` — a named, persistent problem in the AUT, produced by the analyst.
  References an :class:`AgentRegistration` by name within the same workspace.

* :class:`InsightTrace` — the association between an :class:`Insight` and a trace in
  intake, carrying the trace's role (evidence vs. regression-test candidate).
  Composite name ``"{insight}--{trace_id}"`` enforces uniqueness of the link.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from nemo_platform_plugin.entity import NemoEntity
from pydantic import Field


class CloudAgentType(StrEnum):
    CURSOR = "cursor"
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"


class InsightStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DELETED = "deleted"


class InsightTraceRole(StrEnum):
    EVIDENCE = "evidence"
    REGRESSION_TEST_CANDIDATE = "regression_test_candidate"


class AgentRegistration(NemoEntity, entity_type="agent_registration"):
    """A registered agent under test.

    ``name`` (inherited from EntityBase) is the canonical agent name and must match
    the ``agent_id`` span attribute the AUT emits into intake. This is how the
    analyst filters traces to a specific AUT.
    """

    description: str = Field(default="", description="Human-readable description of the AUT.")
    repo_url: str = Field(default="", description="URL of the source repository hosting the AUT.")
    agent_description_path: str = Field(
        default="AGENT_DESCRIPTION.md",
        description="Path within the repo to the AGENT_DESCRIPTION.md file.",
    )
    agent_description_content: str = Field(
        default="",
        description="Last uploaded AGENT_DESCRIPTION.md body. Inlined as a string in v1.",
    )
    agent_description_uploaded_at: datetime | None = Field(
        default=None,
        description="Timestamp of the most recent AGENT_DESCRIPTION.md upload.",
    )
    eval_command: str = Field(
        default="",
        description="CLI command (from AGENT_DESCRIPTION.md front matter) for running evals.",
    )
    cloud_agent_type: CloudAgentType | None = Field(
        default=None,
        description="Configured cloud coding-agent integration. None until configured (M3).",
    )
    cloud_agent_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form cloud-agent configuration. Schema firmed up in M3.",
    )


class Insight(NemoEntity, entity_type="insight"):
    """A named, persistent problem in the AUT.

    Status transitions allowed: ``open → in_progress``, ``open → resolved``,
    ``open → deleted``, ``in_progress → resolved``, ``in_progress → deleted``,
    ``resolved → in_progress`` (reopening). Same-state writes are idempotent.
    All other transitions return 400.
    """

    agent: str = Field(description="Name of the AgentRegistration this insight is about.")
    description: str = Field(description="The problem statement: specific enough to act on.")
    hypothesis: str = Field(
        default="",
        description="Analyst's reasoning for how to address the insight.",
    )
    status: InsightStatus = Field(default=InsightStatus.OPEN)
    impact_estimate: float | None = Field(
        default=None,
        description="Derived by the analyst from associated traces. Null when human-authored.",
    )
    eval_dataset_row_refs: list[str] = Field(
        default_factory=list,
        description="Evaluator dataset row ids attached as regression tests.",
    )
    experiment_refs: list[str] = Field(
        default_factory=list,
        description="Experiment entity names attempted against this insight. Empty in M1.",
    )


class InsightTrace(NemoEntity, entity_type="insight_trace"):
    """Join entity linking an Insight to a trace in intake.

    Naming convention: ``name == f"{insight}--{trace_id}"``. Callers should let the
    service layer construct this — see :func:`compose_insight_trace_name`.
    """

    insight: str = Field(description="Name of the Insight this trace is attached to.")
    trace_id: str = Field(description="intake trace.id of the linked trace.")
    role: InsightTraceRole = Field(default=InsightTraceRole.EVIDENCE)
    note: str = Field(default="", description="Optional analyst note on this association.")


def compose_insight_trace_name(insight: str, trace_id: str) -> str:
    """Compose the canonical InsightTrace name from its (insight, trace_id) pair.

    The double-dash separator is unlikely to appear in insight names or trace ids;
    if it ever does we'd need to escape, but for v1 this is sufficient.
    """
    return f"{insight}--{trace_id}"
