# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# TODO(shared-module): Rationale models copied from experimentalist rationalizer.py; unify with rationalizer module.

from pydantic import BaseModel, Field


class RationaleStep(BaseModel):
    """One reasoning step in a task rationale."""

    thought: str
    action: str
    observation: str = ""


class Rationale(BaseModel):
    """Task-level context produced by the Rationalizer before trace analysis."""

    task_name: str
    steps: list[RationaleStep] = Field(default_factory=list)
