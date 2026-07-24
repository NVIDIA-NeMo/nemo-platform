# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.experimentalist.experiment_mirror import ExperimentMirror, group_metadata
from nemo_platform import ConflictError, NotFoundError, omit  # VERIFY-2

pytestmark = pytest.mark.asyncio

_CONFLICT = ConflictError(
    "conflict", response=httpx.Response(409, request=httpx.Request("POST", "http://x/y")), body=None
)
_NOTFOUND = NotFoundError(
    "not found", response=httpx.Response(404, request=httpx.Request("GET", "http://x/y")), body=None
)


def _client(groups: object, experiments: object) -> object:
    return SimpleNamespace(experiment_groups=groups, evaluations=experiments)


class _StatefulGroups:
    """Models experiment_groups as a full-replace PUT store: create/update set the
    stored body to exactly the fields passed, treating ``omit`` (or an absent kwarg)
    as "field became None". This is what catches accidental field-wiping on update."""

    _TRACKED = ("insight_id", "summary", "metadata")

    def __init__(self) -> None:
        self.name: str | None = None
        self.body: dict[str, object | None] = {}

    def _apply(self, **kwargs: object) -> None:
        for field in self._TRACKED:
            value = kwargs.get(field, omit)
            self.body[field] = None if value is omit else value

    async def create(self, *, name: str, **kwargs: object) -> object:
        self.name = name
        self._apply(**kwargs)
        return SimpleNamespace(id="grp-1", name=name, **self.body)

    async def retrieve(self, name: str, **kwargs: object) -> object:
        return SimpleNamespace(id="grp-1", name=self.name, **self.body)

    async def update(self, path_name: str, **kwargs: object) -> object:
        self._apply(**kwargs)
        return SimpleNamespace(id="grp-1", name=self.name, **self.body)


def _run(**kw) -> ExperimentRun:
    base = dict(
        workspace="default",
        agent="a",
        insight="ins-1",
        config_snapshot={},
        status="running",
        rounds_completed=0,
        winner_agent=None,
    )
    base.update(kw)
    run = ExperimentRun(**base)
    run._id = "run-1"  # store id (private attr, as the entity client sets it)
    return run


def _cand(**kw) -> Candidate:
    base = dict(run_id="run-1", label="agent-0", round=0, optimization="baseline")
    base.update(kw)
    return Candidate(**base)


async def test_ensure_group_creates_with_insight_and_metadata():
    groups = AsyncMock()
    groups.create.return_value = SimpleNamespace(id="grp-1", name="opt-run-1")
    mirror = ExperimentMirror(_client(groups, AsyncMock()), workspace="default")
    await mirror.ensure_group(_run())
    kwargs = groups.create.await_args.kwargs
    assert kwargs["name"] == "opt-run-1" and kwargs["insight_id"] == "ins-1"
    assert kwargs["metadata"]["agent"] == "a"


async def test_ensure_group_conflict_retrieves():
    groups = AsyncMock()
    groups.create.side_effect = _CONFLICT
    groups.retrieve.return_value = SimpleNamespace(id="grp-1", name="opt-run-1")
    mirror = ExperimentMirror(_client(groups, AsyncMock()), workspace="default")
    await mirror.ensure_group(_run())
    groups.retrieve.assert_awaited_once()


async def test_project_candidate_upserts_experiment_per_evaluated_split():
    experiments = AsyncMock()
    experiments.create.return_value = SimpleNamespace(id="exp-train")
    mirror = ExperimentMirror(_client(AsyncMock(), experiments), workspace="default")
    cand = _cand(round=0, train_reward={"reward": 1.0}, train_reward_details=[])
    await mirror.project_candidate(cand)
    kwargs = experiments.create.await_args.kwargs
    assert kwargs["name"] == "opt-run-1-agent-0-train"
    assert kwargs["status"] == "baseline"
    # metadata is identity-only — reward/trials are NOT copied (§4.3)
    assert kwargs["metadata"] == {"round": "0", "candidate_id": "agent-0", "split": "train"}
    assert "aggregate_metrics" not in kwargs["metadata"] and "trials" not in kwargs["metadata"]
    # validation not evaluated → not created
    assert experiments.create.await_count == 1


async def test_project_candidate_skips_when_no_reward():
    experiments = AsyncMock()
    mirror = ExperimentMirror(_client(AsyncMock(), experiments), workspace="default")
    await mirror.project_candidate(_cand())  # no reward set
    experiments.create.assert_not_awaited()


