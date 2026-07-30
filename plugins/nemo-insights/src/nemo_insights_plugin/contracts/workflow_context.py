# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local handoff state for the trace → Insight → experiment workflow."""

import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from nemo_insights_plugin.contracts.profile import DEFAULT_BASE_URL, ProfileError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONTEXT_RELPATH = Path(".nemo-optimizer") / "context.yaml"


class WorkflowContext(BaseModel):
    """The latest trace corpus selected for an agent profile."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    agent: str = Field(min_length=1)
    workspace: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    trace_source: str = Field(min_length=1)
    trace_since: datetime


def context_path(profile_dir: Path) -> Path:
    """Return the profile-owned workflow context path."""
    return profile_dir / CONTEXT_RELPATH


def load_workflow_context(profile_dir: Path, *, agent: str | None = None) -> WorkflowContext | None:
    """Load the profile's workflow context and reject stale cross-agent state."""
    path = context_path(profile_dir)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProfileError(f"Could not read workflow context {path}: {exc}") from None
    if not isinstance(payload, dict):
        raise ProfileError(f"Could not read workflow context {path}: expected a YAML mapping")
    try:
        context = WorkflowContext.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}" for error in exc.errors())
        raise ProfileError(f"Invalid workflow context {path}: {details}") from None
    if agent is not None and context.agent != agent:
        raise ProfileError(
            f"Workflow context {path} belongs to agent {context.agent!r}, "
            f"but optimizer.yaml selects {agent!r}. Run `nemo traces import` again."
        )
    return context


def write_workflow_context(profile_dir: Path, context: WorkflowContext) -> Path:
    """Atomically persist the latest trace selection beside ``optimizer.yaml``."""
    path = context_path(profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        yaml.safe_dump(context.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def resolve_context_base_url(
    explicit: str | None,
    context: WorkflowContext | None,
    *,
    env: Mapping[str, str] = os.environ,
) -> str:
    """Apply flag, shell, imported-context, then localhost precedence."""
    if explicit is not None:
        return explicit
    if value := env.get("NMP_BASE_URL"):
        return value
    if context is not None:
        return context.base_url
    return DEFAULT_BASE_URL
