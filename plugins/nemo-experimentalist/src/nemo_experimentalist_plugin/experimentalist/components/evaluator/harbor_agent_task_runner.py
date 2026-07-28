# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor evaluator that delegates orchestration to the NeMo Evaluator SDK.

``HarborEvaluator`` builds Harbor's ``JobConfig`` and drives ``Job`` itself. This
evaluator hands that job to the SDK's ``HarborAgentTaskRunner`` instead: the SDK
owns the ``JobConfig``, the success-aware job-directory cache, and the scoped
agent import. Harbor still does the work underneath — the difference is who owns
the orchestration.

Results are read back off the Harbor job directory through the same
:func:`~...evaluator.harbor.trials_from_job_dir` adapter the plain evaluator uses,
so both evaluator types produce equivalent :class:`TrialResult` objects. The SDK's
own trial model is deliberately not the contract here: its default score model
exposes a single ``harbor_reward.reward``, while the Experimentalist loop needs
every verifier metric (``format_ok`` and friends), short task ids, attempt
indices, and trace/artifact references.

The SDK is imported lazily inside :meth:`HarborRunnerEvaluator._run`, so
a missing or partial SDK install only breaks this evaluator type — importing the
plain Harbor evaluator keeps working.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorType,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    _TRACE_ARTIFACT_SOURCE,
    HarborDataset,
    resolve_harbor_run_inputs,
    trials_from_job_dir,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    Dataset,
    TrialResult,
    local_path_from_uri,
)
from pydantic import ConfigDict, Field

if TYPE_CHECKING:
    # Imported for annotations only. A regular import would defeat the lazy-import
    # contract in this module's docstring: a broken SDK install must not break
    # importing (and therefore using) the plain Harbor evaluator.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
        HarborAgentTaskRunner,
        HarborRuntimeConfig,
    )
    from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask

logger = logging.getLogger(__name__)

_SDK_INSTALL_HINT = (
    "The 'harbor_agent_task_runner' evaluator needs the NeMo Evaluator SDK "
    "(nemo-evaluator-sdk). Install it, or set evaluator_type to 'harbor' to use "
    "the built-in Harbor evaluator instead."
)


_CACHE_KEY_FILENAME = ".experimentalist-cache-key"
# Never part of the fingerprint: these change how a run is *presented* or where it
# is stored, not what it produces. Including them would evict a usable cache for
# nothing (e.g. flipping `quiet` in a config).
_CACHE_IRRELEVANT_OPTIONS = frozenset({"force_rerun", "jobs_dir", "job_name", "quiet", "n_concurrent_trials"})
# Skipped when digesting a directory: build/VCS noise, plus the experiment tree
# itself, which is where results land and would otherwise make every run differ.
_DIGEST_SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules", ".uv", "eval-and-optimize"})


class HarborTaskNameError(ValueError):
    """A dataset task could not be mapped onto exactly one Harbor task name."""


