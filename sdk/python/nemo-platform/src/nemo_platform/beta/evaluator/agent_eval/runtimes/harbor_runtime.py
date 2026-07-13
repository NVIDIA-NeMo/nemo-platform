# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor-backed :class:`AgentTaskRunner` for the agent-eval pipeline.

Harbor already runs trials in (Docker) environments, retries them, and writes a
documented results tree: one ``<task>__<hash>/result.json`` per trial under the
job directory. This runtime adapts that tree into SDK :class:`AgentEvalTrial`
objects so an :class:`AgentEvaluator` can score and report Harbor runs through the
same seam as any other runtime.

Two ways to drive it:

* **Native** — pass a :class:`HarborRuntimeConfig` and a dataset directory; the
  runtime builds Harbor's ``JobConfig`` and runs it itself. The one-call
  :func:`run_harbor_eval` loads the tasks, runs, and scores, so caller code is a
  couple of lines. ``harbor`` is imported lazily inside ``run_tasks`` (it is an
  optional extra), so importing this module never requires Harbor. Custom
  ``import_path`` agents are supported too: set ``agent_import_path`` and, for a
  loose ``harbor_wrapper.py``, also ``agent_dir`` — the runtime then injects that
  directory into ``sys.modules`` for the duration of the run and tears it down
  after (see :func:`scoped_harbor_agent_import`). When ``agent_dir`` is omitted
  (the module is already importable) the path is handed to Harbor's importer
  unchanged, so nothing is imposed on how the agent is packaged.
* **Injected / offline** — pass a ``job_dir`` (and optionally a ``run_job``
  callback) to adapt an already-completed job dir or to run a caller-built job.

Trial *adaptation* only ever reads Harbor's on-disk ``result.json`` files, so
that half stays dependency-free regardless of how the job was produced.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import json
import logging
import re
import shutil
import sys
import threading
import tomllib
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalResult
from nemo_platform.beta.evaluator.agent_eval.scores import AgentEvalScoreStatus
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask, AgentEvalTaskset
from nemo_platform.beta.evaluator.agent_eval.trials import (
    AgentEvalTrial,
    AgentEvalTrialStatus,
    AgentOutput,
    standard_evidence_descriptors,
)
from nemo_platform.beta.evaluator.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

# Default reward key inside Harbor's ``verifier_result.rewards`` mapping.
DEFAULT_REWARD_KEY = "reward"
# Filename that marks a directory as a Harbor task, and the template dir to skip.
_TASK_CONFIG_FILENAME = "task.toml"
_TASK_TEMPLATE_DIRNAME = "task_template"
# Synthetic sys.modules root a custom ``import_path`` agent package is injected under.
_AGENT_IMPORT_ROOT = "_nemo_evaluator_harbor_agents"
# Guards the sys.modules mutation while injecting/removing scoped agent packages.
_IMPORT_LOCK = threading.Lock()

RunJob = Callable[[], Awaitable[None]]


