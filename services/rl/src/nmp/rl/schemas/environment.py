# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Environment FileSet manifest schemas (native-v1, wheels-v1, adapter-wheels-v1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class EnvironmentFormat(StrEnum):
    NATIVE_V1 = "native-v1"
    WHEELS_V1 = "wheels-v1"
    ADAPTER_WHEELS_V1 = "adapter-wheels-v1"


class EnvironmentManifestMetadata(BaseModel):
    """User/provenance metadata in nemo-environment.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    hub_id: str | None = None
    vf_env_id: str | None = None
    adapter_agent: str | None = None


class _ManifestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_paths: list[str] = Field(min_length=1)
    metadata: EnvironmentManifestMetadata

    @field_validator("config_paths")
    @classmethod
    def _relative_contained_paths(cls, paths: list[str]) -> list[str]:
        for p in paths:
            if not p or p.startswith("/") or p.startswith("\\") or ".." in p.split("/"):
                raise ValueError(f"config_paths entry must be relative and contained: {p!r}")
        return paths


class NativeV1Manifest(_ManifestBase):
    format: Literal[EnvironmentFormat.NATIVE_V1] = EnvironmentFormat.NATIVE_V1

    @field_validator("config_paths")
    @classmethod
    def _under_gym_dirs(cls, paths: list[str]) -> list[str]:
        allowed = ("responses_api_agents/", "resources_servers/", "responses_api_models/")
        for p in paths:
            if not p.startswith(allowed):
                raise ValueError(f"native-v1 config_paths must be under {allowed}: {p!r}")
        return paths


class WheelsV1Manifest(_ManifestBase):
    format: Literal[EnvironmentFormat.WHEELS_V1] = EnvironmentFormat.WHEELS_V1


class AdapterRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1)
    agent_type: Literal["responses_api_agents"] = "responses_api_agents"
    image_config_root: str | None = None


class AdapterWheelsV1Manifest(_ManifestBase):
    format: Literal[EnvironmentFormat.ADAPTER_WHEELS_V1] = EnvironmentFormat.ADAPTER_WHEELS_V1
    adapter: AdapterRef

    @model_validator(mode="after")
    def _config_paths_under_configs(self) -> AdapterWheelsV1Manifest:
        for p in self.config_paths:
            if not p.startswith("configs/"):
                raise ValueError(f"adapter-wheels-v1 config_paths should live under configs/: {p!r}")
        return self


EnvironmentManifest = Annotated[
    NativeV1Manifest | WheelsV1Manifest | AdapterWheelsV1Manifest,
    Field(discriminator="format"),
]

ENVIRONMENT_MANIFEST_ADAPTER: TypeAdapter[EnvironmentManifest] = TypeAdapter(EnvironmentManifest)


class ModelServerRefSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["responses_api_models"] = "responses_api_models"
    name: str = "policy_model"


class VerifiersAgentInstanceConfig(BaseModel):
    """Fields under responses_api_agents.verifiers_agent in Hydra YAML."""

    model_config = ConfigDict(extra="allow", protected_namespaces=())

    entrypoint: str = "app.py"
    model_server: ModelServerRefSpec = Field(default_factory=ModelServerRefSpec)
    model_name: str = ""
    vf_env_id: str
    vf_env_args: dict = Field(default_factory=dict)
    max_tokens: int = 8192
    temperature: float = 1.0
    top_p: float = 1.0
    domain: str = ""
    description: str = ""
    value: str = ""
    group_size: int = 1
    max_concurrent_generation: int = -1
    max_concurrent_scoring: int = -1


class AgentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["responses_api_agents"] = "responses_api_agents"
    name: str


class GymVerifiersDatasetRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_idx: int
    vf_env_id: str
    responses_create_params: dict
    agent_ref: AgentRef
    answer: str = ""
    task: str = ""
    example_id: int | str = 0
    info: dict = Field(default_factory=dict)
    question: str | None = None
