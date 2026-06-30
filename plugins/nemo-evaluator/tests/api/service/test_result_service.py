# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Service-level tests for ResultService (list/get/delete over the two result entity types).

The entity store is an in-memory fake keyed by ``(entity_type, workspace, name)`` so the two
collections (agent-eval vs row-eval) are proven not to collide.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from nemo_evaluator.api.schemas import AgentEvalResult, EvaluateResult
from nemo_evaluator.api.service.result_service import ResultService
from nemo_evaluator.entities import AgentEvalResultEntity, EvaluateResultEntity
from nemo_evaluator_sdk.values.results import AggregatedMetricResult
from nemo_platform_plugin.entities import EntityBase, EntityNotFoundError, ListResponse, PaginationInfo


class _FakeEntityClient:
    """In-memory store keyed by (entity_type, workspace, name)."""

    def __init__(self) -> None:
        self.entities: dict[tuple[str, str, str], EntityBase] = {}

    def seed(self, entity: EntityBase) -> EntityBase:
        now = datetime.now(timezone.utc)
        entity._id = f"{entity.__entity_type__}-{entity.name}"
        entity._created_at = now
        entity._updated_at = now
        self.entities[(entity.__entity_type__, entity.workspace, entity.name)] = entity
        return entity

    async def get(self, entity_cls, *, workspace, name):
        key = (entity_cls.__entity_type__, workspace, name)
        if key not in self.entities:
            raise EntityNotFoundError(f"{workspace}/{name} not found")
        return self.entities[key]

    async def delete(self, entity_cls, name, *, workspace):
        # Mirror the real EntityClient: raise EntityNotFoundError when absent.
        key = (entity_cls.__entity_type__, workspace, name)
        if key not in self.entities:
            raise EntityNotFoundError(f"{workspace}/{name} not found")
        del self.entities[key]

    async def list(self, entity_cls, *, workspace, filter_operation=None, sort=None, page=1, page_size=100):
        items = [
            e for (etype, ws, _), e in self.entities.items() if etype == entity_cls.__entity_type__ and ws == workspace
        ]
        return ListResponse(
            data=items,
            pagination=PaginationInfo(
                page=page,
                page_size=page_size,
                current_page_size=len(items),
                total_pages=1,
                total_results=len(items),
            ),
        )


def _agent_entity(name: str, workspace: str = "default") -> AgentEvalResultEntity:
    return AgentEvalResultEntity(
        name=name,
        workspace=workspace,
        job_id=name,
        target_kind="codex",
        target_name="gpt-5.5",
        target_url=None,
        scores=AggregatedMetricResult(scores=[]),
        bundle_ref=f"fileset://{workspace}/agent-eval-results#b",
    )


def _eval_entity(name: str, workspace: str = "default") -> EvaluateResultEntity:
    return EvaluateResultEntity(
        name=name,
        workspace=workspace,
        job_id=name,
        target_kind="model",
        target_name="m",
        target_url=None,
        scores=AggregatedMetricResult(scores=[]),
        bundle_ref=f"fileset://{workspace}/eval-results#b",
        dataset_ref=f"{workspace}/ds",
        metric_types=["exact_match"],
    )


@pytest.fixture
def fake() -> _FakeEntityClient:
    return _FakeEntityClient()


@pytest.fixture
def service(fake: _FakeEntityClient) -> ResultService:
    return ResultService(fake)


async def test_list_returns_only_that_collection(service: ResultService, fake: _FakeEntityClient) -> None:
    # Same name across both collections must not collide — they are distinct entity types.
    fake.seed(_agent_entity("job-1"))
    fake.seed(_eval_entity("job-1"))
    fake.seed(_eval_entity("job-2"))

    agent_page = await service.list_agent_eval_results(workspace="default")
    eval_page = await service.list_eval_results(workspace="default")

    assert {e.name for e in agent_page.data} == {"job-1"}
    assert {e.name for e in eval_page.data} == {"job-1", "job-2"}
    assert eval_page.pagination is not None
    assert eval_page.pagination.total_results == 2


async def test_get_returns_typed_dto(service: ResultService, fake: _FakeEntityClient) -> None:
    fake.seed(_eval_entity("job-9"))

    got = await service.get_eval_result("default", "job-9")

    # The service maps the stored entity to the API DTO (so id/created_at round-trip on the wire).
    assert isinstance(got, EvaluateResult)
    assert got.id == "evaluate_result-job-9"
    assert got.created_at is not None
    assert got.dataset_ref == "default/ds"
    assert got.metric_types == ["exact_match"]


async def test_list_maps_entities_to_dtos(service: ResultService, fake: _FakeEntityClient) -> None:
    fake.seed(_agent_entity("job-1"))

    page = await service.list_agent_eval_results(workspace="default")

    assert all(isinstance(item, AgentEvalResult) for item in page.data)
    assert page.data[0].job_id == "job-1"


async def test_get_returns_none_when_missing(service: ResultService) -> None:
    assert await service.get_agent_eval_result("default", "nope") is None
    assert await service.get_eval_result("default", "nope") is None


async def test_delete_removes_only_matching_type(service: ResultService, fake: _FakeEntityClient) -> None:
    fake.seed(_agent_entity("job-1"))
    fake.seed(_eval_entity("job-1"))

    assert await service.delete_agent_eval_result("default", "job-1") is True
    # The same-named row-eval result is a different type and must survive.
    assert await service.get_agent_eval_result("default", "job-1") is None
    assert await service.get_eval_result("default", "job-1") is not None


async def test_delete_returns_false_when_missing(service: ResultService) -> None:
    assert await service.delete_eval_result("default", "nope") is False