class HarborRuntimeConfig(BaseModel):
    """Declarative config for running a Harbor job natively through the SDK.

    Holds only plain/pydantic fields so importing this module never needs Harbor;
    the fields are mapped onto Harbor's ``JobConfig`` lazily at run time.
    """

    model_config = ConfigDict(extra="forbid")

    jobs_dir: Path = Field(description="Parent directory Harbor writes the ``<job_name>/`` results tree into.")
    job_name: str | None = Field(default=None, description="Harbor job name; a timestamp is generated when omitted.")
    agent_name: str | None = Field(
        default="oracle",
        description="Built-in Harbor agent to run (e.g. 'oracle'). Ignored when ``agent_import_path`` is set.",
    )
    agent_import_path: str | None = Field(
        default=None,
        description="Custom Harbor agent import path (e.g. 'harbor_wrapper:WrappedAgent'); overrides ``agent_name``.",
    )
    agent_dir: Path | None = Field(
        default=None,
        description=(
            "Directory holding the module named by ``agent_import_path``. Set it for a loose "
            "wrapper file (the SDK makes it importable); leave it unset when the module is "
            "already importable (installed package), and Harbor imports it directly."
        ),
    )
    agent_model_name: str | None = Field(default=None, description="Optional model slug passed to the Harbor agent.")
    n_attempts: int = Field(default=1, ge=1, description="Number of attempts Harbor runs per task.")
    n_concurrent_trials: int = Field(default=4, ge=1, description="Maximum concurrent Harbor trials.")
    quiet: bool = Field(default=True, description="Suppress Harbor's trial progress displays.")
    force_rerun: bool = Field(default=False, description="Delete an existing job dir before running.")
    artifacts: list[str] = Field(default_factory=list, description="Harbor artifact sources to collect per trial.")
    trace_dir: str | None = Field(
        default=None,
        description="Container path of agent traces to collect as the 'traces' artifact (e.g. '/app/traces').",
    )
    max_retries: int = Field(default=0, ge=0, description="Harbor per-trial retry attempts on transient failures.")
    timeout_multiplier: float | None = Field(default=None, description="Global Harbor timeout multiplier.")
    agent_timeout_multiplier: float | None = Field(default=None, description="Agent-phase timeout multiplier.")
    verifier_timeout_multiplier: float | None = Field(default=None, description="Verifier-phase timeout multiplier.")
    agent_setup_timeout_multiplier: float | None = Field(default=None, description="Agent-setup timeout multiplier.")
    environment_build_timeout_multiplier: float | None = Field(
        default=None, description="Environment-build timeout multiplier."
    )
    reward_key: str = Field(default=DEFAULT_REWARD_KEY, description="Key read from Harbor's rewards mapping.")

    @model_validator(mode="after")
    def _agent_dir_needs_import_path(self) -> HarborRuntimeConfig:
        if self.agent_dir is not None and self.agent_import_path is None:
            raise ValueError("agent_dir only applies to a custom agent_import_path")
        return self


class HarborRewardMetric:
    """Score the verifier reward Harbor stamped onto trial metadata.

    Reads ``reward`` from the candidate metadata (populated by
    :func:`build_trials_from_job_dir`); a trial with no verifier reward scores
    ``0.0``. This is the Harbor analogue of the example ``VerifierRewardMetric``
    — a reward-off-metadata scorer.
    """

    def __init__(self, *, output_name: str = "reward", metric_type: str = "harbor_reward") -> None:
        self._output_name = output_name
        self._metric_type = metric_type

    @property
    def type(self) -> str:
        return self._metric_type

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score(self._output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        reward = input.candidate.metadata.get("reward")
        value = float(reward) if reward is not None else 0.0
        return MetricResult(outputs=[MetricOutput(name=self._output_name, value=value)])


class HarborAgentTaskRunner:
    """An :class:`AgentTaskRunner` that runs a Harbor job, then adapts its results.

    Two construction modes:

    * **Native** — pass ``config`` (a :class:`HarborRuntimeConfig`); the runtime
      builds and runs Harbor's ``JobConfig`` itself (Harbor is imported lazily).
      The dataset directory is taken from the tasks handed to :meth:`run_tasks`
      (each carries ``metadata['harbor_dataset_path']`` from
      :func:`discover_harbor_tasks`), or from an explicit ``dataset_path``
      override, so it isn't repeated. ``task_names`` optionally restricts the run
      to a subset of tasks, and the ``config``'s ``job_dir`` doubles as a cache:
      an existing run whose results already cover every requested task (with
      ``n_attempts`` completed, non-errored trials each) is re-adapted instead of
      re-run (unless ``force_rerun`` is set). Caching only takes effect when a
      stable ``job_name`` is set on the config — the default timestamped
      ``job_name`` writes a fresh dir per run and never hits the cache.
    * **Injected / offline** — pass ``job_dir`` (and optionally a ``run_job``
      callback); ``run_job`` is awaited before the job dir is read, and
      ``run_job=None`` simply adapts an already-completed job dir.

    ``job_dir`` is the directory Harbor writes its per-trial
    ``<task>__<hash>/result.json`` files into.
    """

    def __init__(
        self,
        *,
        config: HarborRuntimeConfig | None = None,
        dataset_path: str | Path | None = None,
        task_names: Sequence[str] | None = None,
        job_dir: str | Path | None = None,
        run_job: RunJob | None = None,
        reward_key: str = DEFAULT_REWARD_KEY,
    ) -> None:
        if config is None and job_dir is None:
            raise ValueError("provide either a HarborRuntimeConfig or an explicit job_dir")
        self._config = config
        self._dataset_path = Path(dataset_path) if dataset_path is not None else None
        self._task_names = task_names
        self._job_dir = Path(job_dir) if job_dir is not None else None
        self._run_job = run_job
        self._reward_key = config.reward_key if config is not None else reward_key

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalTrial]:
        """Run the Harbor job when needed, then return one trial per Harbor trial.

        In native mode the dataset directory is recovered from the tasks (each
        carries ``metadata['harbor_dataset_path']`` from
        :func:`discover_harbor_tasks`) unless a ``dataset_path`` override was given,
        so callers don't repeat it. ``job_dir`` doubles as a cache: the Harbor run
        is skipped and results are simply re-adapted when every requested task
        already has ``n_attempts`` completed, non-errored results there (unless
        ``force_rerun`` is set). The cache only engages when the config pins a
        stable ``job_name``; the default timestamped name never hits it.
        """
        if self._config is not None:
            dataset_path = self._dataset_path or _dataset_path_from_tasks(tasks)
            job_dir, run_job = _build_native_job(self._config, dataset_path, self._task_names)
            if self._config.force_rerun or not _all_tasks_cached(job_dir, tasks, n_attempts=self._config.n_attempts):
                await run_job()
            return build_trials_from_job_dir(job_dir, tasks, reward_key=self._reward_key)

        if self._job_dir is None:  # unreachable: __init__ guarantees config or job_dir
            raise ValueError("no job_dir configured")
        if self._run_job is not None:
            await self._run_job()
        return build_trials_from_job_dir(self._job_dir, tasks, reward_key=self._reward_key)


