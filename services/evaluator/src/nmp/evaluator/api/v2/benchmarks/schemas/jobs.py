# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job input schemas for benchmark evaluation."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, TypeGuard

from nemo_evaluator_sdk.values import (
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
    SupportedJobTypes,
)
from nmp.evaluator.api.v2.common.inline_models import Agent, Model
from nmp.evaluator.app.values import (
    BenchmarkRef,
    ModelRef,
)
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter


class _BenchmarkJobBase(BaseModel):
    """Base input for a benchmark evaluation job."""

    model_config = ConfigDict(extra="forbid", json_schema_mode_override="validation")
    benchmark: BenchmarkRef = Field(description="Reference to the benchmark for evaluation (format: workspace/name).")


# TODO: Align optional_fields with template path semantics.
# Keep support for dataset-relative nested paths (for example "reference.text")
# and runtime sample paths (for example "sample.output_text"), while avoiding
# dependence on the "item." alias form (normalize "item.foo" -> "foo").
OptionalFieldName = Annotated[str, Field(min_length=1)]


class BenchmarkOfflineJob(_BenchmarkJobBase):
    """Input for an offline benchmark evaluation job.

    Evaluates the benchmark's dataset against all metrics in the benchmark.
    """

    params: RunConfig | None = Field(
        default_factory=RunConfig, description="Execution parameters for the benchmark job."
    )
    __job_type__: ClassVar[Literal[SupportedJobTypes.OFFLINE]] = SupportedJobTypes.OFFLINE


class _BenchmarkOnlineJob(_BenchmarkJobBase):
    """Base input for an online benchmark evaluation job."""

    model: Model | ModelRef = Field(description="The model to evaluate.")
    params: RunConfigOnlineModel | None = Field(
        default_factory=RunConfigOnlineModel, description="Execution parameters for the benchmark job."
    )


class BenchmarkOnlineJob(_BenchmarkOnlineJob):
    """Input for an online benchmark evaluation job.

    Evaluates a model by prompting it with the benchmark's dataset and then evaluating
    the responses against all metrics in the benchmark.
    """

    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE

    prompt_template: str | dict = Field(
        description="The jinja template to prompt the model for evaluation. Can be either a simple string or a structured object (e.g., OpenAI messages format). Use Jinja template variables like {{input}}, {{output}}, {{context}}, {{reference}} to reference input columns.",
        examples=[
            {"type": "string", "content": "Question: {{input}}\nAnswer: "},
            {
                "type": "object",
                "content": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Question: {{input}}\nAnswer: ",
                        },
                    ]
                },
            },
        ],
    )
    optional_fields: list[OptionalFieldName] = Field(
        default_factory=list,
        description=(
            "Prompt template fields that should remain available to the prompt template but not be "
            "required by dataset schema validation."
        ),
    )


class BenchmarkOnlineAgentJob(_BenchmarkJobBase):
    """Input for an online benchmark evaluation job targeting an agent.

    Evaluates an agent by prompting it with the benchmark's dataset and then evaluating
    the responses against all metrics in the benchmark.
    """

    agent: Agent = Field(description="The agent to evaluate.")
    params: RunConfigOnline | None = Field(
        default_factory=RunConfigOnline, description="Execution parameters for the benchmark job."
    )
    prompt_template: str | dict = Field(
        description="The jinja template to prompt the agent for evaluation. Can be either a simple string or a structured object (e.g., OpenAI messages format). Use Jinja template variables like {{input}}, {{output}}, {{context}}, {{reference}} to reference input columns.",
        examples=[
            {"type": "string", "content": "Question: {{input}}\nAnswer: "},
            {
                "type": "object",
                "content": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Question: {{input}}\nAnswer: ",
                        },
                    ]
                },
            },
        ],
    )
    optional_fields: list[OptionalFieldName] = Field(
        default_factory=list,
        description=(
            "Prompt template fields that should remain available to the prompt template but not be "
            "required by dataset schema validation."
        ),
    )
    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE


def _benchmark_job_discriminator(data: Any) -> str:
    """
    Discriminate union type specifically for API input job spec which has benchmark references.
    """
    if isinstance(data, dict):
        has_model = "model" in data
        has_agent = "agent" in data
    else:
        has_model = hasattr(data, "model")
        has_agent = hasattr(data, "agent")

    if has_agent and has_model:
        raise ValueError("Only one of 'model' or 'agent' may be specified, not both.")

    if has_agent:
        return "online-agent"

    if has_model:
        return "online"
    return "offline"


BenchmarkJob = Annotated[
    (
        Annotated[BenchmarkOfflineJob, Tag("offline")]
        | Annotated[BenchmarkOnlineJob, Tag("online")]
        | Annotated[BenchmarkOnlineAgentJob, Tag("online-agent")]
    ),
    Discriminator(_benchmark_job_discriminator),
]
BenchmarkJobAdapter = TypeAdapter(BenchmarkJob)


def benchmark_job_type(job: BenchmarkJob) -> SupportedJobTypes:
    """Return the supported evaluator job type for a benchmark job schema."""
    if isinstance(job, BenchmarkOnlineJob | BenchmarkOnlineAgentJob):
        return SupportedJobTypes.ONLINE
    return SupportedJobTypes.OFFLINE


def is_online_benchmark_job(job: BenchmarkJob) -> TypeGuard[BenchmarkOnlineJob | BenchmarkOnlineAgentJob]:
    """Return True when the job schema carries a prompt_template override."""
    return isinstance(job, BenchmarkOnlineJob | BenchmarkOnlineAgentJob)
