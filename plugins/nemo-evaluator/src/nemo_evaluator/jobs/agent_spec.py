# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Spec and target models for the agent-evaluation job.

These are the wire (submitter-facing) and canonical (resolved) DTOs that
:class:`~nemo_evaluator.jobs.agent_evaluate.AgentEvalJob` validates and runs,
plus the ``Target`` union describing what generates trials. They live in their
own module so the job and its compiler can both depend on them without importing
each other.
"""

from __future__ import annotations

from typing import Any, Literal, Self, TypeAlias

# Imported for their registration side effects: each module registers its bundle
# payload kind so MetricBundle payloads round-trip through validation.
import nemo_evaluator.shared.metric_bundles.cloudpickle  # noqa: F401
import nemo_evaluator.shared.metric_bundles.inline  # noqa: F401
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.jobs.metric_resolution import to_runtime_bundle, unresolved_model_refs
from nemo_evaluator.metric_refs import MetricRefOrInline
from nemo_evaluator.shared.metric_bundles.bundles import unbundle_metric
from nemo_evaluator_sdk.agent_eval.tasks import SemanticView
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial
from nemo_evaluator_sdk.values import Agent, Model, RunConfigOnline, RunConfigOnlineModel
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelTarget(BaseModel):
    """Generate trials by calling a Model (OpenAI-compatible) endpoint.

    The prompt template *is* the request sent to the model, so it lives here with the endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["model"] = "model"
    model: Model = Field(description="The model endpoint to generate trials against.")
    prompt_template: str | dict[str, Any] | None = Field(
        default=None,
        description="How each task maps to the chat/completion request. Defaults to a single user "
        "message carrying the task prompt when omitted.",
    )
    params: RunConfigOnlineModel | None = Field(
        default=None, description="Optional online-inference parameters for trial generation."
    )


class AgentTarget(BaseModel):
    """Generate trials by calling a generic HTTP or NeMo Agent Toolkit target.

    The selected agent variant owns its request and response profile, so there is no
    separate prompt template here.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["agent"] = "agent"
    agent: Agent = Field(description="The agent endpoint to generate trials against.")
    params: RunConfigOnline | None = Field(
        default=None, description="Optional online-inference parameters for trial generation."
    )


class CodexRunnerTarget(BaseModel):
    """Generate trials by driving the Codex CLI agent runner."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["codex"] = "codex"
    model: str | None = Field(
        default=None, description="Codex model to use (e.g. 'gpt-5.5'); CLI default when omitted."
    )
    timeout_s: int = Field(default=600, ge=1, description="Per-task timeout for the Codex CLI, in seconds.")


#: The agent-runner slot of the target union — the spec-side mirror of ``AgentTaskRunner``, resolved
#: to a runtime at run time. One member today; widen to a ``kind``-union as more runners land.
AgentRunnerTarget: TypeAlias = CodexRunnerTarget

#: What generates trials: a Model or Agent endpoint, or an agent runner. ``kind``-discriminated, and
#: the spec-level analog of the SDK's runtime ``AgentEvalTarget`` (Model | Agent | AgentTaskRunner).
Target: TypeAlias = ModelTarget | AgentTarget | AgentRunnerTarget


