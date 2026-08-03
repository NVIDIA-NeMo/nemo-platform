# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The plugin-facing seam: everything a strategy is allowed to reach.

A strategy receives one :class:`ExperimentContext` and nothing else. The context holds
the :class:`~nemo_experimentalist_plugin.experimentalist.experimentalist_backend.ExperimentalistBackend`
privately, so no component ever sees ``create_run``, ``publish_candidate``, or the
platform client; the runner that built the context is the only code that holds a
backend.

The two keyword arguments below are deliberately different words. ``evaluate(split=…)``
names a *dataset split* to run against; ``record_reward(channel=…)`` names a *reward
channel* to store under. Usually a run on the validation split lands in the
``validation`` channel, but trajectory scoring produces a second channel from the same
split, which is why one is not spelled with the other's name.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from nemo_experimentalist_plugin.entities import (
    Candidate,
    Dataset,
    DataValue,
    EvaluationResult,
    ExperimentRun,
    RewardRecord,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Evaluator
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
    ExperimentalistBackend,
)
from nemo_experimentalist_plugin.experimentalist.reporting import RunReporter, reward_scalar
from nemo_platform import AsyncNeMoPlatform

logger = logging.getLogger(__name__)

#: The split every run has, and what ``evaluate()`` measures unless told otherwise.
#: It is also the channel a selector ranks on by default.
PRIMARY_SPLIT = "validation"


