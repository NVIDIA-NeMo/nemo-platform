# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared models for evaluator inputs, outputs, resources, and dependencies."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
from abc import ABC
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, TypeAlias
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field, SerializeAsAny

DataValue: TypeAlias = str | int | float | bool | dict[str, Any] | list[Any] | None
MetricValue: TypeAlias = float | int
TrialStatus: TypeAlias = Literal["completed", "failed"]


class DatasetValidationError(ValueError):
    """Dataset content failed evaluator-specific authoring validation."""


def local_path_from_uri(uri: str, *, context: str = "Resource") -> Path:
    """Convert a plain path or local file URI to a path on Python 3.12+."""
    parsed = urlparse(uri)
    if parsed.scheme not in ("", "file"):
        raise ValueError(f"{context} must be a local path or file URI, got URI scheme {parsed.scheme!r}: {uri}")
    if parsed.scheme == "file" and parsed.netloc not in ("", "localhost"):
        raise ValueError(f"{context} file URI must be local, got: {uri}")
    raw_path = parsed.path if parsed.scheme == "file" else uri
    return Path(unquote(raw_path)).expanduser()


def subset_dataset_id(dataset_id: str, task_ids: Sequence[str]) -> str:
    """Return deterministic dataset id for a selected task subset.

    Args:
        dataset_id (str): The dataset id to subset.
        task_ids (Sequence[str]): The task ids to subset the dataset by.

    Returns:
        str: A deterministic dataset id for the selected task subset.
    """
    digest = hashlib.sha256("\n".join(task_ids).encode("utf-8")).hexdigest()[:12]
    return f"{dataset_id}-subset-{len(task_ids)}-{digest}"


class ResourceRef(BaseModel):
    """Lazy reference to a local, remote, or evaluator-native resource."""

    uri: str = Field(description="Portable locator: file, remote URL, or evaluator-native URI.")
    description: str = Field(default="", description="Human-readable description of the resource.")
    metadata: dict[str, DataValue] = Field(default_factory=dict, description="Small serializable resource facts.")


class CommandSpec(BaseModel):
    """Runnable command description for dependency setup."""

    argv: list[str] = Field(description="Command arguments.")
    cwd: ResourceRef | None = Field(default=None, description="Working directory for the command.")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables for the command.")
    timeout_sec: int | None = Field(default=None, description="Timeout for the command in seconds.")
    metadata: dict[str, DataValue] = Field(default_factory=dict, description="Metadata for the command.")


class DependencyRuntime(BaseModel):
    """Commands that describe how to start task dependencies."""

    start: CommandSpec | None = Field(default=None, description="Command to start the dependencies.")
    stop: CommandSpec | None = Field(default=None, description="Command to stop the dependencies.")
    readiness: CommandSpec | None = Field(
        default=None, description="Command to check the readiness of the dependencies."
    )
    metadata: dict[str, DataValue] = Field(default_factory=dict, description="Metadata for the dependencies.")

    def context(self) -> AbstractAsyncContextManager[DependencyRuntime | None]:
        """Return dependency context for this runtime."""
        return DependencyContext(self)


async def run_dependency_command(spec: CommandSpec, phase: str) -> None:
    """Run a dependency command.

    Args:
        spec (CommandSpec): The command spec to run.
        phase (str): The phase of the dependency command.

    """
    if not spec.argv:
        raise ValueError(f"Dependency {phase} command has empty argv")

    cwd = local_path_from_uri(spec.cwd.uri, context="Command cwd") if spec.cwd is not None else None
    env = os.environ.copy()
    env.update(spec.env)

    process = await asyncio.create_subprocess_exec(
        *spec.argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=spec.timeout_sec)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        command = shlex.join(spec.argv)
        raise TimeoutError(f"Dependency {phase} command timed out after {spec.timeout_sec}s: {command}") from exc

    if process.returncode == 0:
        return

    command = shlex.join(spec.argv)
    stdout_text = stdout.decode(errors="replace").strip()
    stderr_text = stderr.decode(errors="replace").strip()
    raise RuntimeError(
        f"Dependency {phase} command failed with exit code {process.returncode}: {command}\n"
        f"stdout:\n{stdout_text}\n"
        f"stderr:\n{stderr_text}"
    )


