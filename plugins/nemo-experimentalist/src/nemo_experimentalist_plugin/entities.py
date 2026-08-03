# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The entities every Experimentalist plugin speaks.

``ExperimentRun`` and ``Candidate`` are stored in the NeMo Platform entity store; the
dataset and evaluation-result models are what a strategy reads and writes. Every plugin
shares these, so they live here rather than inside any one component.
"""

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

from nemo_platform_plugin.entity import NemoEntity
from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, model_validator

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


class ExperimentRun(NemoEntity, entity_type="experiment_run"):
    """Tracks a single Experimentalist optimization run end-to-end.

    Enables resumability and listing all runs for an insight. Created when a
    run starts, updated on each round, and finalized (with summary and
    winner) when the run completes or fails.
    """

    model_config = ConfigDict(validate_assignment=True)

    # --- immutable: set at creation, never updated ---
    agent: str = Field(frozen=True, description="Name or path of the agent under test.")
    insight: str | None = Field(
        frozen=True,
        default=None,
        description=(
            "Id of the Insight this run is optimizing against, or a local "
            "filesystem path to the insight fixture when running offline. "
            "None for Mode 2 (dataset-driven) runs."
        ),
    )
    config_snapshot: dict[str, Any] = Field(
        frozen=True,
        default_factory=dict,
        description="EvolutionaryOptimizerConfig fields at run creation time.",
    )
    # --- mutable: updated throughout the run lifecycle ---
    status: Literal["running", "completed", "failed"] = Field(
        default="running",
        description="Lifecycle status of this optimization run.",
    )
    progress_completed: int = Field(
        default=0,
        description="Units of work the strategy reports finished so far. Display only.",
    )
    progress_total: int | None = Field(
        default=None,
        description=(
            "Units of work expected in total, when the strategy can say. None means it "
            "cannot — an opaque strategy has no honest denominator, so consumers show a "
            "counter rather than a bar."
        ),
    )
    progress_unit: str = Field(
        default="step",
        description="What one unit of progress is: 'round' for the evolutionary loop, 'trial' for a search.",
    )
    progress_note: str | None = Field(
        default=None,
        description="What the strategy is currently doing, for strategies with no meaningful total.",
    )
    winner_agent: str | None = Field(
        default=None,
        description=(
            "Entity id of the winning Candidate, or a local filesystem path "
            "to the agent directory when running offline; set on completion."
        ),
    )
    summary: str | None = Field(
        default=None,
        description="Human-readable summary of the run; filled by persist_result.",
    )

    @model_validator(mode="wrap")
    @classmethod
    def _restore_id_from_json(cls, data: Any, handler: Any) -> "ExperimentRun":
        """Restore computed field ``id`` when deserializing from JSON.

        The ``id`` property is a computed field backed by private ``_id``. It serializes
        to JSON but ``model_validate`` ignores computed fields during deserialization,
        so the private ``_id`` must be restored from the serialized ``"id"`` key.
        Without this, resumed runs lose their identity and projection names collapse.
        """
        if isinstance(data, dict) and "id" in data:
            # Pydantic wraps the dict during validation, extract the raw data
            instance = handler(data)
            instance._id = data["id"]  # type: ignore[attr-defined]
            return instance
        return handler(data)


class RewardRecord(BaseModel):
    """One measurement of one candidate on one reward channel.

    ``metrics`` are the channel's dimensions — what a selector may compare on.
    ``summary`` is an optional scalar rollup of them, kept out of ``metrics`` so a
    selector can never mistake a derived total for a Pareto dimension that dominates
    every real one.
    """

    metrics: dict[str, float] = Field(default_factory=dict, description="This channel's reward dimensions.")
    summary: float | None = Field(default=None, description="Optional scalar rollup; never a metrics key.")
    trials: Sequence[TrialResult] = Field(
        default_factory=list, description="Per-trial detail, when the channel has any."
    )
    metadata: dict[str, DataValue] = Field(default_factory=dict, description="Provenance for this measurement.")


class Proposal(BaseModel):
    """A request to build one candidate — the Proposer → Builder contract.

    A transient component message, not a separately persisted entity and not an
    unfinished Candidate: a proposal describes work to perform, and a Candidate is the
    durable result after a Builder completes it. Failed proposals produce no Candidate
    and are not retained; a successful one is embedded in ``Candidate.generated_from``.

    ``kind`` is an opaque compatibility discriminator, not a global enumeration: it
    routes the proposal to a Builder that declares it can accept it. ``payload`` is
    owned by that Proposer/Builder pair — Layer A stores and transports it and
    interprets neither.
    """

    ancestor: str | None = Field(
        default=None,
        description="Parent Candidate id to build from. None means the baseline.",
    )
    description: str = Field(
        min_length=1,
        description="Human-readable explanation of the proposed variant.",
    )
    kind: str = Field(
        min_length=1,
        description="Builder compatibility discriminator, e.g. 'code-change' or 'parameters'.",
    )
    payload: dict[str, DataValue] = Field(
        default_factory=dict,
        description="Build instructions, validated by the component-owned schema for this kind.",
    )


class Candidate(NemoEntity, entity_type="candidate"):
    """A candidate agent version produced during an Experimentalist run.

    Metadata and measurements live in the entity store; the completed work is
    *addressed*, not contained. ``artifact`` points at the resource that defines this
    candidate and, when external evaluation is used, is directly consumable by the
    run's evaluation component. Its format belongs to the components that produce and
    consume that candidate kind — the host only stores, transports, archives and
    publishes the reference.

    A Candidate is only ever created once its artifact exists and validates, so
    ``artifact`` is required and no durable record points at partial work. Incomplete
    work is a runner-owned path, not a Candidate.

    Identity is the store-assigned ``id``. ``label`` survives purely as a display
    handle for reports and the evolution tree; it is unique within a run, not globally,
    and nothing may derive storage or lineage from it.
    """

    workspace: str = Field(
        default="default",
        description="NeMo Platform workspace this candidate belongs to.",
    )
    run_id: str = Field(
        ...,
        description="ExperimentRun entity id that this candidate belongs to.",
    )
    label: str = Field(
        ...,
        description=(
            "Display handle for this candidate (e.g. 'agent-0'), used in reports and the "
            "evolution tree. Unique within a run, not globally, and not identity."
        ),
    )
    ancestor: str | None = Field(
        default=None,
        description=(
            "Parent Candidate id. None means this is the baseline — the one place the "
            "distinction is encoded, replacing the round-0 sentinel it used to share it with."
        ),
    )
    generation: int = Field(
        default=0,
        description=(
            "Strategy-supplied grouping index. Our loop sets the round and HPO sets the "
            "generation; a strategy with no such notion leaves it 0."
        ),
    )
    generated_from: Proposal | None = Field(
        default=None,
        description=(
            "Immutable snapshot of the Proposal this candidate was built from, so a Proposer "
            "can read the history of what worked. None for the baseline or an imported candidate."
        ),
    )
    description: str = Field(
        description="Human-readable explanation of this candidate; derived from the Proposal when there is one.",
    )
    artifact: ResourceRef = Field(
        ...,
        description="The completed resource that defines this candidate, written by its Builder.",
    )
    rewards: dict[str, RewardRecord] = Field(
        default_factory=dict,
        description=(
            "Measurements keyed by reward channel. An open set: 'train', 'validation', "
            "'insight' and 'validation-trajectory' today. A channel is a measurement, not a "
            "dataset split — trajectory scoring is a second measurement of the validation "
            "split — so adding one costs no entity change."
        ),
    )
    trajectory_detail: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Per-node, per-task trajectory scores and explanations "
            "(node_id -> task_id -> {reward, explanation}). Shaped unlike RewardRecord.trials "
            "and produced by one scorer; revisit when the trajectory-scorer seam lands."
        ),
    )
    killed_generation: int | None = Field(
        default=None,
        description="Generation in which this candidate was eliminated. None means still alive.",
    )

    @model_validator(mode="after")
    def _projections_agree_with_origin(self) -> "Candidate":
        """Reject a record whose derived projections disagree with its origin.

        ``ancestor`` and ``description`` are generic, queryable copies of what the
        embedded Proposal already says. ``commit_candidate`` derives them, so a
        disagreement means something set a copy independently and the two accounts of
        this candidate's origin have drifted.
        """
        origin = self.generated_from
        if origin is None:
            return self
        if self.ancestor != origin.ancestor:
            raise ValueError(f"Candidate ancestor {self.ancestor!r} disagrees with its Proposal's {origin.ancestor!r}")
        if self.description != origin.description:
            raise ValueError("Candidate description disagrees with its Proposal's")
        return self

    @property
    def is_baseline(self) -> bool:
        """True for the agent under test as it arrived, before any change."""
        return self.ancestor is None

    def __repr__(self) -> str:
        parts = [f"Candidate(label={self.label!r}, generation={self.generation}"]
        if self.ancestor is not None:
            parts.append(f", ancestor={self.ancestor!r}")
        parts.append(f", description={self.description!r}")
        if self.generated_from is not None:
            parts.append(f", kind={self.generated_from.kind!r}")
        for channel, record in self.rewards.items():
            if record.metrics:
                scores = ", ".join(f"{k}={v:.3f}" for k, v in record.metrics.items())
                parts.append(f", {channel}={{{scores}}}")
        if self.killed_generation is not None:
            parts.append(f", killed_generation={self.killed_generation}")
        parts.append(")")
        return "".join(parts)

    def reward(self, channel: str) -> RewardRecord:
        """This candidate's measurement on *channel*, empty when unmeasured.

        Returns a blank record rather than ``None`` so call sites read
        ``candidate.reward("train").metrics`` without a presence check. Use
        ``channel in candidate.rewards`` to ask whether it was measured at all —
        an empty record and an unmeasured channel are different things.
        """
        return self.rewards.get(channel) or RewardRecord()

    def record_reward(
        self,
        channel: str,
        *,
        metrics: dict[str, float] | None = None,
        summary: float | None = None,
        trials: Sequence[TrialResult] | None = None,
        metadata: dict[str, DataValue] | None = None,
    ) -> None:
        """Merge a measurement into *channel*, leaving unspecified parts untouched.

        Named ``record_`` rather than ``set_`` because it merges: an argument left as
        ``None`` keeps whatever the channel already holds. Every caller today writes a
        channel exactly once, so nothing currently depends on that — but the channel set
        is open, and a second writer adding ``metadata`` to a channel another path
        measured should not silently drop its ``metrics``. Replace semantics would make
        that a data loss no test would catch.
        """
        current = self.rewards.get(channel) or RewardRecord()
        update = {
            key: value
            for key, value in (
                ("metrics", metrics),
                ("summary", summary),
                ("trials", trials),
                ("metadata", metadata),
            )
            if value is not None
        }
        self.rewards = {**self.rewards, channel: current.model_copy(update=update)}

    def slim(self) -> "Candidate":
        """Return a copy without per-trial detail (safe to pass to LLM methods)."""
        return self.model_copy(
            update={
                "rewards": {c: r.model_copy(update={"trials": []}) for c, r in self.rewards.items()},
                "trajectory_detail": None,
            }
        )