def _dataset_path_from_tasks(tasks: Sequence[AgentEvalTask]) -> Path:
    """Recover the Harbor dataset dir stamped on tasks by :func:`discover_harbor_tasks`."""
    for task in tasks:
        stamped = task.metadata.get("harbor_dataset_path")
        if isinstance(stamped, str) and stamped:
            return Path(stamped)
    raise ValueError(
        "native Harbor run needs a dataset path: pass dataset_path, or build tasks with "
        "discover_harbor_tasks/HarborTasksetLoader (which stamp metadata['harbor_dataset_path'])"
    )


def _all_tasks_cached(job_dir: Path, tasks: Sequence[AgentEvalTask], *, n_attempts: int) -> bool:
    """Return True when every requested task already has ``n_attempts`` completed results.

    Lets ``job_dir`` act as a cache so a native run whose results are all present
    is re-adapted instead of re-run. The cache is **success-aware**: only trials
    that finished without an ``exception_info`` count, and a task must have at
    least ``n_attempts`` of them, so an interrupted, errored, or under-sampled run
    is re-run rather than silently served from a partial cache. Caching only takes
    effect when a stable ``job_name`` is set on the config; with the default
    timestamped ``job_name`` every run writes a fresh dir and never hits the cache.
    """
    if not job_dir.is_dir():
        return False
    counts: dict[str, int] = {}
    for result_path in job_dir.glob("*/result.json"):
        try:
            data = json.loads(result_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("exception_info") is not None:
            continue
        name = data.get("task_name")
        if isinstance(name, str):
            counts[name] = counts.get(name, 0) + 1
    return all(counts.get(task.id, 0) >= n_attempts for task in tasks)


def _build_native_job(
    config: HarborRuntimeConfig,
    dataset_path: Path,
    task_names: Sequence[str] | None,
) -> tuple[Path, RunJob]:
    """Build a Harbor ``JobConfig`` from ``config`` and return ``(job_dir, run_job)``.

    Harbor is imported inside ``run_job`` (not at module load) because it is an
    optional extra. The job name is resolved up front so ``job_dir`` is known
    without importing Harbor. When ``agent_import_path`` is set, ``run_job``
    scopes the user's agent package into ``sys.modules`` for the run and removes
    it afterwards (see :func:`scoped_harbor_agent_import`).
    """
    job_name = config.job_name or datetime.now(timezone.utc).strftime("%Y-%m-%d__%H-%M-%S__%f")
    job_dir = config.jobs_dir / job_name

    async def run_job() -> None:
        try:
            from harbor.job import DatasetConfig, Job, JobConfig  # ty: ignore[unresolved-import]
            from harbor.models.job.config import RetryConfig  # ty: ignore[unresolved-import]
            from harbor.models.trial.config import AgentConfig, ArtifactConfig  # ty: ignore[unresolved-import]
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "the native Harbor runtime needs `harbor`, which is not an SDK dependency "
                '(it requires Python >=3.12). Install it separately: uv pip install "harbor>=0.16.1"'
            ) from exc

        if config.force_rerun and job_dir.exists():
            shutil.rmtree(job_dir)

        artifacts: list[str | ArtifactConfig] = list(config.artifacts)
        if config.trace_dir is not None:
            artifacts = [ArtifactConfig(source=config.trace_dir, destination="traces"), *artifacts]

        timeout_kwargs = {
            key: value
            for key, value in {
                "timeout_multiplier": config.timeout_multiplier,
                "agent_timeout_multiplier": config.agent_timeout_multiplier,
                "verifier_timeout_multiplier": config.verifier_timeout_multiplier,
                "agent_setup_timeout_multiplier": config.agent_setup_timeout_multiplier,
                "environment_build_timeout_multiplier": config.environment_build_timeout_multiplier,
            }.items()
            if value is not None
        }

        async def _create_and_run(agent: Any) -> None:
            job_config = JobConfig(
                job_name=job_name,
                jobs_dir=config.jobs_dir,
                n_attempts=config.n_attempts,
                n_concurrent_trials=config.n_concurrent_trials,
                quiet=config.quiet,
                retry=RetryConfig(max_retries=config.max_retries),
                artifacts=artifacts,
                agents=[agent],
                datasets=[DatasetConfig(path=dataset_path, task_names=list(task_names) if task_names else None)],
                **timeout_kwargs,
            )
            job = await Job.create(job_config)
            await job.run()

        if config.agent_import_path is None:
            await _create_and_run(AgentConfig(name=config.agent_name or "oracle", model_name=config.agent_model_name))
        elif config.agent_dir is not None:
            # Loose wrapper file: make its directory importable for the run.
            agent_dir = config.agent_dir.expanduser().resolve()
            with scoped_harbor_agent_import(agent_dir, config.agent_import_path) as scoped_import:
                await _create_and_run(AgentConfig(import_path=scoped_import, model_name=config.agent_model_name))
        else:
            # Already-importable module (installed package): let Harbor import it directly.
            await _create_and_run(AgentConfig(import_path=config.agent_import_path, model_name=config.agent_model_name))

    return job_dir, run_job


