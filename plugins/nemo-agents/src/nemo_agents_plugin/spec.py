# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent spec schema (``agents/<name>.spec.md``).

The :class:`AgentSpec` model is the canonical typed artifact that the
``nemo-explore`` skill produces and ``nemo-spec`` writes to disk. It is also
the contract that the analyst agent (insights plugin) and the experimentalist
agent read as their primary context.

The spec is persisted in two places:

* The platform's Filesets service, which is the **source of truth**.
* A local file at ``agents/<name>.spec.md`` in the developer's working
  directory, which is a write-through cache. On conflict, the Fileset copy
  wins.

The on-disk markdown format is a render of this model: YAML front matter
(``name``, ``eval_command``) plus one ``##`` section per body field, in the
order declared on the model. Round-tripping markdown ↔ ``AgentSpec`` is the
responsibility of a separate renderer module; this file owns only the schema
and its validation.

Field-level guidance ("what good looks like") lives in the ``nemo-explore``
skill at
``packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-explore/SKILL.md``
and is intentionally kept out of this file so the schema stays terse and the
skill stays the single source of truth for interview prompts.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A "job" answer below this length is almost always too vague to be useful
# downstream (e.g. "help with stuff", "answer questions"). The exact cutoff is
# a heuristic — the real guard is the vague-phrase check in
# :meth:`AgentSpec._validate_job`.
_MIN_JOB_LENGTH = 20

# Vague stems we reject outright. Match is case-insensitive on the full
# (stripped) job string.
_VAGUE_JOB_PHRASES = frozenset(
    {
        "help with stuff",
        "help users",
        "answer questions",
        "do things",
        "be helpful",
        "assist users",
    }
)


class FrameworkResolution(str, Enum):
    """Resolved framework status for the agent.

    The ``nemo-explore`` skill forces the user to pick one of these before
    handoff. ``nemo-spec`` refuses to write if the value is missing.
    """

    LANGGRAPH_NAT = "langgraph-nat"
    """LangGraph wrapped in NVIDIA NeMo Agent Toolkit (NAT) — the supported
    build path."""

    NEEDS_WRAPPER = "needs-wrapper"
    """The agent is in another framework (CrewAI, AutoGen, plain LangChain,
    Pydantic AI, etc.) and needs a user-written NAT wrapper before
    ``nemo-build-agent`` can do anything useful."""


class Framework(BaseModel):
    """The agent's framework, resolved against NAT support.

    Marked planned-deprecation: this guard exists today because NAT only
    supports LangGraph-wrapped agents. It is expected to relax as NAT expands.
    Do not bake assumptions about this field's permanence into other code.
    """

    model_config = ConfigDict(extra="forbid")

    resolution: FrameworkResolution
    source_framework: str | None = Field(
        default=None,
        description=(
            "Name of the source framework (e.g. 'crewai', 'autogen', "
            "'langchain', 'pydantic-ai') when ``resolution`` is "
            "``needs-wrapper``. Ignored otherwise."
        ),
    )
    notes: str | None = Field(
        default=None,
        description="Free-form notes — wrapper plan, version constraints, etc.",
    )


class ModelChoice(BaseModel):
    """Model family/size choice. Resolved to a concrete model entity ID later
    by ``nemo-build-agent`` via ``nemo models list``; this is not the place to
    pin an alias.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["cloud", "local-nim"] = Field(
        description="'cloud' = NVIDIA Build API. 'local-nim' = self-hosted NIM "
        "(requires host-gpu mode at deploy time).",
    )
    family: str = Field(
        min_length=1,
        description="Family or size, e.g. 'Nemotron Super 49B', 'smallest open-weight that works'.",
    )


class AllowedChanges(BaseModel):
    """Permissions list controlling what the experimentalist agent in the
    optimization loop is allowed to modify when fixing Insights.

    Defaults follow the POR: prompt, tools, middleware, inference params,
    model swap within mode, and skills are all on; fine-tuning is off. The
    user can veto any of these during ``nemo-explore``. The loop never edits
    the spec file itself.
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: bool = True
    tools: bool = True
    middleware: bool = True
    inference_params: bool = True
    model_swap_within_mode: bool = True
    skills: bool = True
    fine_tuning: bool = False
    notes: str | None = Field(
        default=None,
        description="Free-form notes — vetoes, exceptions, scope clarifications.",
    )


