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

# A "role" answer below this length is almost always too vague to be useful
# downstream (e.g. "help with stuff", "answer questions"). The exact cutoff is
# a heuristic — the real guard is the vague-phrase check in
# :meth:`AgentSpec._validate_role`.
_MIN_ROLE_LENGTH = 20

# Vague stems we reject outright. Match is case-insensitive on the full
# (stripped) role string.
_VAGUE_ROLE_PHRASES = frozenset(
    {
        "help with stuff",
        "help users",
        "answer questions",
        "do things",
        "be helpful",
        "assist users",
    }
)


class Harness(BaseModel):
    """The model-surrounding execution layer that turns a model into an agent.

    In current agent terminology, the harness is the extra-model layer that
    manages the agent loop, tool dispatch, context/state, orchestration,
    guardrails, observability, recovery, and verification. It is descriptive
    standard metadata, not a NeMo Platform capability gate.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        min_length=1,
        description=(
            "Human-readable description of the extra-model layer that makes "
            "the model behave as an agent: loop, tools, context, state, "
            "constraints, observation, and validation."
        ),
    )
    agent_loop: str | None = Field(
        default=None,
        description="How model calls, tool calls, observations, retries, and stop conditions are orchestrated.",
    )
    tool_dispatch: str | None = Field(
        default=None,
        description="How tool calls are validated, routed, executed, and returned to the model.",
    )
    context_management: str | None = Field(
        default=None,
        description="How prompts, conversation history, retrieval, compaction, and context windows are managed.",
    )
    state_management: str | None = Field(
        default=None,
        description="How session state, memory, artifacts, or durable workspace state are stored and reused.",
    )
    guardrails: str | None = Field(
        default=None,
        description="Permission, safety, policy, sandboxing, or middleware controls enforced around agent actions.",
    )
    observability: str | None = Field(
        default=None,
        description="Tracing, logging, metrics, replay, or audit data emitted by the harness.",
    )
    verification: str | None = Field(
        default=None,
        description="Checks, validators, tests, self-verification, or recovery loops run before work is accepted.",
    )
    runtime: str | None = Field(
        default=None,
        description=(
            "Runtime or execution environment, e.g. NAT workflow, FastAPI "
            "service, hosted vendor agent, CLI command, notebook, or unknown."
        ),
    )
    notes: str | None = Field(
        default=None,
        description="Free-form notes — caveats, recovery behavior, budget controls, or other harness details.",
    )


class FrameworkResolution(str, Enum):
    """Temporary NeMo Platform framework compatibility status.

    This field exists while NeMo Platform's build path supports only
    LangGraph-wrapped NAT agents. It is expected to relax or disappear as
    broader framework support lands; do not treat it as part of the portable
    AGENTSpec standard.
    """

    LANGGRAPH_NAT = "langgraph-nat"
    """LangGraph wrapped in NVIDIA NeMo Agent Toolkit (NAT) — the supported
    NeMo build path today."""

    NEEDS_WRAPPER = "needs-wrapper"
    """The agent is in another framework (CrewAI, AutoGen, plain LangChain,
    Pydantic AI, custom service, etc.) and needs a user-written NAT wrapper
    before ``nemo-build-agent`` can do anything useful."""


class Framework(BaseModel):
    """Temporary NeMo-specific framework compatibility hint."""

    model_config = ConfigDict(extra="forbid")

    resolution: FrameworkResolution
    source_framework: str | None = Field(
        default=None,
        description=(
            "Name of the source framework (e.g. 'crewai', 'autogen', "
            "'langchain', 'pydantic-ai', 'custom service') when resolution "
            "is ``needs-wrapper``. Ignored otherwise."
        ),
    )
    notes: str | None = Field(
        default=None,
        description="Free-form notes — wrapper plan, version constraints, migration path, etc.",
    )


class Scope(BaseModel):
    """Who the agent serves and which work it should, and should not, cover."""

    model_config = ConfigDict(extra="forbid")

    audience: str = Field(
        min_length=1,
        description="Who talks to the agent. Shapes tone, assumptions, and safety surface.",
    )
    categories: list[str] = Field(
        min_length=3,
        max_length=6,
        description="3-6 task buckets the agent handles; useful for analysis, routing, and reporting.",
    )
    in_scope: list[str] = Field(
        default_factory=list,
        description="Capabilities, user intents, or situations the agent is expected to handle.",
    )
    out_of_scope: list[str] = Field(
        default_factory=list,
        description=(
            "Capabilities, user intents, or situations the agent should not handle. "
            "Use this to keep analysts from filing intended non-goals as failures."
        ),
    )

    @field_validator("categories", "in_scope", "out_of_scope")
    @classmethod
    def _strip_non_empty_list(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != len(value):
            raise ValueError("list contains empty entries")
        return cleaned


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


class ChangeScope(BaseModel):
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
        description=(
            "Free-form notes — vetoes, exceptions, human approval requirements, "
            "or other scope clarifications."
        ),
    )


class AgentSpec(BaseModel):
    """The canonical agent spec, written to ``agents/<name>.spec.md``.

    Field order on the class matches the on-disk section order. ``name`` and
    ``eval_command`` render as YAML front matter; all other fields render as
    ``##`` body sections in declared order.

    The two hard preconditions for handoff to ``nemo-spec`` are ``role`` and
    the temporary NeMo-specific ``framework`` compatibility field — both must
    validate before the spec is written.

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

    role: str = Field(
        min_length=_MIN_ROLE_LENGTH,
        description="One concrete sentence describing the role this agent plays for its users.",
    )
    purpose: str = Field(
        min_length=1,
        description=(
            "One or two short paragraphs explaining why the agent exists, what "
            "user value it provides, and the decision or workflow context it supports."
        ),
    )
    scope: Scope = Field(description="Audience, task categories, and explicit in/out boundaries.")
    tools: str = Field(
        min_length=1,
        description=(
            "Tools, APIs, and knowledge sources the agent can use, rendered as "
            "markdown. Include purpose, credentials/scopes, side effects, data "
            "freshness, expected failures, and external knowledge sources where relevant. "
            "Use the literal string 'Prompt-only.' if none."
        ),
    )
    model: ModelChoice
    framework: Framework = Field(
        description=(
            "Temporary NeMo Platform framework compatibility hint. This is "
            "not intended to be a permanent part of the portable AGENTSpec "
            "standard; it exists until NeMo Platform supports more agent frameworks."
        ),
        json_schema_extra={"x-planned-deprecation": "temporary until broader framework support"},
    )
    harness: Harness | None = Field(
        default=None,
        description=(
            "Optional description of the extra-model execution layer: agent "
            "loop, tool dispatch, context/state, guardrails, observability, "
            "verification, and runtime."
        ),
    )
    behavior: str = Field(
        min_length=1,
        description=(
            "Behavioral rules and boundaries: constraints, refusal and escalation "
            "policy, tone, safety/compliance requirements, accepted limitations, "
            "and known non-goals."
        ),
    )
    success_criteria: str = Field(
        min_length=1,
        description=(
            "What good production behavior looks like for this agent, independent "
            "of the current eval suite. Capture desired user outcomes, quality "
            "standards, escalation quality, accuracy expectations, latency or cost "
            "expectations where relevant, and representative examples of success."
        ),
    )
    evaluation_setup: str = Field(
        min_length=1,
        description=(
            "The current validation setup: how to run it, what datasets or "
            "checks it uses, what its scorers or metrics measure, pass/fail "
            "thresholds, and known coverage gaps relative to the success criteria. "
            "State explicitly if no eval suite is wired yet."
        ),
    )
    change_scope: ChangeScope = Field(default_factory=ChangeScope)
    signals: str | None = Field(
        default=None,
        description=(
            "How observers and analyst agents should interpret telemetry, user "
            "feedback, eval outcomes, and trace patterns. Include high-priority "
            "signals, noisy signals to ignore, and agent identity details if needed."
        ),
    )
    unresolved_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Optional unresolved facts that affect safe use, evaluation, or "
            "modification of the agent. Remove items once answered."
        ),
    )

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        # Two post-strip checks. The vague-phrase check runs first so a
        # whitespace-padded vague phrase ("   help with stuff   ") surfaces
        # the more useful diagnosis rather than the length floor.
        #
        # The length floor itself is re-enforced here because Pydantic's
        # built-in ``min_length`` runs against the raw value, so padded
        # short strings would otherwise bypass it.
        stripped = value.strip()
        if stripped.lower() in _VAGUE_ROLE_PHRASES:
            raise ValueError(
                f"'role' is too vague ({stripped!r}). Write one concrete sentence "
                "describing the role this agent plays for its users."
            )
        if len(stripped) < _MIN_ROLE_LENGTH:
            raise ValueError(
                f"'role' must be at least {_MIN_ROLE_LENGTH} characters after trimming "
                f"(got {len(stripped)}). Write one concrete sentence describing what "
                "role the agent plays."
            )
        return stripped
