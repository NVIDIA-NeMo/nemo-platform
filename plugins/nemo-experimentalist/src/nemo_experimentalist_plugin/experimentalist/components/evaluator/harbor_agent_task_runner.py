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

        runtime_config = _import_harbor_runtime().runtime_config(
            jobs_dir=inputs.jobs_dir,
            job_name=inputs.job_name,
            agent_import_path=options.import_path,
            agent_dir=inputs.agent_path,
            n_attempts=options.n_attempts,
            n_concurrent_trials=options.n_concurrent_trials,
            quiet=options.quiet,
            force_rerun=options.force_rerun,
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

    ``CACHE_STAMP_VERSION`` is imported purely as a capability probe, and is public
    SDK API precisely so this check does not depend on a private name. The SDK owns
    cache staleness (AALGO-427); against an SDK predating that, this evaluator would
    silently fall back to caching keyed on nothing but the job name and a count of
    successful trials — returning stale results after a candidate edit. Failing
    loudly is the only safe reading, since the plugin declares no version floor.
    """
    try:
        from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (  # noqa: PLC0415
            CACHE_STAMP_VERSION,  # noqa: F401  — capability probe, see docstring
            HarborAgentTaskRunner,
            HarborRuntimeConfig,
            discover_harbor_tasks,
        )
    except ImportError as exc:
        raise ImportError(f"{_SDK_INSTALL_HINT} (import failed: {exc})") from exc
    return _SdkRuntime(HarborRuntimeConfig, HarborAgentTaskRunner, discover_harbor_tasks)


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
