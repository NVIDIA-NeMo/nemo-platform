# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent-related value types."""

# ruff: noqa: I001 - the vendored SDK mirror uses different import-order settings.

from __future__ import annotations

import os
from functools import cached_property
from typing import Any, Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from nemo_platform.beta.evaluator.enums import AgentFormat
from nemo_platform.beta.evaluator.values.common import SecretRef


def _require_format_in_json_schema(schema: dict[str, Any]) -> None:
    """Require the discriminator in serialized agent payloads."""
    required = schema.setdefault("required", [])
    if "format" not in required:
        required.append("format")


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


class AgentBase(BaseModel):
    """Fields shared by every inference agent target."""

    # TODO: Much of this is duplicated between agent and model. Once we have aligned on model defination.
    # the duplication can be removed by defining EndPoint class and reusing it across both model and agent.
    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="Base URL of the agent endpoint.")
    name: str = Field(description="Agent name / identifier.")
    api_key_secret: SecretRef | None = Field(
        default=None,
        description="API key secret reference for the agent. Format: workspace/secret_name or secret_name within the job workspace.",
    )

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
        api_key_env = self.api_key_env
        return os.getenv(api_key_env) if api_key_env is not None else None


class GenericAgent(AgentBase):
    """Configurable HTTP agent with optional JSON SSE response handling."""

    model_config = ConfigDict(json_schema_extra=_require_format_in_json_schema)

    format: Literal[AgentFormat.GENERIC] = AgentFormat.GENERIC
    body: dict[str, Any] = Field(description="Jinja template for the request payload.")
    response_path: str = Field(description="JSONPath expression used to extract the response value.")
    trajectory_path: str | None = Field(
        default=None,
        description="Optional JSONPath expression used to extract trajectory data.",
    )
    stream: bool = Field(
        default=False,
        description="Read JSON SSE data frames instead of a single JSON response body.",
    )


class NemoAgentToolkitAgent(AgentBase):
    """NeMo Agent Toolkit target normalized to the shared streaming transport."""

    model_config = ConfigDict(json_schema_extra=_require_format_in_json_schema)

    format: Literal[AgentFormat.NEMO_AGENT_TOOLKIT] = AgentFormat.NEMO_AGENT_TOOLKIT
    nat: NatAgentConfig | None = Field(
        default=None,
        description="Optional NAT endpoint and stream configuration; defaults preserve /generate/full behavior.",
    )


Agent: TypeAlias = Annotated[
    GenericAgent | NemoAgentToolkitAgent,
    Field(discriminator="format"),
]
