# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validation contract for non-secret Harbor framework profiles."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class HarborProfileConfig(BaseModel):
    """Extensible Harbor config envelope understood by the sandbox runner.

    Harbor's full configuration is versioned independently, so unknown fields
    are preserved. Fields interpreted directly by scaled-evals are typed here
    so malformed profiles fail at the API boundary instead of during dispatch.
    """

    model_config = ConfigDict(extra="allow")

    config: StrictStr | None = Field(default=None, min_length=1)
    harbor_config: StrictStr | None = Field(default=None, min_length=1)
    template: StrictStr | None = Field(default=None, min_length=1)
    harbor_template: StrictStr | None = Field(default=None, min_length=1)
    env: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    vars: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_structured_config(self) -> HarborProfileConfig:
        extra = self.__pydantic_extra__ or {}
        for key in ("agents", "tasks"):
            value = extra.get(key)
            if value is not None and not isinstance(value, list):
                raise ValueError(f"harbor profile '{key}' must be a list")
        for key in ("retry",):
            value = extra.get(key)
            if value is not None and not isinstance(value, dict):
                raise ValueError(f"harbor profile '{key}' must be an object")
        for key in ("job_name", "jobs_dir"):
            value = extra.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"harbor profile '{key}' must be a string")
        for key in ("n_attempts", "n_concurrent_trials"):
            value = extra.get(key)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
                raise ValueError(f"harbor profile '{key}' must be a positive integer")
        return self


def validate_harbor_profile_config(raw_config: dict[str, Any]) -> HarborProfileConfig:
    """Validate fields scaled-evals interprets while preserving Harbor extensions."""

    return HarborProfileConfig.model_validate(raw_config)