@contextlib.contextmanager
def scoped_harbor_agent_import(agent_dir: Path, import_path: str) -> Iterator[str]:
    """Make ``agent_dir`` importable under a unique synthetic package for the block.

    Args:
        agent_dir: directory containing the module referenced by ``import_path``.
        import_path: Harbor agent path, ``"module"`` or ``"module:attribute"``.

    Yields:
        str: the rewritten import path Harbor should load (the module rooted under
        the injected synthetic package, preserving any ``:attribute`` suffix).

    Raises:
        ValueError: if ``import_path`` has no module component.

    On exit the injected ``sys.modules`` entries are removed. The mutation is
    guarded by a process-wide lock so concurrent runs don't corrupt import state;
    each run gets its own uniquely-named package so distinct agents never collide.

    Only ``agent_dir`` (not ``sys.path``) is made importable, so a loose wrapper
    must be self-contained: a single module, or one that reaches siblings via
    relative imports (``from .helper import ...``). A wrapper that does an absolute
    ``import helper`` of a sibling file won't resolve — install it as a package and
    use the ``agent_dir``-less path instead.
    """
    module_name, sep, attribute = import_path.partition(":")
    module_name = module_name.strip().lstrip(".")
    if not module_name:
        raise ValueError("import_path must be 'module' or 'module:attribute'")
    package = f"{_AGENT_IMPORT_ROOT}.{_safe_identifier(agent_dir.name)}_{uuid4().hex[:8]}"
    with _IMPORT_LOCK:
        _install_agent_package(package, agent_dir)
    try:
        scoped = f"{package}.{module_name}"
        yield f"{scoped}:{attribute}" if sep else scoped
    finally:
        with _IMPORT_LOCK:
            _uninstall_agent_package(package)


def _safe_identifier(value: str) -> str:
    """Turn an arbitrary directory name into a valid Python identifier."""
    identifier = re.sub(r"\W+", "_", value).strip("_")
    if not identifier:
        return "agent"
    return identifier if identifier[0].isalpha() or identifier[0] == "_" else f"_{identifier}"