class AgentSpec(BaseModel):
    """The canonical agent spec, written to ``agents/<name>.spec.md``.

    Field order on the class matches the on-disk section order. ``name`` and
    ``eval_command`` render as YAML front matter; all other fields render as
    ``##`` body sections in declared order.

    The two hard preconditions for handoff to ``nemo-spec`` are ``job`` and
    ``framework`` — both must validate before the spec is written.

    Known issues / failure patterns are deliberately **not** in this schema.
    They are first-class Insight entities owned by the insights plugin.
    """

    # The ``model`` field below collides with Pydantic's reserved
    # ``model_*`` namespace. We turn the protection off rather than rename
    # the field, because the on-disk section name has to be ``Model``.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    name: str = Field(
        min_length=1,
        description="Canonical agent name registered with NeMo Platform.",
    )
    eval_command: str | None = Field(
        default=None,
        description=(
            "CLI one-liner that runs the agent's eval suite. Optional at "
            "explore time; the eval-setup skill fills it later if absent."
        ),
    )

    job: str = Field(
        min_length=_MIN_JOB_LENGTH,
        description="One concrete sentence describing what the agent does.",
    )
    audience: str = Field(
        min_length=1,
        description="Who talks to the agent. Shapes tone and safety surface.",
    )
    categories: list[str] = Field(
        min_length=3,
        max_length=6,
        description="3-6 task buckets the agent handles.",
    )
    tools: str = Field(
        min_length=1,
        description=(
            "Tools the agent can call, rendered as a markdown table, or the "
            "literal string 'Prompt-only.' Default at explore time is "
            "prompt-only plus ``current_datetime``."
        ),
    )
    model: ModelChoice
    framework: Framework = Field(
        description=(
            "Resolved framework status. Required. Marked planned-deprecation — see :class:`Framework` for why."
        ),
        json_schema_extra={"x-planned-deprecation": "tracked under FP-161"},
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Negative requirements. Empty list is allowed but rare.",
    )
    success_criteria: list[str] = Field(
        min_length=1,
        description=(
            "Concrete check questions with good-answer descriptions, or named "
            "metric thresholds (e.g. ``tool_call_accuracy >= 0.85``)."
        ),
    )
    allowed_changes: AllowedChanges = Field(default_factory=AllowedChanges)
    feedback_signals: str | None = Field(
        default=None,
        description=("How the analyst should prioritize issues. 'defaults' if the user has nothing specific."),
    )
    eval_command_notes: str | None = Field(
        default=None,
        description=(
            "Free-form context on eval state when the suite is not well-"
            "defined yet (coverage gaps, why). The runnable command lives in "
            "``eval_command``."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Unresolved items the build skill should know about.",
    )

    @field_validator("job")
    @classmethod
    def _validate_job(cls, value: str) -> str:
        # Two post-strip checks. The vague-phrase check runs first so a
        # whitespace-padded vague phrase ("   help with stuff   ") surfaces
        # the more useful diagnosis rather than the length floor.
        #
        # The length floor itself is re-enforced here because Pydantic's
        # built-in ``min_length`` runs against the raw value, so padded
        # short strings would otherwise bypass it.
        stripped = value.strip()
        if stripped.lower() in _VAGUE_JOB_PHRASES:
            raise ValueError(
                f"'job' is too vague ({stripped!r}). Write one concrete sentence "
                "describing what the agent actually does."
            )
        if len(stripped) < _MIN_JOB_LENGTH:
            raise ValueError(
                f"'job' must be at least {_MIN_JOB_LENGTH} characters after trimming "
                f"(got {len(stripped)}). Write one concrete sentence describing what "
                "the agent does."
            )
        return stripped

    @field_validator("categories")
    @classmethod
    def _strip_categories(cls, value: list[str]) -> list[str]:
        cleaned = [c.strip() for c in value if c and c.strip()]
        if len(cleaned) != len(value):
            raise ValueError("'categories' contains empty entries")
        return cleaned