async def test_project_candidate_conflict_updates_experiment():
    groups = AsyncMock()
    groups.retrieve.return_value = SimpleNamespace(id="grp-1", name="opt-run-1")
    experiments = AsyncMock()
    experiments.create.side_effect = _CONFLICT
    experiments.update.return_value = SimpleNamespace(id="exp-train")
    mirror = ExperimentMirror(_client(groups, experiments), workspace="default")
    cand = _cand(round=0, train_reward={"reward": 1.0}, train_reward_details=[])
    await mirror.project_candidate(cand)
    experiments.update.assert_awaited_once()
    # update is a full-replace: dataset_version must be re-supplied (symmetric with create)
    kwargs = experiments.update.await_args.kwargs
    assert kwargs["dataset_version"] == "v1"
    assert kwargs["metadata"] == {"round": "0", "candidate_id": "agent-0", "split": "train"}


async def test_parent_experiment_id_cache_hit():
    groups = AsyncMock()
    groups.retrieve.return_value = SimpleNamespace(id="grp-1", name="opt-run-1")
    experiments = AsyncMock()
    experiments.create.side_effect = [
        SimpleNamespace(id="exp-ancestor-train"),  # ancestor train experiment
        SimpleNamespace(id="exp-child-train"),  # child train experiment
    ]
    mirror = ExperimentMirror(_client(groups, experiments), workspace="default")
    ancestor = _cand(label="agent-0", round=0, train_reward={"reward": 1.0}, train_reward_details=[])
    await mirror.project_candidate(ancestor)
    child = _cand(label="agent-1", ancestor="agent-0", round=1, train_reward={"reward": 1.0}, train_reward_details=[])
    await mirror.project_candidate(child)
    child_kwargs = experiments.create.await_args.kwargs  # last call == child
    assert child_kwargs["parent_evaluation_id"] == "exp-ancestor-train"
    experiments.retrieve.assert_not_awaited()  # resolved from cache, no lookup


async def test_parent_experiment_id_fallback_retrieve():
    groups = AsyncMock()
    groups.retrieve.return_value = SimpleNamespace(id="grp-1", name="opt-run-1")
    experiments = AsyncMock()
    experiments.retrieve.return_value = SimpleNamespace(id="exp-ancestor-train")
    experiments.create.return_value = SimpleNamespace(id="exp-child-train")
    mirror = ExperimentMirror(_client(groups, experiments), workspace="default")
    child = _cand(label="agent-1", ancestor="agent-0", round=1, train_reward={"reward": 1.0}, train_reward_details=[])
    await mirror.project_candidate(child)
    experiments.retrieve.assert_awaited()
    kwargs = experiments.create.await_args.kwargs
    assert kwargs["parent_evaluation_id"] == "exp-ancestor-train"


async def test_parent_experiment_id_not_found_omits():
    groups = AsyncMock()
    groups.retrieve.return_value = SimpleNamespace(id="grp-1", name="opt-run-1")
    experiments = AsyncMock()
    experiments.retrieve.side_effect = _NOTFOUND
    experiments.create.return_value = SimpleNamespace(id="exp-child-train")
    mirror = ExperimentMirror(_client(groups, experiments), workspace="default")
    child = _cand(label="agent-1", ancestor="agent-0", round=1, train_reward={"reward": 1.0}, train_reward_details=[])
    await mirror.project_candidate(child)
    kwargs = experiments.create.await_args.kwargs
    assert kwargs["parent_evaluation_id"] is omit


async def test_finalize_round0_winner_preserves_existing_source_link():
    # A round-0 winner with no PR must keep the source_link written during the run (e.g. a
    # real {repo}@{ref}), not have it clobbered with a pseudo link by the full-replace update.
    groups = AsyncMock()
    groups.retrieve.return_value = SimpleNamespace(id="grp-1", name="opt-run-1", insight_id=None, metadata=None)
    experiments = AsyncMock()
    experiments.retrieve.return_value = SimpleNamespace(id="exp-w", source_link="https://git/repo.git@main")
    experiments.create.return_value = SimpleNamespace(id="exp-w")
    mirror = ExperimentMirror(_client(groups, experiments), workspace="default")
    winner = _cand(label="agent-0", round=0, train_reward={"reward": 1.0}, train_reward_details=[])
    await mirror.finalize(run_id="run-1", summary="done", winner=winner, pr_url=None)
    kwargs = experiments.create.await_args.kwargs
    assert kwargs["source_link"] == "https://git/repo.git@main"  # preserved, not pseudo
    assert kwargs["status"] == "winner"


async def test_group_update_and_finalize_do_not_wipe_insight_or_metadata():
    # experiment_groups.update is a full-replace PUT; ensure_group → update_group →
    # finalize must all preserve insight_id + metadata rather than reset them to None.
    groups = _StatefulGroups()
    mirror = ExperimentMirror(_client(groups, AsyncMock()), workspace="default")
    run = _run(insight="ins-1")
    await mirror.ensure_group(run)
    await mirror.update_group(run)
    await mirror.finalize(run_id="run-1", summary="done", winner=None)
    assert groups.body["insight_id"] == "ins-1"
    assert groups.body["metadata"] == group_metadata(run)
    assert groups.body["metadata"] is not None
    assert groups.body["summary"] == "done"
