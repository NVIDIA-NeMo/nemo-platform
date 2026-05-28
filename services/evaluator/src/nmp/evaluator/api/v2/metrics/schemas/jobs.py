# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

import nmp.evaluator.app.values as app
from nemo_evaluator_sdk.values import (
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
    SupportedJobTypes,
)
from nmp.evaluator.api.v2.common.inline_models import Agent
from nmp.evaluator.api.v2.metrics.schemas.metrics import (
    Metric,
    WithModel,
)
from nmp.evaluator.app.values.metrics_job import _discriminate_job_type_from_fields
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter


class _MetricJobBase(BaseModel):
    """A metric job."""

    model_config = ConfigDict(extra="forbid", json_schema_mode_override="validation")
    metric: app.MetricRef | Metric = Field(description="The metric for evaluation.")
    metric_params: dict = Field(
        default_factory=dict,
        description="Additional parameter overrides for the metric.",
    )
    field_mapping: app.FieldMapping | None = Field(
        default=None,
        description="Maps canonical evaluator fields such as 'input' and 'output' to dataset column paths for this job.",
    )


# TODO: Align optional_fields with template path semantics.
# Keep support for dataset-relative nested paths (for example "reference.text")
# and runtime sample paths (for example "sample.output_text"), while avoiding
# dependence on the "item." alias form (normalize "item.foo" -> "foo").
OptionalFieldName = Annotated[str, Field(min_length=1)]


class MetricOfflineJob(_MetricJobBase):
    """An offline metric job."""

    __job_type__: ClassVar[Literal[SupportedJobTypes.OFFLINE]] = SupportedJobTypes.OFFLINE

    dataset: app.Dataset = Field(
        description="The dataset to evaluate which may represent generated outputs from a model."
    )
    params: RunConfig | None = Field(default_factory=RunConfig, description="Execution parameters for the metric job.")


class MetricOnlineJob(WithModel, _MetricJobBase):
    """A online metric job."""

    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE

    dataset: app.Dataset = Field(description="The dataset to use for model prompts and evaluation.")
    params: RunConfigOnlineModel | None = Field(
        default_factory=RunConfigOnlineModel, description="Execution parameters for the metric job."
    )
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


class MetricOnlineAgentJob(_MetricJobBase):
    """An online metric job that evaluates an agent."""

    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE

    agent: Agent = Field(description="The agent to evaluate.")
    dataset: app.Dataset = Field(description="The dataset to use for agent prompts and evaluation.")
    params: RunConfigOnline | None = Field(
        default_factory=RunConfigOnline, description="Execution parameters for the metric job."
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


def _metric_job_input_discriminator(v: Any) -> str:
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
    Discriminator(_metric_job_input_discriminator),
]
MetricJobAdapter = TypeAdapter(MetricJob)