class ExperimentContext:
    """One run's view of the platform, handed to exactly one strategy.

    Args:
        backend: Data-access backend. Held privately; never handed to a component.
        workspace: NeMo Platform workspace this run belongs to.
        run: The ``ExperimentRun`` entity the runner created (or re-opened on resume).
        root: Working directory for the run's artifacts.
        agent_dir: The agent under test, materialized by the runner. A strategy forks
            candidates from here; it must not write into it.
        agent_spec: Optional markdown description of the agent under test.
        datasets: Evaluator-domain datasets keyed by split. ``validation`` is always
            present; ``train`` and ``insight`` are present when the run has them.
        evaluator: Evaluation component the run was configured with.
        resuming: True when the runner re-opened an existing run, so the strategy
            should rebuild its state from :meth:`candidates` instead of starting over.
        reporter: Optional human narration sink. Best-effort and never load-bearing.
    """

    def __init__(
        self,
        *,
        backend: ExperimentalistBackend,
        workspace: str,
        run: ExperimentRun,
        root: Path,
        agent_dir: Path,
        agent_spec: Path | None = None,
        datasets: Mapping[str, Dataset],
        evaluator: Evaluator,
        resuming: bool = False,
        reporter: RunReporter | None = None,
    ) -> None:
        if PRIMARY_SPLIT not in datasets:
            raise ValueError(f"ExperimentContext requires a {PRIMARY_SPLIT!r} dataset; got {sorted(datasets)}")
        self._backend = backend
        self._run = run
        self._evaluator = evaluator
        self._reporter = reporter
        self.workspace = workspace
        self.root = root
        self.agent_dir = agent_dir
        self.agent_spec = agent_spec
        self.datasets: Mapping[str, Dataset] = dict(datasets)
        self.resuming = resuming

    # -- Inputs --------------------------------------------------------------

    @property
    def dataset(self) -> Dataset:
        """The run's primary dataset — what ``evaluate()`` measures by default."""
        return self.datasets[PRIMARY_SPLIT]

    @property
    def run_id(self) -> str:
        """Durable id of this run, and the key every Candidate is grouped under."""
        return self._run.id or ""

    @property
    def evaluation(self) -> Evaluator:
        """The evaluation component this run was configured with.

        Exposed so a composite strategy can hand it to a component it owns — the Coder
        runs smoke evals of its own. Once the registry lands this becomes
        ``ctx.component("evaluation", …)`` and this property goes away.
        """
        return self._evaluator

    @property
    def client(self) -> AsyncNeMoPlatform | None:
        """Platform client, for reading ``intake://`` traces. Transitional.

        This is the last piece of backend that still reaches a component: the trace
        readers resolve ``intake://`` trial traces themselves, so they need a client.
        A ``ctx`` verb that loads a trace by reference would close it; until that
        exists, a strategy whose components read traces needs this, and a strategy
        that does not should ignore it.
        """
        return self._backend.client

    # -- Candidates ----------------------------------------------------------

    async def candidates(self) -> list[Candidate]:
        """Every Candidate committed to this run, in store order.

        This is what makes resume possible for a strategy the host did not write: the
        population is persisted, so a strategy rebuilds it rather than checkpointing it.
        """
        return await self._backend.list_candidates(workspace=self.workspace, run_id=self.run_id)

    def candidate_dir(self, candidate: Candidate) -> Path:
        """Directory holding *candidate*'s code.

        Still derived from the label, because a Candidate is still a directory. The
        candidate contract replaces this with ``candidate.artifact``.
        """
        return self.root / "eval-and-optimize" / "agents" / candidate.label

    async def save_candidate(self, candidate: Candidate, *, updates: dict[str, Any] | None = None) -> Candidate:
        """Create or update *candidate* in the entity store.

        Fills in ``workspace`` and ``run_id`` from the run (which is authoritative)
        before persisting. On first save the backend assigns a store id; later saves
        update the existing record.
        """
        candidate.workspace = self.workspace
        candidate.run_id = self.run_id
        for key, value in (updates or {}).items():
            setattr(candidate, key, value)
        if candidate.id:
            return await self._backend.update_candidate(workspace=self.workspace, candidate=candidate)
        stored = await self._backend.create_candidate(workspace=self.workspace, candidate=candidate)
        candidate._id = stored._id  # type: ignore[attr-defined]
        return candidate

    async def archive_candidate(self, candidate: Candidate) -> None:
        """Persist *candidate*'s code to durable storage, if the run archives at all.

        Best-effort in both directions: a backend that cannot archive returns nothing,
        and a failure is logged rather than raised — archival must never fail a run.
        """
        if not self._backend.storage.archive_candidates:
            return
        try:
            await self._backend.archive_candidate(workspace=self.workspace, candidate=candidate)
        except Exception as exc:  # noqa: BLE001 - archival must never fail the run
            logger.warning("[PERSISTENCE] archive failed for candidate %s; continuing: %s", candidate.label, exc)

    # -- Measurement ---------------------------------------------------------

    async def record_reward(
        self,
        candidate: Candidate,
        *,
        channel: str,
        result: EvaluationResult | RewardRecord,
        metadata: dict[str, DataValue] | None = None,
    ) -> None:
        """Store one measurement of *candidate* on *channel*, and persist the candidate.

        An ``EvaluationResult`` is the outcome of running the candidate, so its traces
        are persisted before the record is stored; a ``RewardRecord`` is a measurement
        the strategy computed itself (trajectory scoring, a self-scoring strategy) and
        is stored as given. Either way the channel is an open key — adding one costs no
        entity change.
        """
        if isinstance(result, EvaluationResult):
            await self._backend.persist_evaluation(
                workspace=self.workspace,
                result=result,
                candidate=candidate,
                split=channel,
            )
            record = RewardRecord(
                metrics={k: float(v) for k, v in result.aggregate_metrics.items()},
                trials=list(result.trials),
                metadata=dict(metadata or {}),
            )
        else:
            record = result if metadata is None else result.model_copy(update={"metadata": dict(metadata)})
        candidate.set_reward(
            channel,
            metrics=record.metrics,
            summary=record.summary,
            trials=record.trials,
            metadata=record.metadata,
        )
        await self.save_candidate(candidate)

    async def evaluate(
        self,
        candidate: Candidate,
        *,
        split: str = PRIMARY_SPLIT,
        task_ids: Sequence[str] | None = None,
        minimum_attempts: int | None = None,
    ) -> EvaluationResult:
        """Run the configured evaluation component over *candidate*'s artifact.

        Optional by design: a strategy that scores itself skips this and calls
        :meth:`record_reward` directly. The association between the result and the
        candidate is owned here, not by the evaluation component.

        Args:
            candidate: Whose artifact to evaluate.
            split: Which of :attr:`datasets` to run against.
            task_ids: Restrict the run to these task ids.
            minimum_attempts: Raise the evaluator's attempt count to at least this.

        Raises:
            KeyError: if *split* is not one of the run's datasets.
        """
        dataset = self.datasets[split]
        if task_ids is not None:
            dataset = dataset.subset(list(task_ids))
        # Force a unique job name per candidate so concurrent candidates never collide on
        # one results directory when a fixed job_name is configured. job_name/n_attempts
        # are Harbor's vocabulary reaching a generic call site — an evaluator leak the
        # registered evaluation component closes.
        options = self._evaluator.options.model_dump()
        options["job_name"] = f"{candidate.label}-{dataset.id}"
        if minimum_attempts is not None:
            configured = options.get("n_attempts")
            if not isinstance(configured, int):
                raise ValueError("Evaluator options must define integer n_attempts to raise the attempt floor")
            options["n_attempts"] = max(configured, minimum_attempts)
        result = await self._evaluator.run(
            agent=self.candidate_dir(candidate),
            dataset=dataset,
            options=type(self._evaluator.options).model_validate(options),
        )
        if self._reporter is not None:
            self._reporter.candidate_evaluated(
                label=candidate.label,
                split=split,
                reward=reward_scalar(result.aggregate_metrics),
                artifacts=self.root / "eval-and-optimize" / "results" / result.id,
            )
        return result

    # -- Progress ------------------------------------------------------------

    async def report_progress(
        self,
        *,
        completed: int,
        total: int | None = None,
        unit: str = "step",
        note: str | None = None,
    ) -> None:
        """Report how far the strategy has got, as a counter rather than a fraction.

        A counter is always producible; a fraction usually is not — an opaque strategy
        cannot say how many trials it will run, and even a round-based one stops early
        on convergence. When *total* is known a consumer may render a bar; when it is
        not, ``note`` is where a strategy says what it is doing instead.
        """
        self._run.progress_completed = completed
        self._run.progress_total = total
        self._run.progress_unit = unit
        self._run.progress_note = note
        await self._backend.update_run(workspace=self.workspace, run=self._run)
        if self._reporter is not None:
            self._reporter.progress(phase=note or unit, completed=completed, total=total, unit=unit)

    def note(self, message: str) -> None:
        """Say what is happening, for a human watching the run.

        Narration only: it touches no entity and never raises, so a strategy may call it
        as freely as it likes. Use :meth:`report_progress` for anything a consumer
        should be able to read back off the run.
        """
        if self._reporter is not None:
            self._reporter.note(message)
