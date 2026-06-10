# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimental benchmark extension points for standalone agent evaluation."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Protocol, TypeGuard, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalRunResult, AgentEvalTask


class AgentEvalBenchmarkLoadConfig(BaseModel):
    """Generic load options passed from callers to benchmark implementations."""

    model_config = ConfigDict(extra="forbid")

    source: str | Path | None = None
    limit: int | None = Field(default=None, ge=0)
    evidence_dir: Path | None = None


class AgentEvalBenchmarkBundle(BaseModel):
    """SDK-native tasks and optional stored attempts loaded by a benchmark."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    tasks: list[AgentEvalTask] = Field(default_factory=list)
    attempts: list[AgentEvalAttempt] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evaluation_shape(self) -> "AgentEvalBenchmarkBundle":
        if not self.tasks:
            raise ValueError("benchmark bundles require at least one task")
        return self


class AgentEvalBenchmarkReports(BaseModel):
    """Report files written by a benchmark-specific report writer."""

    model_config = ConfigDict(extra="forbid")

    paths: list[Path] = Field(default_factory=list)


@runtime_checkable
class AgentEvalBenchmark(Protocol):
    """Experimental protocol for adapting external benchmarks into agent-eval."""

    @property
    def name(self) -> str:
        """Stable benchmark name used in diagnostics, metadata, and user-facing output."""
        ...

    def load(self, config: AgentEvalBenchmarkLoadConfig) -> AgentEvalBenchmarkBundle:
        """Load tasks and optional recorded attempts."""
        ...


@runtime_checkable
class AgentEvalBenchmarkReportWriter(Protocol):
    """Optional benchmark-specific report hook."""

    def write_reports(self, result: AgentEvalRunResult, output_dir: Path) -> AgentEvalBenchmarkReports:
        """Write benchmark-specific reports for a completed run and return their paths."""
        ...


def resolve_agent_eval_benchmark(ref: str) -> AgentEvalBenchmark:
    """Resolve a ``module:object`` benchmark reference.

    The referenced object may be a benchmark instance, a benchmark class, or a
    zero-argument factory returning a benchmark instance.
    """
    module_name, separator, object_path = ref.partition(":")
    if not separator or not module_name or not object_path:
        raise ValueError("benchmark references must use module:object syntax")

    module = importlib.import_module(module_name)
    resolved: Any = module
    for part in object_path.split("."):
        resolved = getattr(resolved, part)

    candidate = resolved
    if isinstance(candidate, type):
        candidate = candidate()
    elif not _is_agent_eval_benchmark(candidate) and callable(candidate):
        candidate = candidate()

    if not _is_agent_eval_benchmark(candidate):
        raise TypeError(f"resolved benchmark {ref!r} does not implement AgentEvalBenchmark")
    return candidate


def _is_agent_eval_benchmark(value: object) -> TypeGuard[AgentEvalBenchmark]:
    return (
        isinstance(getattr(value, "name", None), str)
        and callable(getattr(value, "load", None))
    )