class HarborRunnerConfig(EvaluatorConfig):
    """Configuration for the SDK-backed Harbor evaluator.

    Every field maps onto exactly one ``HarborRuntimeConfig`` field. Unknown keys
    are rejected rather than silently ignored: several plain-``HarborEvaluator``
    options (notably the full ``retry`` model) have no unambiguous SDK equivalent,
    so passing them here is a configuration error, not a no-op.

    ``agent_dir`` is deliberately absent — it is always derived from the candidate
    being evaluated, so a config cannot point the run at a different agent.

    One asymmetry to know when A/B-ing against ``HarborEvaluatorConfig``: at their
    defaults the two are equivalent (Harbor resolves an unset phase multiplier to
    the global ``timeout_multiplier``, which defaults to ``1.0``), but they diverge
    once tuned. This config exposes the global ``timeout_multiplier`` and leaves the
    phase multipliers unset so they inherit it; the plain config has no global knob
    and pins each phase to ``1.0``, which masks it. Set the phase multipliers
    explicitly on both sides when comparing non-default timeouts.
    """

    model_config = ConfigDict(extra="forbid")

    job_name: str | None = Field(
        default=None,
        description=(
            "Harbor job name. Defaults to the loop's deterministic '<candidate>-<dataset>', "
            "which is what makes the SDK's success-aware job-dir cache usable."
        ),
    )
    jobs_dir: Path = Field(
        default=Path("eval-and-optimize") / "results",
        description="Directory to store job results, resolved relative to the experiment directory.",
    )
    n_attempts: int = Field(default=1, ge=1, description="Number of attempts Harbor runs per task.")
    n_concurrent_trials: int = Field(
        default=os.cpu_count() or 4, ge=1, description="Maximum number of concurrent Harbor trials."
    )
    quiet: bool = Field(default=False, description="Suppress Harbor's trial progress display.")
    artifacts: list[str] = Field(default=[], description="Additional Harbor artifact sources to collect per trial.")
    trace_dir: str = Field(
        default=_TRACE_ARTIFACT_SOURCE,
        description="Container path of agent traces, collected into the trial's 'traces' artifact directory.",
    )
    max_retries: int = Field(default=0, ge=0, description="Harbor per-trial retries on transient failures.")
    timeout_multiplier: float | None = Field(default=None, description="Global Harbor timeout multiplier.")
    agent_timeout_multiplier: float | None = Field(default=None, description="Agent-phase timeout multiplier.")
    verifier_timeout_multiplier: float | None = Field(default=None, description="Verifier-phase timeout multiplier.")
    agent_setup_timeout_multiplier: float | None = Field(default=None, description="Agent-setup timeout multiplier.")
    environment_build_timeout_multiplier: float | None = Field(
        default=None, description="Environment-build timeout multiplier."
    )
    import_path: str = Field(
        default="harbor_wrapper:WrappedAgent",
        description="Harbor agent import path resolved inside the candidate directory.",
    )


class HarborRunnerEvaluator(Evaluator):
    """Run Harbor through the SDK's ``HarborAgentTaskRunner`` and parse the job dir."""

    evaluator_type: EvaluatorType = "harbor_agent_task_runner"

    def __init__(
        self,
        options: HarborRunnerConfig | None = None,
        experiment_dir: Path | None = None,
    ) -> None:
        super().__init__(options or HarborRunnerConfig(), experiment_dir=experiment_dir)

    async def _run(
        self,
        agent: Path,
        dataset: Dataset,
        options: EvaluatorConfig,
    ) -> Sequence[TrialResult]:
        if not isinstance(options, HarborRunnerConfig):
            raise TypeError("Options must be a HarborRunnerConfig")

        inputs = await resolve_harbor_run_inputs(agent, dataset, options, self.experiment_dir)
        harbor_dataset = inputs.dataset
        sdk_tasks = _sdk_tasks_for(harbor_dataset)

        # The SDK's cache keys off the job name and counts successful trials; it
        # never looks at *what* was evaluated. The job name is only
        # "<candidate>-<dataset>", so a rerun in the same experiment directory
        # after editing the candidate, the tasks, or a result-affecting option
        # would silently re-adapt stale trials. Plain Harbor fails loudly here
        # (it compares its persisted JobConfig), so without this the SDK path
        # would be the weaker of the two. Fingerprint the real inputs instead.
        fingerprint = _cache_fingerprint(options, inputs.agent_path, harbor_dataset)
        stale_cache = _cache_is_stale(inputs.job_dir, fingerprint)

        runtime_config = _import_harbor_runtime().runtime_config(
            jobs_dir=inputs.jobs_dir,
            job_name=inputs.job_name,
            agent_import_path=options.import_path,
            agent_dir=inputs.agent_path,
            n_attempts=options.n_attempts,
            n_concurrent_trials=options.n_concurrent_trials,
            quiet=options.quiet,
            force_rerun=options.force_rerun or stale_cache,
            artifacts=list(options.artifacts),
            trace_dir=options.trace_dir,
            max_retries=options.max_retries,
            timeout_multiplier=options.timeout_multiplier,
            agent_timeout_multiplier=options.agent_timeout_multiplier,
            verifier_timeout_multiplier=options.verifier_timeout_multiplier,
            agent_setup_timeout_multiplier=options.agent_setup_timeout_multiplier,
            environment_build_timeout_multiplier=options.environment_build_timeout_multiplier,
        )

        # Two different name spaces, and mixing them up produces either an empty
        # run or an empty cache:
        #   * Harbor's local-dataset `task_names` filter matches the task
        #     *directory* name, which is the Experimentalist task id.
        #   * `result.json` records `[task].name` from task.toml, which is what
        #     the SDK's tasks are keyed by and what its cache counts.
        runner = _import_harbor_runtime().task_runner(
            config=runtime_config,
            dataset_path=inputs.dataset_path,
            task_names=[task.id for task in harbor_dataset.tasks],
        )
        # The returned SDK trials are discarded: they expose only a single
        # `harbor_reward.reward`, while the loop needs every verifier metric. The
        # job dir is the richer contract, so both evaluators read that instead.
        sdk_trials = await runner.run_tasks(list(sdk_tasks.values()))
        _write_cache_fingerprint(inputs.job_dir, fingerprint)
        logger.debug("SDK Harbor runner returned %d trial(s) for job %s", len(sdk_trials), inputs.job_name)

        return trials_from_job_dir(inputs.job_dir, harbor_dataset.tasks)


