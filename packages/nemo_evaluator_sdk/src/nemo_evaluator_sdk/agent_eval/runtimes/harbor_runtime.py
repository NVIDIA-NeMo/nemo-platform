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
import hashlib
import importlib.machinery
import json
import logging
import os
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

from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask, AgentEvalTaskset
from nemo_evaluator_sdk.agent_eval.trials import (
    AgentEvalTrial,
    AgentEvalTrialStatus,
    AgentOutput,
    standard_evidence_descriptors,
)
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values.evidence import CandidateEvidence
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
# Records which inputs produced a job dir, so a rerun can tell a reusable cache from
# a stale one. A file, not a directory: Harbor rmtree's stray directories in a job dir.
CACHE_STAMP_FILENAME = ".nemo-eval-harbor-cache.json"
# Public so downstreams can assert the SDK is new enough to own cache staleness.
CACHE_STAMP_VERSION = 1
# Excluded from the cache fingerprint — see :func:`_cache_stamp` for why each one.
_CACHE_IRRELEVANT_OPTIONS = frozenset(
    {"jobs_dir", "job_name", "force_rerun", "quiet", "n_concurrent_trials", "agent_dir", "reward_key"}
)
# Derived/VCS noise skipped when digesting a directory. Deliberately NOT skipped:
# `node_modules` and other vendored dependency trees, which ship with the agent and
# change what it does. `.venv`/`.uv` stay skipped because they are environment, not
# deliverable — the Harbor wrapper does not upload them into the task container.
_DIGEST_SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", ".uv", ".mypy_cache", ".pytest_cache"})
_DIGEST_CHUNK_BYTES = 1 << 20

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
        so callers don't repeat it.

        ``job_dir`` doubles as a cache, and it is reused only when **both** hold:
        every requested task already has ``n_attempts`` completed, non-errored
        results there, *and* the directory carries a cache stamp matching this run's
        inputs (agent contents, task contents, result-affecting options). Anything
        else re-runs from scratch — the directory is discarded rather than handed to
        Harbor, because a surviving directory plus a changed agent is exactly the
        case Harbor itself refuses.

        The cache only engages when the config pins a stable ``job_name``; with the
        default timestamped name no fingerprint is computed at all.

        Assumes a **single writer per job directory**. Neither this runtime nor
        Harbor locks it, so two processes sharing a pinned ``job_name`` on a shared
        volume will race.
        """
        if self._config is not None:
            dataset_path = self._dataset_path or _dataset_path_from_tasks(tasks)
            job_name, job_dir = _resolve_job_dir(self._config)

            # Only fingerprint when the answer can depend on it: an unpinned job name
            # can never hit, and force_rerun/a missing dir already decided. This keeps
            # the digest I/O off every run of callers that don't pin a job name.
            stamp: dict[str, Any] | None = None
            if self._config.job_name is None or self._config.force_rerun or not job_dir.is_dir():
                stale = True
            else:
                stamp = _cache_stamp(self._config, dataset_path, tasks)
                stale = _cache_is_stale(job_dir, stamp)

            if stale or not _all_tasks_cached(job_dir, tasks, n_attempts=self._config.n_attempts):
                job_dir, run_job = _build_native_job(
                    self._config,
                    dataset_path,
                    self._task_names,
                    job_name=job_name,
                    # Discard when the inputs changed, and whenever `agent_dir` is
                    # set: Harbor bakes a fresh uuid into the scoped agent import
                    # path, so its own JobConfig never matches on a rerun and it
                    # raises FileExistsError instead of resuming. With `agent_dir`
                    # unset the AgentConfig is deterministic, so leaving force_rerun
                    # off lets Harbor resume per trial and keep completed work.
                    force_rerun=(self._config.force_rerun or stale or self._config.agent_dir is not None),
                )
                # Fingerprint the inputs *before* running and confirm they are
                # unchanged afterwards. Stamping only the post-run state would label
                # results produced from the old sources with the new fingerprint, so
                # a later run would happily serve them. Covers what Harbor actually
                # ran: with no task_names filter that is the whole dataset, and
                # recording only the requested subset would make the next full-set
                # run look stale and re-run a complete job dir.
                coverage = _stamp_coverage(dataset_path, tasks, self._task_names)
                before = _cache_stamp(self._config, dataset_path, coverage)
                await run_job()
                if self._config.job_name is not None:
                    after = _cache_stamp(self._config, dataset_path, coverage)
                    if after == before:
                        _write_cache_stamp(job_dir, after)
                    else:
                        # Leaving it unstamped re-runs next time, which is the safe
                        # direction: we cannot say which inputs produced these results.
                        logger.warning(
                            "Agent or task contents changed while Harbor job %s was running; leaving it unstamped "
                            "so the next run re-executes rather than trusting these results.",
                            job_dir,
                        )
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


def _feed(digest: "hashlib._Hash", label: bytes, payload: bytes) -> None:
    """Append a length-framed field to ``digest``.

    Framing matters: concatenating ``name \0 content \0`` is ambiguous because file
    *contents* may contain NUL, so two different trees can produce an identical byte
    stream. Prefixing every variable-length field with its length makes the encoding
    injective, which is what stops a collision from being read as "unchanged".
    """
    digest.update(label)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _safe_resolve(path: Path) -> Path:
    """``Path.resolve()`` that degrades instead of raising.

    ``resolve()`` calls ``os.readlink`` internally, so a symlink that disappears
    mid-walk propagates ``OSError`` out of it. The digest is a best-effort guard, not
    a reason to fail a run that would otherwise succeed, so fall back to the
    unresolved absolute path.
    """
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _is_executable(path: Path) -> bool:
    """Whether the owner-execute bit is set, following symlinks.

    Only the execute bit, mirroring what git tracks: read/write bits vary with umask
    and would evict the cache for nothing, but flipping +x on ``tests/test.sh`` or an
    agent entrypoint genuinely changes what Harbor does.
    """
    try:
        return bool(path.stat().st_mode & 0o100)
    except OSError:
        return False


def _digest_directory(root: Path, *, exclude: frozenset[Path] = frozenset()) -> str:
    """Content-hash a directory tree, skipping build/VCS noise and excluded roots.

    Contents rather than mtimes: callers routinely materialize the directory with
    ``copytree`` (the optimizer does, per candidate), which rewrites every mtime and
    would defeat the cache entirely.

    ``exclude`` takes *resolved* directories to skip wholesale. It exists because
    ``jobs_dir`` is caller-chosen and may sit **under** the dataset or agent
    directory; without excluding it the digest would hash the growing results tree
    it is meant to validate, and would never stabilize.

    Symlinks are **followed**, not skipped. Skipping them silently defeats the whole
    guard: a directory assembled out of links to shared sources would hash to the
    empty digest, so edits behind those links would never invalidate the cache. The
    link target is folded in alongside the contents, so re-pointing a link is a
    change even when both targets happen to hold identical bytes.

    Unreadable or vanished files are folded in as a marker rather than raised: a
    transient read failure must not kill a run that would otherwise have succeeded.
    """
    digest = hashlib.sha256()
    if not root.is_dir():
        return digest.hexdigest()
    # Keep only exclusions strictly *inside* this tree. An excluded root that is an
    # ancestor of (or equal to) `root` would otherwise match every entry and yield
    # an empty digest — silently disabling invalidation for the whole directory,
    # which is exactly the failure this function exists to prevent. jobs_dir being
    # a parent of the agent/task dir is a legitimate layout, not a reason to stop
    # hashing it.
    root_resolved = _safe_resolve(root)
    excluded = {
        resolved
        for resolved in (_safe_resolve(path) for path in exclude)
        if resolved != root_resolved and resolved.is_relative_to(root_resolved)
    }
    # Resolved dirs already walked, so a symlink cycle terminates instead of hanging.
    visited: set[Path] = set()

    def walk(directory: Path) -> None:
        resolved_dir = _safe_resolve(directory)
        if resolved_dir in visited:
            return
        visited.add(resolved_dir)
        try:
            entries = sorted(directory.iterdir())
        except OSError as exc:
            logger.warning("Could not list %s while fingerprinting %s: %s", directory, root, exc)
            _feed(digest, b"unlistable", b"")
            return
        for path in entries:
            if path.name in _DIGEST_SKIP_DIRS:
                continue
            resolved = _safe_resolve(path)
            if any(resolved == item or item in resolved.parents for item in excluded):
                continue

            _feed(digest, b"name", path.relative_to(root).as_posix().encode("utf-8"))
            _feed(digest, b"mode", b"x" if _is_executable(path) else b"-")
            if path.is_symlink():
                # Record where the link points, so retargeting counts as a change.
                try:
                    target = os.readlink(path).encode("utf-8")
                except OSError as exc:
                    # The link vanished mid-walk. Same contract as an unreadable
                    # file: degrade to a marker rather than kill the run.
                    logger.warning("Could not read link %s while fingerprinting %s: %s", path, root, exc)
                    target = b"<unreadable-link>"
                _feed(digest, b"symlink", target)
            if path.is_dir():
                _feed(digest, b"dir", b"")
                walk(path)
                continue
            if not path.is_file():
                # Broken link, socket, fifo: nothing to hash, but its presence counts.
                _feed(digest, b"not-a-file", b"")
                continue
            content = hashlib.sha256()
            try:
                with path.open("rb") as handle:
                    # Streamed: Harbor datasets may ship large seeds or build contexts.
                    for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
                        content.update(chunk)
            except OSError as exc:
                logger.warning("Could not read %s while fingerprinting %s: %s", path, root, exc)
                content.update(b"<unreadable>")
            # The sub-digest is fixed width, so file bytes can never be confused with
            # the framing around them.
            _feed(digest, b"file", content.digest())

    walk(root)
    return digest.hexdigest()


def _task_dirs_for(dataset_path: Path, tasks: Sequence[AgentEvalTask]) -> dict[str, Path | None]:
    """Resolve each task's on-disk directory, falling back to re-discovery.

    :func:`discover_harbor_tasks` stamps ``metadata['harbor_task_dir']``, but callers
    may build :class:`AgentEvalTask` objects by hand (the Evaluator plugin builds
    them from a job spec), so the metadata is not guaranteed.

    A task that cannot be resolved maps to ``None`` — the caller must treat that as
    un-cacheable rather than silently omitting it from the fingerprint, which would
    be a stale-cache hole.
    """
    dataset_root = dataset_path.resolve()
    resolved: dict[str, Path | None] = {}
    for task in tasks:
        stamped = task.metadata.get("harbor_task_dir")
        candidate = Path(stamped) if isinstance(stamped, str) and stamped else None
        # The stamp records where a task was *discovered*, which is not necessarily
        # where this run executes it: `dataset_path` can be overridden on the runner.
        # Trusting a stale or foreign path would fingerprint one dataset while Harbor
        # runs another, so anything missing or outside the active dataset is dropped
        # and re-discovered below.
        if candidate is not None:
            candidate_resolved = candidate.resolve()
            if not candidate.is_dir() or not candidate_resolved.is_relative_to(dataset_root):
                logger.debug(
                    "Ignoring stamped harbor_task_dir %s for task %r: not a directory under the active dataset %s",
                    candidate,
                    task.id,
                    dataset_root,
                )
                candidate = None
        resolved[task.id] = candidate
    if all(path is not None for path in resolved.values()):
        return resolved

    try:
        discovered = {
            task.id: Path(str(task.metadata["harbor_task_dir"])) for task in discover_harbor_tasks(dataset_path)
        }
    except (OSError, ValueError) as exc:
        # discover_harbor_tasks raises on ANY malformed task.toml in the dataset.
        # Refusing the cache is the safe reading; failing the run is not, since this
        # path previously never read those files.
        logger.warning(
            "Could not resolve Harbor task dirs under %s; treating the cache as stale: %s", dataset_path, exc
        )
        return dict.fromkeys(resolved, None)
    return {task_id: path or discovered.get(task_id) for task_id, path in resolved.items()}


def _stamp_coverage(
    dataset_path: Path,
    tasks: Sequence[AgentEvalTask],
    task_names: Sequence[str] | None,
) -> Sequence[AgentEvalTask]:
    """Tasks a written stamp must cover: everything Harbor was asked to run.

    ``task_names`` is the filter handed to Harbor's ``DatasetConfig``. When it is
    ``None`` Harbor runs every task in the dataset, which can be a superset of the
    tasks this call was asked to score — and a stamp that recorded only the smaller
    set would report the larger one as stale on the next run.
    """
    if task_names is not None:
        return tasks
    try:
        discovered = discover_harbor_tasks(dataset_path)
    except (OSError, ValueError):
        # Same reasoning as _task_dirs_for: a malformed sibling task must not fail a
        # run. Recording only the requested tasks just costs a re-run later.
        return tasks
    covered = {task.id: task for task in discovered}
    covered.update({task.id: task for task in tasks})
    return list(covered.values())


def _cache_stamp(
    config: HarborRuntimeConfig,
    dataset_path: Path,
    tasks: Sequence[AgentEvalTask],
) -> dict[str, Any]:
    """Fingerprint the inputs that decide whether a job dir can be reused.

    Covers the result-affecting options, the contents of ``agent_dir``, and the
    contents of every task directory. Two gaps are deliberate and worth knowing
    before trusting a hit: when ``agent_dir`` is ``None`` the agent is an already
    importable module, so only its *import path* is fingerprinted and edits to that
    installed package are invisible; and a task whose directory cannot be resolved
    is recorded as ``<unresolved>``, which always forces a re-run.

    Recorded per task rather than as one job-wide hash so that evaluating a
    **subset** of a previously-cached job still hits: staleness is decided only over
    the tasks actually requested.

    Excluded from the option hash: presentation and placement knobs (``quiet``,
    ``n_concurrent_trials``, ``jobs_dir``, ``job_name``, ``force_rerun``), which
    change nothing about the results; ``agent_dir``, an absolute path whose
    *content* is hashed separately, so a relocated but identical agent still hits;
    and ``reward_key``, which only selects which reward
    :func:`build_trials_from_job_dir` reads back and must not cost a Docker re-run.
    """
    options = config.model_dump(exclude=set(_CACHE_IRRELEVANT_OPTIONS), mode="json")
    excluded_roots = frozenset({config.jobs_dir.expanduser().resolve()})

    agent_digest = "<none>"
    if config.agent_dir is not None:
        agent_digest = _digest_directory(config.agent_dir.expanduser().resolve(), exclude=excluded_roots)

    task_digests: dict[str, str] = {}
    for task_id, task_dir in sorted(_task_dirs_for(dataset_path, tasks).items()):
        task_digests[task_id] = (
            "<unresolved>" if task_dir is None else _digest_directory(task_dir.resolve(), exclude=excluded_roots)
        )

    return {
        "version": CACHE_STAMP_VERSION,
        "options": hashlib.sha256(json.dumps(options, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        "agent": agent_digest,
        "tasks": task_digests,
    }


def _cache_is_stale(job_dir: Path, stamp: Mapping[str, Any]) -> bool:
    """Return True when ``job_dir`` was not produced by the inputs in ``stamp``.

    A directory with no stamp is stale: it predates this check, or was written by
    plain Harbor, and re-running is the safe reading. An ``<unresolved>`` task
    digest is likewise always stale — we could not prove the inputs match. A
    directory that does not exist is stale too: there is nothing there to reuse, and
    answering "not stale" would be an invitation to serve zero trials.
    """
    if not job_dir.is_dir():
        return True
    try:
        stored = json.loads((job_dir / CACHE_STAMP_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stored = None

    reason: str | None = None
    if not isinstance(stored, Mapping):
        reason = "no usable cache stamp"
    elif stored.get("version") != stamp["version"]:
        reason = "cache stamp version changed"
    elif stored.get("options") != stamp["options"]:
        reason = "a result-affecting option changed"
    elif stored.get("agent") != stamp["agent"]:
        reason = "the agent directory changed"
    else:
        stored_tasks = stored.get("tasks")
        stored_tasks = stored_tasks if isinstance(stored_tasks, Mapping) else {}
        for task_id, digest in stamp["tasks"].items():
            if digest == "<unresolved>":
                reason = f"task {task_id!r} could not be resolved on disk"
                break
            if stored_tasks.get(task_id) != digest:
                reason = f"task {task_id!r} changed or was not part of the cached run"
                break

    if reason is None:
        return False
    logger.info("Re-running Harbor job %s instead of serving it from cache: %s.", job_dir, reason)
    return True


def _write_cache_stamp(job_dir: Path, stamp: Mapping[str, Any]) -> None:
    """Record the inputs a completed job dir was produced from.

    Best-effort: a job dir that could not be stamped simply re-runs next time, which
    is the safe direction. Written as a *file* deliberately — Harbor deletes any
    stray *directory* in a job dir that lacks ``result.json``.
    """
    try:
        (job_dir / CACHE_STAMP_FILENAME).write_text(
            json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not stamp Harbor job dir %s with its cache key: %s", job_dir, exc)


def _resolve_job_dir(config: HarborRuntimeConfig) -> tuple[str, Path]:
    """Resolve ``(job_name, job_dir)`` without importing Harbor.

    Split out from :func:`_build_native_job` because the caller must know the job
    directory *before* deciding whether to run: an unpinned ``job_name`` is a
    timestamp with microsecond precision, so resolving it twice would yield two
    different directories and the cache decision would be made about the wrong one.
    """
    job_name = config.job_name or datetime.now(timezone.utc).strftime("%Y-%m-%d__%H-%M-%S__%f")
    return job_name, config.jobs_dir / job_name


def _build_native_job(
    config: HarborRuntimeConfig,
    dataset_path: Path,
    task_names: Sequence[str] | None,
    *,
    job_name: str | None = None,
    force_rerun: bool | None = None,
) -> tuple[Path, RunJob]:
    """Build a Harbor ``JobConfig`` from ``config`` and return ``(job_dir, run_job)``.

    Harbor is imported inside ``run_job`` (not at module load) because it is an
    optional extra. The job name is resolved up front so ``job_dir`` is known
    without importing Harbor. When ``agent_import_path`` is set, ``run_job``
    scopes the user's agent package into ``sys.modules`` for the run and removes
    it afterwards (see :func:`scoped_harbor_agent_import`).

    Args:
        job_name: Pre-resolved job name from :func:`_resolve_job_dir`. Pass it when
            the caller already resolved the directory, so an unpinned name is not
            re-generated into a different timestamp.
        force_rerun: Overrides ``config.force_rerun`` for this build. Passed rather
            than applied via ``model_copy`` so the caller's config is never mutated
            and the job name stays fixed.
    """
    resolved_name = job_name if job_name is not None else _resolve_job_dir(config)[0]
    job_dir = config.jobs_dir / resolved_name
    effective_force_rerun = config.force_rerun if force_rerun is None else force_rerun

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

        if effective_force_rerun and job_dir.exists():
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
                job_name=resolved_name,
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
            instruction = (
                instruction_path.read_text(encoding="utf-8").strip() if instruction_path.is_file() else task_name
            )
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"unreadable Harbor instruction at {instruction_path}: {exc}") from exc
        tasks.append(
            AgentEvalTask(
                id=task_name,
                # `intent` is human-facing metadata, never shown to the agent; the task name is the
                # only human label Harbor's task.toml provides. The instruction the agent acts on
                # lives in `inputs["instruction"]`.
                intent=task_name,
                inputs={"instruction": instruction},
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
    from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator

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
    "CACHE_STAMP_FILENAME",
    "CACHE_STAMP_VERSION",
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