def _install_agent_package(package: str, agent_dir: Path) -> None:
    """Register ``package`` (and its parents) in ``sys.modules`` rooted at ``agent_dir``."""
    parts = package.split(".")
    for idx in range(1, len(parts) + 1):
        name = ".".join(parts[:idx])
        if name not in sys.modules:
            module = ModuleType(name)
            module.__path__ = []  # namespace package; leaf __path__ is set below
            module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
            sys.modules[name] = module
            if idx > 1:
                setattr(sys.modules[".".join(parts[: idx - 1])], parts[idx - 1], module)
    sys.modules[package].__path__ = [str(agent_dir)]


def _uninstall_agent_package(package: str) -> None:
    """Remove ``package`` and any submodules imported through it from ``sys.modules``."""
    for name in [n for n in sys.modules if n == package or n.startswith(f"{package}.")]:
        sys.modules.pop(name, None)
    parent, _, child = package.rpartition(".")
    parent_module = sys.modules.get(parent)
    if parent_module is not None:
        with contextlib.suppress(AttributeError):
            delattr(parent_module, child)


def build_trials_from_job_dir(
    job_dir: str | Path,
    tasks: Sequence[AgentEvalTask],
    *,
    reward_key: str = DEFAULT_REWARD_KEY,
) -> list[AgentEvalTrial]:
    """Adapt Harbor's per-trial ``result.json`` files into :class:`AgentEvalTrial` objects.

    Reads ``<job_dir>/<task>__<hash>/result.json`` (the top-level aggregate
    ``<job_dir>/result.json`` is skipped because it is not nested). Each Harbor
    trial whose ``task_name`` matches a supplied task id becomes one trial, with
    the verifier reward, exception type, and token/cost measurements stamped on
    ``metadata`` and standard evidence descriptors pointing at the trial's
    on-disk artifacts.
    """
    job_path = Path(job_dir)
    known_task_ids = {task.id for task in tasks}
    trials: list[AgentEvalTrial] = []
    for result_path in sorted(job_path.glob("*/result.json")):
        try:
            data = json.loads(result_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable Harbor trial result %s: %s", result_path, exc)
            continue
        task_id = data.get("task_name")
        if task_id not in known_task_ids:
            # Trial for a task we weren't asked to score (e.g. a wider dataset run).
            continue
        trials.append(_trial_from_harbor_result(result_path.parent, data, reward_key=reward_key))

    # Surface tasks that produced no trial loudly: a mis-pointed job_dir or a
    # crashed run would otherwise silently score fewer tasks than requested.
    missing = known_task_ids - {trial.task_id for trial in trials}
    if missing:
        logger.warning("No Harbor trial result found for %d requested task(s): %s", len(missing), sorted(missing))
    if not trials:
        logger.warning(
            "No Harbor trial results under %s matched the requested tasks; nothing will be scored.", job_path
        )
    return trials


def _trial_from_harbor_result(trial_dir: Path, data: Mapping[str, Any], *, reward_key: str) -> AgentEvalTrial:
    task_id = str(data["task_name"])
    trial_id = str(data.get("trial_name") or trial_dir.name)
    rewards = _rewards_mapping(data)
    reward = _primary_reward(rewards, reward_key)
    exception_type = _exception_type(data.get("exception_info"))

    metadata: dict[str, Any] = {
        "reward": reward,
        "reward_details": dict(rewards),
        "harbor_trial_dir": str(trial_dir),
    }
    if exception_type is not None:
        metadata["exception_type"] = exception_type
    metadata.update(_token_measurements(data.get("agent_result")))

    # An errored trial (or one with no reward) stays PARTIAL so it is still scored
    # as 0 and counted in the summary; FAILED would exclude it from scoring.
    status = (
        AgentEvalTrialStatus.COMPLETED
        if exception_type is None and reward is not None
        else AgentEvalTrialStatus.PARTIAL
    )

    trace_path = trial_dir / "agent" / "trajectory.json"
    descriptors = standard_evidence_descriptors(
        logs_dir=trial_dir / "agent",
        final_state_dir=trial_dir / "artifacts",
        trace_path=trace_path if trace_path.exists() else None,
        verifier_logs_dir=trial_dir / "verifier",
    )

    return AgentEvalTrial(
        id=trial_id,
        task_id=task_id,
        status=status,
        output=AgentOutput(metadata={"harbor_trial_dir": str(trial_dir)}),
        evidence=CandidateEvidence(descriptors=descriptors),
        metadata=metadata,
    )


def _rewards_mapping(data: Mapping[str, Any]) -> dict[str, float]:
    verifier_result = data.get("verifier_result")
    if not isinstance(verifier_result, Mapping):
        return {}
    rewards = verifier_result.get("rewards")
    if not isinstance(rewards, Mapping):
        return {}
    out: dict[str, float] = {}
    for key, value in rewards.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _primary_reward(rewards: Mapping[str, float], reward_key: str) -> float | None:
    """Return the single reward a trial is scored on.

    Returns the reward named by ``reward_key`` when the verifier emitted it.
    Returns ``None`` otherwise (the trial is treated as having no reward, so it
    stays PARTIAL rather than scoring a misleading 0.0): if the verifier emitted
    rewards but none matches ``reward_key`` a warning is logged, since we do not
    guess among the emitted rewards (point ``reward_key`` at the intended one, or
    score the others with additional metrics over ``reward_details``).
    """
    if reward_key in rewards:
        return rewards[reward_key]
    if rewards:
        logger.warning(
            "Harbor trial emitted rewards %s but none matches reward_key=%r; treating the trial as having no reward",
            sorted(rewards),
            reward_key,
        )
    return None


def _exception_type(exception_info: Any) -> str | None:
    if exception_info is None:
        return None
    if isinstance(exception_info, Mapping):
        for key in ("exception_type", "type", "name", "class"):
            value = exception_info.get(key)
            if isinstance(value, str) and value:
                return value
        return "UnknownException"
    return str(exception_info)


def _token_measurements(agent_result: Any) -> dict[str, int | float]:
    """Map Harbor's ``agent_result`` token counts onto SDK ``TrialMeasurements`` keys."""
    if not isinstance(agent_result, Mapping):
        return {}
    mapping = {
        "prompt_tokens": "n_input_tokens",
        "completion_tokens": "n_output_tokens",
        "cache_read_tokens": "n_cache_tokens",
    }
    out: dict[str, int | float] = {}
    for sdk_key, harbor_key in mapping.items():
        value = agent_result.get(harbor_key)
        if isinstance(value, int) and not isinstance(value, bool):
            out[sdk_key] = value
    cost = agent_result.get("cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        out["cost_usd"] = float(cost)
    return out


def _harbor_task_dirs(dataset_path: Path) -> list[Path]:
    """Return the Harbor task folders under ``dataset_path`` (or itself if it is one)."""
    if (dataset_path / _TASK_CONFIG_FILENAME).is_file():
        return [dataset_path]
    return sorted(
        path
        for path in dataset_path.iterdir()
        if path.is_dir() and path.name != _TASK_TEMPLATE_DIRNAME and (path / _TASK_CONFIG_FILENAME).is_file()
    )


def discover_harbor_tasks(dataset_path: str | Path) -> list[AgentEvalTask]:
    """Build one :class:`AgentEvalTask` per Harbor task folder in ``dataset_path``.

    Mirrors Harbor's own local-dataset discovery: every immediate subdirectory
    with a ``task.toml`` is a task. The task id is read from ``[task] name`` so it
    matches the ``task_name`` Harbor writes into each trial's ``result.json``, and
    each task is scored by a :class:`HarborRewardMetric`.

    Raises:
        ValueError: if a task's ``task.toml`` or ``instruction.md`` is malformed or
            unreadable — the offending path is named. A discovered task is never
            silently dropped, since that would quietly shrink eval coverage.
    """
    dataset_path = Path(dataset_path)
    tasks: list[AgentEvalTask] = []
    for task_dir in _harbor_task_dirs(dataset_path):
        config_path = task_dir / _TASK_CONFIG_FILENAME
        try:
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"malformed Harbor task config at {config_path}: {exc}") from exc
        task_name = config.get("task", {}).get("name", task_dir.name)
        instruction_path = task_dir / "instruction.md"
        try:
            intent = instruction_path.read_text(encoding="utf-8").strip() if instruction_path.is_file() else task_name
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"unreadable Harbor instruction at {instruction_path}: {exc}") from exc
        tasks.append(
            AgentEvalTask(
                id=task_name,
                intent=intent,
                inputs={"instruction": intent},
                metrics=[HarborRewardMetric()],
                metadata={"harbor_dataset_path": str(dataset_path), "harbor_task_dir": str(task_dir)},
            )
        )
    return tasks