class DependencyContext:
    """Async context manager that starts and stops command dependencies."""

    def __init__(self, runtime: DependencyRuntime | None) -> None:
        self._runtime = runtime

    async def __aenter__(self) -> DependencyRuntime | None:
        """Start dependencies and return the runtime that was entered."""
        if self._runtime is None:
            return None
        try:
            if self._runtime.start is None:
                raise ValueError("DependencyRuntime requires start")
            await run_dependency_command(self._runtime.start, "start")

            if self._runtime.readiness is not None:
                await run_dependency_command(self._runtime.readiness, "readiness")
        except BaseException:
            try:
                await self._stop_started_runtime()
            except Exception:
                pass
            raise
        return self._runtime

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Stop dependencies after the wrapped analysis block completes."""
        if self._runtime is None:
            return False
        try:
            await self._stop_started_runtime()
        except Exception:
            if exc_type is None:
                raise
        return False

    async def _stop_started_runtime(self) -> None:
        """Stop the started runtime."""
        stop_error: Exception | None = None
        if self._runtime is not None and self._runtime.stop is not None:
            try:
                await run_dependency_command(self._runtime.stop, "stop")
            except Exception as exc:
                if stop_error is None:
                    stop_error = exc

        if stop_error is not None:
            raise stop_error


class MetricSpec(BaseModel):
    """Metric definition expected from evaluator output."""

    name: str = Field(description="Stable metric identifier, such as 'reward' or 'accuracy'.")
    description: str = Field(description="Human-readable meaning of the metric.")
    ref: ResourceRef | None = Field(default=None, description="Reference to the metric definition.")


class MetricResult(BaseModel):
    """Numeric metric value with provenance metadata."""

    name: str = Field(description="Name of the metric.")
    value: MetricValue = Field(description="Numeric metric value.")
    spec: MetricSpec | None = Field(default=None, description="Metric spec for the metric.")
    metadata: dict[str, DataValue] = Field(
        default_factory=dict,
        description="Metric provenance or aggregation details.",
    )


class Task(BaseModel):
    """One task input item."""

    uri: str = Field(default="", description="Portable locator for the task itself.")
    description: str = Field(default="", description="Human-readable description of the task reference.")
    id: str = Field(description="Stable task identifier within the dataset.")
    inputs: dict[str, DataValue | ResourceRef] = Field(default_factory=dict, description="Named inputs for the task.")
    resources: dict[str, ResourceRef] = Field(default_factory=dict, description="Named resources for the task.")
    metric_specs: dict[str, MetricSpec] = Field(default_factory=dict, description="Named metric specs for the task.")
    dependencies: SerializeAsAny[DependencyRuntime] | None = Field(
        default=None,
        description="Dependencies for the task.",
    )
    metadata: dict[str, DataValue] = Field(default_factory=dict, description="Metadata for the task.")

    def start_deps(self) -> AbstractAsyncContextManager[DependencyRuntime | None]:
        """Return an async context manager for this task's dependency runtime.

        Returns:
            AbstractAsyncContextManager[DependencyRuntime | None]: An async context manager for this task's dependency runtime.
        """
        if self.dependencies is None:
            return DependencyContext(None)
        return self.dependencies.context()


class Dataset(ABC):
    """Collection of tasks."""

    def __init__(
        self,
        id: str,
        source: ResourceRef | None = None,
        tasks: Sequence[Task] | None = None,
        metadata: dict[str, DataValue] | None = None,
    ) -> None:
        self.id = id
        self.source = source
        self.tasks = list(tasks or [])
        self.metadata = dict(metadata or {})

    def list_tasks(self) -> Sequence[Task]:
        """Return all tasks in the dataset.

        Returns:
            Sequence[Task]: A sequence of Task objects in the dataset.
        """
        return list(self.tasks)

    async def validate(self) -> None:
        """Validate authored dataset content without running evaluation trials.

        Evaluator-specific datasets override this method with safe, static
        checks that dataset authors can call repeatedly while editing.

        Raises:
            DatasetValidationError: If authored dataset content is invalid.
        """

    def subset(self, task_ids: Sequence[str]) -> Dataset:
        """Return a dataset containing selected task ids.

        Args:
            task_ids (Sequence[str]): The task ids to subset the dataset by.

        Returns:
            Dataset: A dataset containing the selected task ids.
        """
        selected_ids = set(task_ids)
        tasks = [task for task in self.list_tasks() if task.id in selected_ids]
        missing = selected_ids - {task.id for task in tasks}
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"Task id(s) not found in dataset {self.id!r}: {missing_text}")
        return self.__class__(
            id=subset_dataset_id(self.id, [task.id for task in tasks]),
            source=self.source,
            tasks=tasks,
            metadata=self.metadata,
        )

    @classmethod
    def from_ref(cls, ref: DatasetRef) -> Dataset:
        """Create a Dataset from a DatasetRef.

        Parses the DatasetRef and returns a Dataset object based on the type of the DatasetRef.

        Args:
            ref (DatasetRef): The DatasetRef to parse.

        Returns:
            Dataset: A Dataset object based on the type of the DatasetRef.
        """
        raise NotImplementedError("Subclasses must implement this method")


class TrialResult(BaseModel):
    """One task execution by one agent attempt."""

    id: str = Field(description="Stable trial identifier within the evaluation run.")
    task_id: str = Field(description="Stable task identifier within the dataset.")
    attempt: int | None = Field(default=None, description="Attempt index when multiple attempts are run.")
    status: TrialStatus = Field(description="Execution status of the trial.")
    trace: ResourceRef | None = Field(default=None, description="Local or Intake trace reference for analyzers.")
    outputs: dict[str, DataValue | ResourceRef] = Field(
        default_factory=dict,
        description="Named outputs for the trial.",
    )
    resources: dict[str, ResourceRef] = Field(default_factory=dict, description="Named resources for the trial.")
    metrics: dict[str, MetricResult] = Field(default_factory=dict, description="Named metrics for the trial.")
    error: dict[str, DataValue] | None = Field(default=None, description="Error details for the trial.")
    metadata: dict[str, DataValue] = Field(
        default_factory=dict,
        description="Metadata for the trial.",
    )


class EvaluationResult(BaseModel):
    """Evaluator run output consumed by optimizer and downstream analyzers."""

    id: str = Field(description="Stable identifier for one evaluator run.")
    aggregate_metrics: dict[str, float | int] = Field(
        default_factory=dict,
        description="Run-level metric summaries.",
    )
    trials: Sequence[TrialResult] = Field(default_factory=list, description="Trials produced by this run.")
    metadata: dict[str, DataValue] = Field(
        default_factory=dict,
        description="Metadata for the evaluation run.",
    )


class DatasetRef(ResourceRef):
    """Source handle used to build evaluator-specific Dataset objects."""
