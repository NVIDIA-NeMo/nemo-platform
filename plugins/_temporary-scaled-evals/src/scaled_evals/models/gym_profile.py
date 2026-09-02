# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validation contract for non-secret Gym framework profiles."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SAFE_ABSOLUTE_ROOTS = (
    PurePosixPath("/opt/gym"),
    PurePosixPath("/harness/gym-sandbox-opensandbox"),
)
_RESERVED_OVERRIDE_PARTS = frozenset(
    {
        "api_key",
        "connection",
        "domain",
        "environment",
        "opensandbox",
        "proxy",
        "resources",
        "sandbox_provider",
        "sandbox_spec",
        "ttl",
        "user",
    }
)
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class GymProfileConfig(BaseModel):
    """Versioned, non-secret configuration accepted from a ``gym`` profile."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    command: Literal["run_and_collect", "ng_e2e_collect_rollouts", "ng_collect_rollouts"]
    config_paths: list[str] = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    input_jsonl_fpath: str | None = None
    output_jsonl_fpath: str | None = None
    split: str | None = None
    limit: int | None = Field(default=None, ge=1)
    num_repeats: int | None = Field(default=None, ge=1)
    num_samples_in_parallel: int | None = Field(default=None, ge=1)
    responses_create_params: dict[str, bool | float | int | str] = Field(default_factory=dict)
    overrides: dict[str, bool | float | int | str] = Field(default_factory=dict)

    @field_validator("agent_name")
    @classmethod
    def _validate_agent_name(cls, value: str) -> str:
        if not _NAME_RE.fullmatch(value):
            raise ValueError("agent_name may contain only letters, numbers, '.', '_', and '-'")
        return value

    @field_validator("config_paths")
    @classmethod
    def _validate_config_paths(cls, values: list[str]) -> list[str]:
        return [_safe_runner_path(value, field="config_paths") for value in values]

    @field_validator("input_jsonl_fpath")
    @classmethod
    def _validate_input_path(cls, value: str | None) -> str | None:
        return None if value is None else _safe_runner_path(value, field="input_jsonl_fpath")

    @field_validator("responses_create_params", "overrides")
    @classmethod
    def _validate_override_values(
        cls, values: dict[str, bool | float | int | str]
    ) -> dict[str, bool | float | int | str]:
        for key, value in values.items():
            if not key or not all(_NAME_RE.fullmatch(part) for part in key.split(".")):
                raise ValueError(f"invalid Gym override key: {key!r}")
            if "," in str(value) or "\n" in str(value):
                raise ValueError(f"Gym override {key!r} may not contain commas or newlines")
        return values

    @model_validator(mode="after")
    def _protect_substrate(self) -> GymProfileConfig:
        for key in self.overrides:
            if _is_reserved_override(key):
                raise ValueError(f"Gym override {key!r} changes operator-owned sandbox configuration")
        for key in self.responses_create_params:
            if _is_reserved_override(key):
                raise ValueError(f"responses_create_params {key!r} changes operator-owned routing or secrets")
        if self.command == "ng_collect_rollouts" and not self.input_jsonl_fpath:
            raise ValueError("input_jsonl_fpath is required for ng_collect_rollouts")
        return self


def validate_gym_profile_config(raw_config: dict[str, Any]) -> GymProfileConfig:
    """Validate a complete Gym profile at API and dispatch boundaries."""
    return GymProfileConfig.model_validate(raw_config)


def _safe_runner_path(value: str, *, field: str) -> str:
    if not value or "\n" in value or "," in value:
        raise ValueError(f"{field} entries must be non-empty paths without commas or newlines")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise ValueError(f"{field} entries may not traverse parent directories")
    if path.is_absolute() and not any(path == root or path.is_relative_to(root) for root in _SAFE_ABSOLUTE_ROOTS):
        roots = ", ".join(str(root) for root in _SAFE_ABSOLUTE_ROOTS)
        raise ValueError(f"absolute {field} entries must be under one of: {roots}")
    return value


def _is_reserved_override(key: str) -> bool:
    normalized = key.lower()
    parts = set(normalized.replace("-", "_").split("."))
    if parts & _RESERVED_OVERRIDE_PARTS:
        return True
    return any(
        fragment in normalized for fragment in ("api_key", "base_url", "opensandbox", "sandbox_", "connection", "proxy")
    )