class HarborTasksetLoader:
    """Load a Harbor local-dataset directory as an :class:`AgentEvalTaskset`.

    Implements the :class:`AgentEvalTasksetLoader` protocol so "dataset dir in →
    tasks out" is a single call.
    """

    def __init__(self, dataset_path: str | Path, *, name: str = "harbor") -> None:
        self._dataset_path = Path(dataset_path)
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def load(
        self,
        *,
        source: str | Path | None = None,
        limit: int | None = None,
        evidence_dir: Path | None = None,
    ) -> AgentEvalTaskset:
        """Discover Harbor tasks under ``source`` (or the configured path) into a taskset."""
        dataset_path = Path(source) if source is not None else self._dataset_path
        tasks = discover_harbor_tasks(dataset_path)
        if limit is not None:
            tasks = tasks[:limit]
        return AgentEvalTaskset(tasks=tasks, metadata={"harbor_dataset_path": str(dataset_path)})


async def run_harbor_eval(
    config: HarborRuntimeConfig,
    dataset_path: str | Path,
    *,
    task_names: Sequence[str] | None = None,
    metrics: Sequence[Metric] | None = None,
    run_config: AgentEvalRunConfig | None = None,
) -> AgentEvalResult:
    """Run a Harbor dataset natively and score it — the minimal-plumbing entry point.

    Loads the taskset from ``dataset_path``, runs Harbor via ``config``, and scores
    through :class:`AgentEvaluator`. Tasks are scored by :class:`HarborRewardMetric`
    unless ``metrics`` overrides them. Returns the scored :class:`AgentEvalResult`.
    """
    from nemo_platform.beta.evaluator.agent_eval.evaluator import AgentEvaluator

    dataset_path = Path(dataset_path)
    tasks = HarborTasksetLoader(dataset_path).load().tasks
    if task_names is not None:
        wanted = set(task_names)
        tasks = [task for task in tasks if task.id in wanted]
    if metrics is not None:
        tasks = [task.model_copy(update={"metrics": list(metrics)}) for task in tasks]

    runner = HarborAgentTaskRunner(config=config, task_names=task_names)
    return await AgentEvaluator().run(
        tasks=tasks,
        target=runner,
        config=run_config or AgentEvalRunConfig(write_dashboard=False),
    )


