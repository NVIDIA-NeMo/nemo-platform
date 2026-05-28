# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from nemo_evaluator_sdk.values import (
    Agent,
    FieldMapping,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
    SupportedJobTypes,
)
from nmp.evaluator.app.values.common import FilesetRef, MetricRef, ModelRef
from nmp.evaluator.app.values.datasets import Dataset
from nmp.evaluator.app.values.metrics import Metric
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter


class _MetricJob(BaseModel):
    """Job to run a metric evaluation."""

    model_config = ConfigDict(extra="forbid")
    metric: Metric = Field(description="The metric for evaluation.")
    metric_ref: MetricRef | None = Field(default=None)
    metric_params: dict = Field(
        default_factory=dict,
        description="Additional parameter overrides for the metric.",
    )
    field_mapping: FieldMapping | None = Field(
        default=None,
        description="Maps canonical evaluator fields such as 'input' and 'output' to dataset column paths for this job.",
    )


OptionalFieldName = Annotated[str, Field(min_length=1)]


class MetricOfflineJob(_MetricJob):
    __job_type__: ClassVar[Literal[SupportedJobTypes.OFFLINE]] = SupportedJobTypes.OFFLINE

    dataset: Dataset = Field(description="The dataset to evaluate which may represent generated outputs from a model.")
    dataset_ref: FilesetRef | None = Field(default=None)
    params: RunConfig = Field(default_factory=RunConfig, description="Execution parameters for the metric job.")


class MetricOnlineJob(_MetricJob):
    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE

    model: Model = Field(description="The model to evaluate.")
    model_ref: ModelRef | None = Field(default=None)
    dataset: Dataset = Field(description="The dataset to use for model prompts and evaluation.")
    dataset_ref: FilesetRef | None = Field(default=None)
    params: RunConfigOnlineModel = Field(
        default_factory=RunConfigOnlineModel, description="Execution parameters for the metric job."
    )
    prompt_template: str | dict[str, Any] = Field(
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


class MetricOnlineAgentJob(_MetricJob):
    """Online metric job targeting an agent."""

    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE

    agent: Agent = Field(description="The agent to evaluate.")
    dataset: Dataset = Field(description="The dataset to use for agent prompts and evaluation.")
    dataset_ref: FilesetRef | None = Field(default=None)
    params: RunConfigOnline = Field(
        default_factory=RunConfigOnline, description="Execution parameters for the metric job."
    )
    prompt_template: str | dict[str, Any] = Field(
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


def _discriminate_job_type_from_fields(data: dict) -> str:
    """Determine job type from field presence in a dict.

    Logic:
    - agent only (no model) -> Online agent job
    - model or agent (with or without prompt_template) -> Online job
    - otherwise -> Offline job

    Note: Routing 'model'/'agent' without 'prompt_template' to Online gives a
    better validation error ("missing prompt_template") vs Offline ("extra field model").
    """
    has_model = "model" in data
    has_agent = "agent" in data

    if has_agent and has_model:
        raise ValueError("Only one of 'model' or 'agent' may be specified, not both.")
    if has_agent:
        return "online-agent"
    if has_model:
        return "online"
    return "offline"


def _metric_job_discriminator(v: Any) -> str:
    """Discriminator for MetricJob union types."""
    if isinstance(v, dict):
        return _discriminate_job_type_from_fields(v)
    if isinstance(v, MetricOnlineAgentJob):
        return "online-agent"
    return getattr(v, "__job_type__", SupportedJobTypes.OFFLINE).value


MetricJob = Annotated[
    Annotated[MetricOfflineJob, Tag("offline")]
    | Annotated[MetricOnlineJob, Tag("online")]
    | Annotated[MetricOnlineAgentJob, Tag("online-agent")],
    Discriminator(_metric_job_discriminator),
]
MetricJobAdapter = TypeAdapter(MetricJob)
