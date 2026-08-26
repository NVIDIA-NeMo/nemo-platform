#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared types for audit-spec measurement scripts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeAlias

JsonObject: TypeAlias = dict[str, Any]


class ToolCallLike(Protocol):
    """Tool-call fields consumed from Harbor trajectory models."""

    function_name: str | None
    tool_call_id: str | None


class StepLike(Protocol):
    """Trajectory step fields consumed by measurement methods."""

    step_id: int | str | None
    tool_calls: Sequence[ToolCallLike] | None


class TrajectoryLike(Protocol):
    """Trajectory fields shared by root and subagent Harbor trajectories."""

    trajectory_id: str | None
    steps: Sequence[StepLike] | None
    subagent_trajectories: Sequence[TrajectoryLike] | None


class MeasurementMethod(Protocol):
    """Module-level protocol implemented by measurement method modules."""

    METHOD_NAME: str
    DETAILS_SCHEMA: str

    def measure(self, audit: JsonObject, trajectory: TrajectoryLike) -> JsonObject: ...