class _AgentEvalTaskCommon(BaseModel):
    """Fields shared by the submitter and canonical task DTOs (everything but ``metrics``).

    ``metrics`` differs between the two (refs allowed vs. fully resolved), so — as
    with ``EvaluateInputSpec``/``EvaluateSpec`` — the variants are siblings that add
    it, not a subtype pair (a mutable field can't be narrowed across inheritance).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable task identifier, unique within the task collection.")
    intent: str = Field(description="Human-readable description of the desired agent behavior.")
    inputs: dict[str, Any] = Field(description="What the agent receives or starts from (instruction, seed, refs).")
    views: dict[str, SemanticView] = Field(
        default_factory=dict,
        description="Optional reporting views mapping this task's metric outputs into named semantic scores.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form metadata associated with the task.")


class AgentEvalTaskInput(_AgentEvalTaskCommon):
    """Submitter-facing task DTO: metrics may be inline bundles or stored-metric references."""

    metrics: list[MetricRefOrInline] = Field(
        default_factory=list,
        description="Metrics that score this task, inline and/or references to stored metrics.",
    )


class AgentEvalTaskSpec(_AgentEvalTaskCommon):
    """Canonical task DTO: metrics fully resolved to inline bundles, reconstructed at run time."""

    metrics: list[MetricInline] = Field(
        default_factory=list,
        description="Inline metric bundles that score this task; reconstructed to runtime metrics at run time.",
    )


class _AgentEvalSpecCommon(BaseModel):
    """Fields shared by the submitter input and canonical agent-eval specs (everything but ``tasks``)."""

    # ``oneOf`` mirrors the ``_require_exactly_one_trial_source`` validator into the OpenAPI schema, so
    # the generated contract (and clients) reject a target-less or both-supplied request instead of
    # only discovering it via a 422 at runtime. Each branch also excludes an explicit ``null`` (the
    # validator keys off non-null, not mere presence), so a request that sends ``"target": null``
    # alongside ``trials`` is accepted by the schema exactly as the runtime accepts it.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {"required": ["target"], "properties": {"target": {"not": {"type": "null"}}}},
                {"required": ["trials"], "properties": {"trials": {"not": {"type": "null"}}}},
            ]
        },
    )

    target: Target | None = Field(
        default=None,
        description="What generates trials online: a Model or Agent endpoint, or an agent runner (e.g. Codex "
        "CLI). Endpoint targets carry their own request config (prompt template / inference params). "
        "Mutually exclusive with `trials`.",
    )
    trials: list[AgentEvalTrial] | None = Field(
        default=None,
        description="Precomputed trials to score directly (offline eval), instead of generating them from a "
        "`target`. Mutually exclusive with `target`.",
    )
    max_concurrent_tasks: int = Field(
        default=4,
        ge=1,
        description="Maximum number of tasks evaluated concurrently. Distinct from a target's "
        "`params.parallelism`, which bounds concurrent inference requests *within* trial generation.",
    )
    fail_fast: bool = Field(default=False, description="Stop the run on the first scoring failure when True.")
    benchmark: dict[str, Any] = Field(default_factory=dict, description="Benchmark metadata recorded with the run.")

    @model_validator(mode="after")
    def _require_exactly_one_trial_source(self) -> Self:
        # The SDK evaluator requires exactly one of trials/target (one generates trials online, the
        # other scores precomputed ones); enforce it at the spec boundary so a target-less or
        # both-supplied spec is rejected at validation rather than failing inside the run.
        if (self.target is None) == (self.trials is None):
            raise ValueError(
                "provide exactly one of `target` (generate trials online) or `trials` (score precomputed trials)"
            )
        return self


class AgentEvalInputSpec(_AgentEvalSpecCommon):
    """Submitter-facing agent-evaluation input: tasks whose metrics may be inline or references."""

    tasks: list[AgentEvalTaskInput] = Field(min_length=1, description="Tasks to evaluate; at least one is required.")


class AgentEvalSpec(_AgentEvalSpecCommon):
    """Canonical agent-evaluation spec: tasks with all metric references resolved to inline."""

    tasks: list[AgentEvalTaskSpec] = Field(min_length=1, description="Tasks to evaluate; at least one is required.")

    @model_validator(mode="after")
    def _reject_unresolved_metric_model_refs(self) -> Self:
        for task in self.tasks:
            unresolved = unresolved_model_refs([unbundle_metric(to_runtime_bundle(metric)) for metric in task.metrics])
            if unresolved:
                raise ValueError(
                    f"AgentEvalSpec task {task.id!r} metric models must be resolved before run: "
                    + ", ".join(unresolved)
                )
        return self
