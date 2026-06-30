# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent-related value types."""

# ruff: noqa: I001 - the vendored SDK mirror uses different import-order settings.

from __future__ import annotations

import os
from functools import cached_property
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nemo_evaluator_sdk.enums import AgentFormat
from nemo_evaluator_sdk.values.common import SecretRef


class NatAgentConfig(BaseModel):
    """NeMo Agent Toolkit request and stream handling configuration."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(
        default="/generate/full",
        description="Relative path below agent.url, or an absolute NAT endpoint URL.",
    )
    request_mode: Literal["input_message", "passthrough"] = Field(
        default="input_message",
        description="Derive the legacy input_message payload or send the rendered request unchanged.",
    )
    query_params: dict[str, str] = Field(
        default_factory=lambda: {"filter_steps": "none"},
        description="Query parameters sent to the NAT endpoint.",
    )
    response_path: str = Field(
        default="$.value",
        description="JSONPath applied to data-channel payloads; the last match is the final output.",
    )
    capture_evidence: bool = Field(
        default=False,
        description="Capture raw and parsed stream evidence for agent-eval trials.",
    )


class Agent(BaseModel):
    """Agent definition for inference in online evaluation jobs.

    An agent is an endpoint that accepts a request and returns a response,
    potentially with a trajectory. Two formats are supported:

    - ``generic``: configurable HTTP POST with Jinja-templated body and
      JSONPath extraction for response and trajectory.
    - ``nemo_agent_toolkit``: NeMo Agent Toolkit SSE streaming protocol
      (``/generate/full?filter_steps=none``).
    """

    # TODO: Much of this is duplicated between agent and model. Once we have aligned on model defination.
    # the duplication can be removed by defining EndPoint class and reusing it across both model and agent.
    #
    # ``allOf``/``if``/``then`` mirrors the ``_validate_generic_fields`` validator into the OpenAPI
    # schema: a generic-format agent must carry ``body`` + ``response_path`` (the generic HTTP path
    # needs them), so the contract rejects a ``url``-only generic agent rather than only failing later.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"format": {"const": "generic"}}},
                    "then": {"required": ["body", "response_path"]},
                }
            ]
        },
    )

    url: str = Field(description="Base URL of the agent endpoint.")
    name: str = Field(description="Agent name / identifier.")
    format: Literal[AgentFormat.GENERIC, AgentFormat.NEMO_AGENT_TOOLKIT] = Field(
        default=AgentFormat.GENERIC, description="Agent format that determines the execution path."
    )
    api_key_secret: SecretRef | None = Field(
        default=None,
        description="API key secret reference for the agent. Format: workspace/secret_name or secret_name within the job workspace.",
    )

    # Generic agent fields
    body: dict | None = Field(
        default=None,
        description="Jinja template for the request payload. Required for generic agents.",
    )
    response_path: str | None = Field(
        default=None,
        description="JSONPath expression to extract the response text from the agent's response body. Required for generic agents.",
    )
    trajectory_path: str | None = Field(
        default=None,
        description="JSONPath expression to extract the trajectory from the agent's response body. Optional.",
    )
    nat: NatAgentConfig | None = Field(
        default=None,
        description="Optional NAT endpoint and stream configuration; defaults preserve /generate/full behavior.",
    )

    # TODO: When agent is type NAT, prefill body, response_path and trajectory_path depending on url ends with generate or generate/full.
    @model_validator(mode="after")
    def _validate_generic_fields(self) -> Agent:
        if self.format == AgentFormat.GENERIC:
            if self.nat is not None:
                raise ValueError("'nat' is only valid when agent format is 'nemo_agent_toolkit'.")
            if self.body is None:
                raise ValueError("'body' is required when agent format is 'generic'.")
            if self.response_path is None:
                raise ValueError("'response_path' is required when agent format is 'generic'.")
        return self

    @cached_property
    def api_key_env(self) -> str | None:
        if self.api_key_secret:
            env_name = self.api_key_secret.root
            if env_name[0].isdigit():
                env_name = f"_{env_name}"
            return env_name.replace("-", "_").replace("/", "_")
        return None

    @cached_property
    def api_key(self) -> str | None:
        if self.api_key_secret:
            api_key_env = self.api_key_env
            if api_key_env is None:
                raise ValueError("api_key_env must be set when api_key_secret is provided")
            return os.getenv(api_key_env)
        return None