def reward_payload_from_result(
    result: AgentEvalResult,
    *,
    reward_key: str = DEFAULT_REWARD_KEY,
) -> dict[str, Any]:
    """Reconstruct the optimizer's legacy ``{reward, reward_details, exceptions}`` payload.

    Phase-1 adapter so consumers that still expect Harbor's aggregate shape can
    read it off an :class:`AgentEvalResult`:

    * ``reward`` — mean of each metric output, keyed ``"<metric_type>.<output>"``.
    * ``reward_details`` — ``{output: {value_str: [task_id, ...]}}`` grouped from
      per-trial scores (Harbor's ``reward_stats`` analogue).
    * ``exceptions`` — ``{exception_type: [task_id, ...]}`` from trial metadata
      (Harbor's ``exception_stats`` analogue).
    """
    reward = {score.name: score.mean for score in result.summary.scores.scores if score.mean is not None}

    reward_details: dict[str, dict[str, list[str]]] = {}
    for score in result.scores:
        if score.status == AgentEvalScoreStatus.FAILED:
            continue
        for output in score.outputs:
            value = output.value
            value_str = (
                str(float(value)) if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
            )
            reward_details.setdefault(output.name, {}).setdefault(value_str, []).append(score.task_id)

    exceptions: dict[str, list[str]] = {}
    for trial in result.trials:
        exc = trial.metadata.get("exception_type")
        if isinstance(exc, str) and exc:
            exceptions.setdefault(exc, []).append(trial.task_id)

    return {
        "reward": reward,
        "reward_details": reward_details,
        "exceptions": exceptions,
    }


__all__ = [
    "DEFAULT_REWARD_KEY",
    "HarborAgentTaskRunner",
    "HarborRewardMetric",
    "HarborRuntimeConfig",
    "HarborTasksetLoader",
    "build_trials_from_job_dir",
    "discover_harbor_tasks",
    "reward_payload_from_result",
    "run_harbor_eval",
    "scoped_harbor_agent_import",
]