class _SdkRuntime(NamedTuple):
    """The SDK entry points this evaluator needs, resolved at run time."""

    runtime_config: type[HarborRuntimeConfig]
    task_runner: type[HarborAgentTaskRunner]
    discover_tasks: Callable[[Path], list[AgentEvalTask]]


def _import_harbor_runtime() -> _SdkRuntime:
    """Import the SDK's Harbor runtime, with an actionable error when it is absent.

    A missing name (older SDK) raises ``ImportError`` from the import statement
    just like a missing package does, so both failure modes carry the same hint.
    """
    try:
        from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (  # noqa: PLC0415
            HarborAgentTaskRunner,
            HarborRuntimeConfig,
            discover_harbor_tasks,
        )
    except ImportError as exc:
        raise ImportError(f"{_SDK_INSTALL_HINT} (import failed: {exc})") from exc
    return _SdkRuntime(HarborRuntimeConfig, HarborAgentTaskRunner, discover_harbor_tasks)


def _directory_digest(root: Path) -> str:
    """Content-hash a directory tree, ignoring build/VCS noise.

    Contents rather than mtimes: the loop materializes each candidate with
    ``copytree``, which rewrites mtimes on every run and would defeat the cache
    entirely. Agent and task directories are source-sized, so reading them is
    cheap next to the Docker work the cache exists to skip.
    """
    digest = hashlib.sha256()
    if not root.is_dir():
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        if any(part in _DIGEST_SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _cache_fingerprint(options: HarborRunnerConfig, agent_path: Path, dataset: HarborDataset) -> str:
    """Identify everything that can change a run's results.

    Covers the three ways a job dir goes stale under an unchanged job name: the
    candidate's code, the selected tasks' content, and any option that affects
    what Harbor produces.

    STOPGAP — superseded by AALGO-427 (close the HarborAgentTaskRunner cache gap).

    The real gap that ticket closes: results *persist*, but nothing skips a task
    that has already been run and scored. This is deliberately not that fix —
    it is only an invalidation guard. ``HarborAgentTaskRunner`` caches
    unconditionally today, keyed on nothing but the job name and a count of
    successful trials, so without this a rerun in the same experiment directory
    silently re-adapts stale results. It exists to make that inherited behaviour
    no worse than plain Harbor's — which validates its persisted ``JobConfig``
    and refuses a mismatched job dir outright.

    Two consequences worth knowing before extending it:

    * It is job-level and all-or-nothing, and it never skips scoring. AALGO-427
      resumes per ``(agent, split, task)`` and belongs in the SDK, not here —
      delete this when that lands rather than growing it.
    * It assumes a **single writer per job directory on a local filesystem**.
      Concurrent writers (multiple pods on a shared RWX volume) are not handled
      by this or by Harbor: neither takes a lock on the job dir, so both would
      see "not cached", both would run, and both would write trials into it.

    Args:
        options: Evaluator options for this run.
        agent_path: Resolved candidate directory.
        dataset: The (possibly subset) dataset being evaluated.

    Returns:
        str: Hex digest to compare against the one stored in the job directory.
    """
    payload = hashlib.sha256()
    payload.update(
        json.dumps(options.model_dump(exclude=set(_CACHE_IRRELEVANT_OPTIONS)), sort_keys=True, default=str).encode(
            "utf-8"
        )
    )
    payload.update(b"\0agent\0")
    payload.update(_directory_digest(agent_path).encode("utf-8"))
    for task in sorted(dataset.tasks, key=lambda task: task.id):
        payload.update(f"\0task\0{task.id}\0".encode("utf-8"))
        if task.uri:
            task_dir = local_path_from_uri(task.uri, context="Harbor task reference")
            payload.update(_directory_digest(task_dir).encode("utf-8"))
    return payload.hexdigest()


def _cache_is_stale(job_dir: Path, fingerprint: str) -> bool:
    """Return True when an existing job dir was produced by different inputs.

    A job dir with no stored fingerprint counts as stale: it predates this check
    (or came from the plain evaluator), and re-running is the safe reading.
    """
    if not job_dir.is_dir():
        return False
    key_path = job_dir / _CACHE_KEY_FILENAME
    try:
        stored = key_path.read_text(encoding="utf-8").strip()
    except OSError:
        stored = ""
    if stored == fingerprint:
        return False
    logger.info(
        "Harbor job dir %s was produced by different inputs (agent, tasks, or options); re-running instead of "
        "serving it from cache.",
        job_dir,
    )
    return True


def _write_cache_fingerprint(job_dir: Path, fingerprint: str) -> None:
    """Stamp the job dir so a later run can tell whether it still matches.

    Best-effort: a job dir that could not be stamped simply re-runs next time,
    which is the safe direction. Harbor and the trial adapter both iterate
    directories only, so this file is inert to them.
    """
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / _CACHE_KEY_FILENAME).write_text(fingerprint, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not stamp Harbor job dir %s with a cache key: %s", job_dir, exc)


def _sdk_tasks_for(dataset: HarborDataset) -> dict[str, AgentEvalTask]:
    """Map each selected dataset task onto the SDK task carrying its full Harbor name.

    The mapping is by task *directory*, never by name similarity: the SDK reads
    ``[task].name`` from the same ``task.toml`` Harbor will read, so matching on
    the directory guarantees the ids we hand the runner are exactly the
    ``task_name`` values Harbor writes into ``result.json``.

    Args:
        dataset: The (possibly subset) Harbor dataset being evaluated.

    Returns:
        dict[str, AgentEvalTask]: Selected tasks keyed by Experimentalist task id,
        in dataset order.

    Raises:
        ValueError: If the dataset has no resolvable source directory.
        HarborTaskNameError: If a selected task has no discovered counterpart, or
            if two selected tasks resolve to the same full Harbor name.
    """
    if dataset.source is None:
        raise ValueError("Harbor dataset source is required")
    dataset_path = local_path_from_uri(dataset.source.uri, context="Harbor dataset reference").resolve()
    discovered = _import_harbor_runtime().discover_tasks(dataset_path)
    by_dir: dict[Path, AgentEvalTask] = {}
    for sdk_task in discovered:
        task_dir = sdk_task.metadata.get("harbor_task_dir")
        if isinstance(task_dir, str) and task_dir:
            by_dir[Path(task_dir).resolve()] = sdk_task

    selected: dict[str, AgentEvalTask] = {}
    full_names: dict[str, str] = {}
    for task in dataset.tasks:
        if not task.uri:
            raise HarborTaskNameError(f"Harbor task {task.id!r} has no URI, so its Harbor name cannot be resolved")
        task_dir = local_path_from_uri(task.uri, context="Harbor task reference").resolve()
        sdk_task = by_dir.get(task_dir)
        if sdk_task is None:
            raise HarborTaskNameError(
                f"Harbor task {task.id!r} at {task_dir} was not discovered under dataset {dataset_path}; "
                "the dataset directory and the task directories must agree"
            )
        if sdk_task.id in full_names:
            raise HarborTaskNameError(
                f"Harbor tasks {full_names[sdk_task.id]!r} and {task.id!r} both declare [task].name = "
                f"{sdk_task.id!r}; task names must be unique within a dataset"
            )
        full_names[sdk_task.id] = task.id
        selected[task.id] = sdk_task
    return selected


def harbor_task_names(dataset: HarborDataset) -> dict[str, str]:
    """Return ``{experimentalist_task_id: full_harbor_name}`` for a Harbor dataset.

    The readable view of the two-namespace translation ``_run`` depends on. Pass a
    ``dataset.subset(...)`` to scope it to selected tasks.

    Args:
        dataset: Harbor dataset whose source directory holds the tasks.

    Returns:
        dict[str, str]: Short Experimentalist task id to full Harbor ``[task].name``.
    """
    return {task_id: sdk_task.id for task_id, sdk_task in _sdk_tasks_for(dataset).items()}
