# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The analyst's single terminal result — a pure, storage-agnostic change-set.

Instead of mutating platform state through a series of tool calls
(``create_insight`` / ``update_insight``) while it
reasons, the analyst reads observability data only, then emits one
:class:`AnalystResult` struct that captures *every* change it wants to make.
That struct is the agent's typed output: Pydantic AI surfaces it as a single
``analyst_result`` tool, and the model calling that tool both ends the run and
hands the whole change-set back to the CLI.

These models intentionally know nothing about how the change-set is persisted.
Each :class:`~nemo_insights_plugin.analyst.analyst_backend.AnalystBackend`
decides that: the remote backend writes Insight rows to the DB, while the local
backend writes the result to a YAML file verbatim.
"""

from nemo_insights_plugin.entities import InsightStatus
from pydantic import BaseModel, ConfigDict, Field


class NewInsight(BaseModel):
    """A brand-new Insight the analyst wants to file."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        description=(
            "A short, human-readable sentence naming the insight (e.g. "
            "'Retrieval drops relevant context near the token limit'). The "
            "full problem statement goes in 'description', not here."
        ),
    )
    description: str = Field(
        min_length=1,
        description=(
            "Problem statement: the failure mode, the affected tool or model "
            "call, the conditions that trigger it, and a hypothesis for the "
            "cause. Specific enough to act on, general enough to recur."
        ),
    )
    status: InsightStatus = Field(
        default=InsightStatus.OPEN,
        description="Lifecycle status for the new insight (usually 'open').",
    )
    trace_refs: list[str] = Field(
        default_factory=list,
        description="Intake trace ids that serve as evidence for this insight.",
    )


class InsightUpdate(BaseModel):
    """New evidence to add to an existing Insight."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        description=(
            "Store-assigned id of the existing insight to add evidence to, as "
            "shown in the ``list_insights`` output (e.g. "
            "'insight-5Q2LoF8z8M9JZxZsHwJKNn'). Not the human-readable title."
        ),
    )
    trace_refs: list[str] = Field(
        default_factory=list,
        description=(
            "Intake trace ids to append as new evidence (merged with the insight's existing refs, de-duplicated)."
        ),
    )


class AnalystResult(BaseModel):
    """The analyst's complete, final change-set for one run.

    The model populates this once, at the end of its analysis, in place of the
    old mutating tool calls. Calling the ``analyst_result`` tool with this
    struct ends the run; the CLI then hands it to the backend to persist.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        min_length=1,
        description=(
            "Brief natural-language summary of the analysis and the "
            "highest-impact findings, for the developer reading the run."
        ),
    )
    new_insights: list[NewInsight] = Field(
        default_factory=list,
        description="Insights to create that do not already exist for the agent.",
    )
    updated_insights: list[InsightUpdate] = Field(
        default_factory=list,
        description=(
            "New evidence (trace refs) for insights that already exist for "
            "the agent. Only evidence can be added to an existing insight — to "
            "record anything else, file a new insight."
        ),
    )
