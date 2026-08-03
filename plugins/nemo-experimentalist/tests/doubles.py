# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared doubles for the runner, the context, and anything a strategy touches.

Before the runner existed every test that wanted to drive the loop had to assemble a
backend, an evaluator and a bag of ``deps`` by hand. These three build the same things
once: an in-memory backend that records what it was asked to persist, an evaluator that
returns a fixed result, and a context wired from both.

``conftest.py`` re-exports these as fixtures; import the classes directly when a test
needs to build more than one.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from nemo_experimentalist_plugin.config import CandidateStorageConfig
from nemo_experimentalist_plugin.entities import (
    Candidate,
    Dataset,
    EvaluationResult,
    ExperimentRun,
    Proposal,
    ResourceRef,
    RewardRecord,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import Evaluator, EvaluatorConfig
from nemo_experimentalist_plugin.experimentalist.components.model_config import ModelTiers
from nemo_experimentalist_plugin.experimentalist.components.repository import AgentSource
from nemo_experimentalist_plugin.experimentalist.context import ExperimentContext
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import ExperimentalistBackend
from nemo_experimentalist_plugin.experimentalist.reporting import RunReporter
from nemo_experimentalist_plugin.experimentalist.result import ExperimentalistResult
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform


def fake_client() -> AsyncNeMoPlatform:
    """A stand-in platform client for paths that only check whether one is present."""
    return cast(AsyncNeMoPlatform, SimpleNamespace())


class RecordedEvaluation(dict):
    """One ``persist_evaluation`` call, as keyword arguments."""


class FakeBackend(ExperimentalistBackend):
    """In-memory backend that keeps everything it was asked to persist.

    Candidates are keyed by label the way the local backend keys them, so a test can
    assert on ``backend.candidates["agent-1"]`` without reading any files.
    """

    def __init__(
        self,
        *,
        client: AsyncNeMoPlatform | None = None,
        storage: CandidateStorageConfig | None = None,
        insight: Insight | None = None,
    ) -> None:
        super().__init__(client, None, storage)
        self.candidates: dict[str, Candidate] = {}
        self.runs: list[ExperimentRun] = []
        self.evaluations: list[RecordedEvaluation] = []
        self.results: list[ExperimentalistResult] = []
        self.archived: list[str] = []
        self.published: list[str] = []
        self.agent_code_calls: list[tuple[str | Path, Path]] = []
        self._insight = insight

    async def get_insight(self, *, workspace: str, insight_id: str) -> Insight:
        if self._insight is None:
            raise ValueError(f"FakeBackend has no insight to return for {insight_id!r}")
        return self._insight

    async def create_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        run._id = run.id or f"run-{len(self.runs) + 1}"  # type: ignore[attr-defined]
        self.runs.append(run)
        return run

    async def update_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        return run

    async def create_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        candidate._id = candidate.id or candidate.label  # type: ignore[attr-defined]
        self.candidates[candidate.label] = candidate
        return candidate

    async def update_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        self.candidates[candidate.label] = candidate
        return candidate

    async def get_candidate(self, *, workspace: str, candidate_id: str) -> Candidate:
        return self.candidates[candidate_id]

    async def list_candidates(self, *, workspace: str, run_id: str) -> list[Candidate]:
        return [c for c in self.candidates.values() if c.run_id == run_id]

    async def persist_result(self, *, workspace: str, result: ExperimentalistResult) -> None:
        self.results.append(result)

    async def persist_evaluation(
        self, *, workspace: str, result: EvaluationResult, candidate: Candidate, split: str
    ) -> None:
        self.evaluations.append(
            RecordedEvaluation(workspace=workspace, result=result, candidate=candidate, split=split)
        )

    async def get_experiment_id(self, *, workspace: str, candidate: Candidate, split: str) -> str:
        return f"exp-{candidate.label}-{split}"

    async def get_agent_code(
        self, *, workspace: str, agent: str | Path, dest: Path, clone_depth: int | None = None
    ) -> AgentSource | None:
        self.agent_code_calls.append((agent, dest))
        dest.mkdir(parents=True, exist_ok=True)
        return None

    async def archive_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        self.archived.append(candidate.label)
        return f"archived://{candidate.label}"

    async def publish_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        self.published.append(candidate.label)
        return f"https://example.invalid/pr/{candidate.label}"

    async def get_agent_spec(self, *, workspace: str, spec: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f"# spec from {spec}\n")
        return dest


class FakeEvaluator(Evaluator):
    """Returns a fixed reward and records the options each run was given."""

    evaluator_type = "harbor"

    def __init__(self, *, reward: float = 0.5, options: EvaluatorConfig | None = None) -> None:
        super().__init__(options or EvaluatorConfig(), None)
        self.reward = reward
        self.runs: list[dict[str, object]] = []

    async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
        self.runs.append({"agent": agent, "dataset": dataset, "options": options})
        return [
            TrialResult(id=f"{agent.name}-{task.id}", task_id=task.id, status="completed")
            for task in dataset.list_tasks()
        ]

    async def aggregate_results(self, results: Sequence[TrialResult]) -> dict[str, float | int]:
        return {"reward": self.reward}


def make_candidate(
    *,
    label: str = "agent-0",
    run_id: str = "run-1",
    generation: int = 0,
    description: str | None = None,
    ancestor: str | None = None,
    optimization_type: str | None = None,
    artifact: str | None = None,
    candidate_id: str | None = None,
    rewards: Mapping[str, RewardRecord] | None = None,
    killed_generation: int | None = None,
    workspace: str = "default",
) -> Candidate:
    """A Candidate with a synthetic artifact, for tests that only care about metadata.

    Every real Candidate is created by ``ctx.commit_candidate()`` from a finished
    artifact; a test that is not exercising that path still needs one, so this supplies
    a plausible directory URI and derives the projections the same way the context does.
    """
    text = description if description is not None else ("baseline" if ancestor is None else f"change in {label}")
    proposal = (
        None
        if ancestor is None
        else Proposal(
            ancestor=ancestor,
            description=text,
            kind="code-change",
            payload={"optimization_type": optimization_type} if optimization_type else {},
        )
    )
    candidate = Candidate(
        name=label,
        label=label,
        run_id=run_id,
        generation=generation,
        ancestor=ancestor,
        generated_from=proposal,
        description=text,
        artifact=ResourceRef(uri=artifact or f"file:///tmp/{run_id}/eval-and-optimize/agents/{label}"),
        rewards=dict(rewards or {}),
        killed_generation=killed_generation,
        workspace=workspace,
    )
    # Distinct from the label by default: identity and the display handle are different
    # strings in a real run, and a double that conflates them hides that class of bug.
    candidate._id = candidate_id or f"id-{label}"  # type: ignore[attr-defined]
    return candidate


def make_context(
    *,
    root: Path,
    backend: ExperimentalistBackend | None = None,
    evaluator: Evaluator | None = None,
    datasets: Mapping[str, Dataset] | None = None,
    run: ExperimentRun | None = None,
    workspace: str = "default",
    resuming: bool = False,
    reporter: RunReporter | None = None,
    models: ModelTiers | None = None,
) -> ExperimentContext:
    """Build a context over *root*, defaulting every collaborator to a double."""
    run = run or ExperimentRun(workspace=workspace, agent="agent-under-test")
    if not run.id:
        run._id = "run-1"  # type: ignore[attr-defined]
    agent_dir = root / "eval-and-optimize" / "source-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    return ExperimentContext(
        backend=backend or FakeBackend(),
        workspace=workspace,
        run=run,
        root=root,
        agent_dir=agent_dir,
        datasets=datasets or {"train": Dataset(id="train"), "validation": Dataset(id="validation")},
        evaluator=evaluator or FakeEvaluator(),
        models=models or ModelTiers(),
        resuming=resuming,
        reporter=reporter,
    )
