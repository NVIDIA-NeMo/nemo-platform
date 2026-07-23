# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights plugin HTTP service.

Mounts Insight CRUD routes under ``/apis/insights/v2/workspaces/{workspace}/``.
Discovered by the platform via the ``nemo.services`` entry-point.
"""

import logging
from datetime import datetime, timezone
from typing import ClassVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_insights_plugin._perms import (
    AnalysisConfigPerms,
    AnalysisRunStatusPerms,
    EvalAuthorRunPerms,
    InsightPerms,
)
from nemo_insights_plugin.authz import scope
from nemo_insights_plugin.entities import (
    AnalysisConfig,
    AnalysisRunStatus,
    EvalAuthorRun,
    EvalAuthorRunStage,
    EvalAuthorRunStatus,
    Insight,
    InsightStatus,
)
from nemo_insights_plugin.jobs.analyze import AnalyzeJob
from nemo_insights_plugin.schema import (
    AnalysisConfigPage,
    AnalysisRunStatusPage,
    CreateEvalAuthorRunRequest,
    CreateInsightRequest,
    EvalAuthorRunPage,
    InsightListItem,
    InsightPage,
    UpdateAnalysisConfigRequest,
    UpdateAnalysisRunStatusRequest,
    UpdateEvalAuthorRunRequest,
    UpdateInsightRequest,
)
from nemo_platform_plugin.authz import CallerKind, path_rule
from nemo_platform_plugin.entities import (
    EntityValidationError as NemoEntityValidationError,
)
from nemo_platform_plugin.entity_client import (
    NemoEntitiesClient,
    NemoEntityConflictError,
    NemoEntityNotFoundError,
    get_entity_client,
)
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.schema import PaginationData
from nemo_platform_plugin.service import NemoService, RouterSpec
from nmp.intake.entities.experiments import ExperimentGroup
from nmp.intake.spans.api.dependencies import SpansServiceDep

logger = logging.getLogger(__name__)

_TERMINAL_EVAL_AUTHOR_STATUSES = frozenset(
    {
        EvalAuthorRunStatus.SUCCEEDED,
        EvalAuthorRunStatus.FAILED,
        EvalAuthorRunStatus.CANCELLED,
    }
)
_EVAL_AUTHOR_STATUS_TRANSITIONS = {
    EvalAuthorRunStatus.CREATED: frozenset(
        {
            EvalAuthorRunStatus.RUNNING,
            EvalAuthorRunStatus.SUCCEEDED,
            EvalAuthorRunStatus.FAILED,
            EvalAuthorRunStatus.CANCELLED,
        }
    ),
    EvalAuthorRunStatus.RUNNING: _TERMINAL_EVAL_AUTHOR_STATUSES,
    EvalAuthorRunStatus.SUCCEEDED: frozenset(),
    EvalAuthorRunStatus.FAILED: frozenset(),
    EvalAuthorRunStatus.CANCELLED: frozenset(),
}
_EVAL_AUTHOR_STAGE_INDEX = {stage: index for index, stage in enumerate(EvalAuthorRunStage)}


def _to_list_item(insight: Insight) -> InsightListItem:
    item = InsightListItem.model_validate(insight.model_dump(exclude_computed_fields=True))
    if insight.__pydantic_private__ is not None:
        item.__pydantic_private__ = insight.__pydantic_private__.copy()
    return item


class InsightsService(NemoService):
    """NeMo Insights plugin service.

    Exposes CRUD routes for :class:`~nemo_insights_plugin.entities.Insight` —
    the analyst agent's primary output. Routes are mounted under
    ``/apis/insights/v2/workspaces/{workspace}/``.
    """

    name: ClassVar[str] = "insights"
    dependencies: ClassVar[list[str]] = ["entities", "jobs", "intake"]

    def get_routers(self) -> list[RouterSpec]:
        return [
            RouterSpec(
                _build_insights_router(),
                tag="Insights Insights",
                description="CRUD for analyst-authored Insight entities.",
                prefix="/v2/workspaces/{workspace}",
            ),
            RouterSpec(
                _build_analysis_configs_router(),
                tag="Insights Analysis Configs",
                description="Per-agent opt-in state for periodic insights analysis.",
                prefix="/v2/workspaces/{workspace}",
            ),
            RouterSpec(
                _build_eval_author_runs_router(),
                tag="Insights Eval Author Runs",
                description="Lifecycle and artifact indexes for externally executed Eval Author runs.",
                prefix="/v2/workspaces/{workspace}",
            ),
            RouterSpec(
                _build_analysis_run_statuses_router(),
                tag="Insights Analysis Run Statuses",
                description="Machine-written state for periodic insights analysis.",
                prefix="/v2/workspaces/{workspace}",
            ),
            RouterSpec(
                add_job_routes(AnalyzeJob, authz=scope),
                tag="Insights Analysis Jobs",
                description="Submit and track one-shot insights analyst jobs.",
                prefix="/v2/workspaces/{workspace}",
            ),
        ]


def _build_insights_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/insights",
        response_model=Insight,
        status_code=201,
        tags=["Insights Insights"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[InsightPerms.CREATE])
    async def create_insight(
        workspace: str,
        body: CreateInsightRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> Insight:
        """Create a new Insight. The store auto-generates the slug name."""
        insight = Insight(
            workspace=workspace,
            title=body.title,
            agent=body.agent,
            description=body.description,
            status=body.status,
            trace_refs=list(body.trace_refs),
        )
        try:
            saved = await entity_client.create(insight)
        except NemoEntityValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to create insight")
            raise HTTPException(status_code=500, detail="Failed to create insight.") from exc
        return saved

    @router.get(
        "/insights",
        response_model=InsightPage,
        tags=["Insights Insights"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[InsightPerms.LIST])
    async def list_insights(
        workspace: str,
        spans_service: SpansServiceDep,
        page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
        page_size: int = Query(default=20, ge=1, le=100, description="Items per page."),
        sort: str = Query(
            default="-created_at",
            description="Sort field. Prefix with '-' for descending (e.g. '-created_at').",
        ),
        agent: str | None = Query(default=None, description="Filter by agent name."),
        status: InsightStatus | None = Query(default=None, description="Filter by lifecycle status."),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> InsightPage:
        """List Insights with pagination, sort, and basic filters."""
        filter_obj: dict[str, object] = {}
        if agent is not None:
            filter_obj["agent"] = agent
        if status is not None:
            filter_obj["status"] = status.value

        try:
            result = await entity_client.list(
                Insight,
                workspace=workspace,
                page=page,
                page_size=page_size,
                sort=sort,
                filter_obj=filter_obj or None,
            )
        except Exception as exc:
            logger.exception("Failed to list insights")
            raise HTTPException(status_code=500, detail="Failed to list insights.") from exc

        items = [_to_list_item(insight) for insight in result.data]
        if items:
            insight_ids = [item.id for item in items]
            try:
                counts = await entity_client.count_by(
                    ExperimentGroup,
                    "insight_id",
                    workspace=workspace,
                    filter_obj={
                        "insight_id": {"$in": insight_ids},
                        "is_deleted": False,
                    },
                )
            except Exception:
                logger.exception("Failed to count experiment groups for insights")
            else:
                for item in items:
                    item.experiment_group_count = counts.get(item.id, 0)

            try:
                last_seen_at = await spans_service.latest_trace_started_at_by_group(
                    workspace=workspace,
                    trace_refs_by_group={item.id: item.trace_refs for item in items},
                )
            except Exception:
                logger.exception("Failed to find latest traces for insights")
            else:
                for item in items:
                    item.last_seen_at = last_seen_at.get(item.id)

        pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
        return InsightPage(
            data=items,
            pagination=pagination,
            sort=sort,
            filter=filter_obj or None,
        )

    @router.get(
        "/insights/{insight_id}",
        response_model=Insight,
        tags=["Insights Insights"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[InsightPerms.READ])
    async def get_insight(
        workspace: str,
        insight_id: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> Insight:
        """Get a single Insight by its store-assigned id."""
        try:
            insight = await entity_client.get_by_id(Insight, entity_id=insight_id)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{insight_id}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to get insight")
            raise HTTPException(status_code=500, detail="Failed to get insight.") from exc
        return insight

    @router.patch(
        "/insights/{insight_id}",
        response_model=Insight,
        tags=["Insights Insights"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[InsightPerms.UPDATE])
    async def update_insight(
        workspace: str,
        insight_id: str,
        body: UpdateInsightRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> Insight:
        """Partially update an Insight by id. Omitted fields are unchanged."""
        try:
            insight = await entity_client.get_by_id(Insight, entity_id=insight_id)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{insight_id}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to fetch insight for update")
            raise HTTPException(status_code=500, detail="Failed to fetch insight.") from exc

        if body.title is not None:
            insight.title = body.title
        if body.agent is not None:
            insight.agent = body.agent
        if body.description is not None:
            insight.description = body.description
        if body.status is not None:
            insight.status = body.status
        if body.trace_refs is not None:
            insight.trace_refs = list(body.trace_refs)

        try:
            saved = await entity_client.update(insight)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{insight_id}' not found in workspace '{workspace}'.",
            ) from exc
        except NemoEntityValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to update insight")
            raise HTTPException(status_code=500, detail="Failed to update insight.") from exc
        return saved

    @router.delete(
        "/insights/{insight_id}",
        status_code=204,
        tags=["Insights Insights"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[InsightPerms.DELETE])
    async def delete_insight(
        workspace: str,
        insight_id: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> None:
        """Delete an Insight by its store-assigned id. Returns 204 on success."""
        try:
            await entity_client.delete_by_id(Insight, entity_id=insight_id)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{insight_id}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to delete insight")
            raise HTTPException(status_code=500, detail="Failed to delete insight.") from exc

    return router


async def _get_workspace_insight(
    entity_client: NemoEntitiesClient,
    *,
    workspace: str,
    insight_id: str,
) -> Insight:
    try:
        insight = await entity_client.get_by_id(Insight, entity_id=insight_id)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Insight '{insight_id}' does not exist in workspace '{workspace}'.",
        ) from exc
    if insight.workspace != workspace:
        raise HTTPException(
            status_code=422,
            detail=f"Insight '{insight_id}' does not exist in workspace '{workspace}'.",
        )
    return insight


async def _get_workspace_eval_author_run(
    entity_client: NemoEntitiesClient,
    *,
    workspace: str,
    run_id: str,
) -> EvalAuthorRun:
    try:
        run = await entity_client.get_by_id(EvalAuthorRun, entity_id=run_id)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Eval Author run '{run_id}' not found in workspace '{workspace}'.",
        ) from exc
    if run.workspace != workspace:
        raise HTTPException(
            status_code=404,
            detail=f"Eval Author run '{run_id}' not found in workspace '{workspace}'.",
        )
    return run


def _validate_eval_author_update(
    run: EvalAuthorRun,
    body: UpdateEvalAuthorRunRequest,
) -> None:
    if body.status is not None and body.status != run.status:
        allowed = _EVAL_AUTHOR_STATUS_TRANSITIONS[run.status]
        if body.status not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"Illegal Eval Author run status transition: {run.status.value} -> {body.status.value}.",
            )
    if body.stage is not None and body.stage != run.stage:
        if run.status in _TERMINAL_EVAL_AUTHOR_STATUSES:
            raise HTTPException(status_code=409, detail="A terminal Eval Author run cannot change stage.")
        if _EVAL_AUTHOR_STAGE_INDEX[body.stage] < _EVAL_AUTHOR_STAGE_INDEX[run.stage]:
            raise HTTPException(
                status_code=409,
                detail=f"Eval Author run stage cannot regress: {run.stage.value} -> {body.stage.value}.",
            )
    next_status = body.status or run.status
    next_stage = body.stage or run.stage
    if next_status == EvalAuthorRunStatus.SUCCEEDED and next_stage != EvalAuthorRunStage.COMPLETED:
        raise HTTPException(
            status_code=422,
            detail="A succeeded Eval Author run must be in the completed stage.",
        )


def _build_eval_author_runs_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/eval-author-runs",
        response_model=EvalAuthorRun,
        status_code=201,
        tags=["Insights Eval Author Runs"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[EvalAuthorRunPerms.CREATE])
    async def create_eval_author_run(
        workspace: str,
        body: CreateEvalAuthorRunRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> EvalAuthorRun:
        await _get_workspace_insight(entity_client, workspace=workspace, insight_id=body.insight_id)
        if body.status == EvalAuthorRunStatus.SUCCEEDED and body.stage != EvalAuthorRunStage.COMPLETED:
            raise HTTPException(
                status_code=422,
                detail="A succeeded Eval Author run must be in the completed stage.",
            )
        now = datetime.now(timezone.utc)
        run = EvalAuthorRun(
            name=body.name or f"eval-author-run-{uuid4().hex[:12]}",
            workspace=workspace,
            insight_id=body.insight_id,
            status=body.status,
            stage=body.stage,
            evaluator_type=body.evaluator_type,
            config=body.config,
            inputs=body.inputs,
            models=body.models,
            provenance=body.provenance,
            outputs=body.outputs,
            capture=body.capture,
            validation=body.validation,
            summary=body.summary,
            error=body.error,
            started_at=now if body.status != EvalAuthorRunStatus.CREATED else None,
            completed_at=now if body.status in _TERMINAL_EVAL_AUTHOR_STATUSES else None,
        )
        try:
            return await entity_client.create(run)
        except NemoEntityValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to create Eval Author run")
            raise HTTPException(status_code=500, detail="Failed to create Eval Author run.") from exc

    @router.get(
        "/eval-author-runs",
        response_model=EvalAuthorRunPage,
        tags=["Insights Eval Author Runs"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[EvalAuthorRunPerms.LIST])
    async def list_eval_author_runs(
        workspace: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        sort: str = Query(default="-created_at"),
        insight_id: str | None = Query(default=None),
        status: EvalAuthorRunStatus | None = Query(default=None),
        created_at: datetime | None = Query(default=None, description="Return runs created at or after this time."),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> EvalAuthorRunPage:
        filter_obj: dict[str, object] = {}
        if insight_id is not None:
            filter_obj["insight_id"] = insight_id
        if status is not None:
            filter_obj["status"] = status.value
        if created_at is not None:
            filter_obj["created_at"] = {"$gte": created_at}
        try:
            result = await entity_client.list(
                EvalAuthorRun,
                workspace=workspace,
                page=page,
                page_size=page_size,
                sort=sort,
                filter_obj=filter_obj or None,
            )
        except Exception as exc:
            logger.exception("Failed to list Eval Author runs")
            raise HTTPException(status_code=500, detail="Failed to list Eval Author runs.") from exc
        pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
        return EvalAuthorRunPage(
            data=result.data,
            pagination=pagination,
            sort=sort,
            filter=filter_obj or None,
        )

    @router.get(
        "/eval-author-runs/{run_id}",
        response_model=EvalAuthorRun,
        tags=["Insights Eval Author Runs"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[EvalAuthorRunPerms.READ])
    async def get_eval_author_run(
        workspace: str,
        run_id: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> EvalAuthorRun:
        return await _get_workspace_eval_author_run(entity_client, workspace=workspace, run_id=run_id)

    @router.patch(
        "/eval-author-runs/{run_id}",
        response_model=EvalAuthorRun,
        tags=["Insights Eval Author Runs"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[EvalAuthorRunPerms.UPDATE])
    async def update_eval_author_run(
        workspace: str,
        run_id: str,
        body: UpdateEvalAuthorRunRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> EvalAuthorRun:
        run = await _get_workspace_eval_author_run(entity_client, workspace=workspace, run_id=run_id)
        _validate_eval_author_update(run, body)
        now = datetime.now(timezone.utc)
        if body.status is not None:
            if body.status == EvalAuthorRunStatus.RUNNING and run.started_at is None:
                run.started_at = now
            if body.status in _TERMINAL_EVAL_AUTHOR_STATUSES and run.completed_at is None:
                run.completed_at = now
            run.status = body.status
        if body.stage is not None:
            run.stage = body.stage
        if body.outputs is not None:
            run.outputs = body.outputs
        if body.capture is not None:
            run.capture = body.capture
        if body.validation is not None:
            run.validation = body.validation
        if body.summary is not None:
            run.summary = body.summary
        if "error" in body.model_fields_set:
            run.error = body.error
        try:
            return await entity_client.update(run)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Eval Author run '{run_id}' not found in workspace '{workspace}'.",
            ) from exc
        except NemoEntityValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to update Eval Author run")
            raise HTTPException(status_code=500, detail="Failed to update Eval Author run.") from exc

    return router


def _config_not_found(agent: str, workspace: str) -> str:
    """Standard 404 detail for a missing analysis config."""
    return f"Analysis config for agent '{agent}' not found in workspace '{workspace}'."


def _run_status_not_found(agent: str, workspace: str) -> str:
    """Standard 404 detail for a missing analysis run status."""
    return f"Analysis run status for agent '{agent}' not found in workspace '{workspace}'."


async def _get_or_create_analysis_config(
    entity_client: NemoEntitiesClient,
    *,
    workspace: str,
    agent: str,
    enabled_if_created: bool,
) -> tuple[AnalysisConfig, bool]:
    """Fetch an analysis config, creating a default one if it is absent.

    Returns the config and whether it was freshly created. Raises
    :class:`HTTPException` (500) on unexpected fetch failures.
    """
    try:
        config = await entity_client.get(AnalysisConfig, name=agent, workspace=workspace)
        return config, False
    except NemoEntityNotFoundError:
        pass
    except Exception as exc:
        logger.exception("Failed to fetch analysis config")
        raise HTTPException(status_code=500, detail="Failed to fetch analysis config.") from exc

    config = AnalysisConfig(name=agent, workspace=workspace, agent=agent, enabled=enabled_if_created)
    try:
        return await entity_client.create(config), True
    except NemoEntityConflictError:
        existing = await entity_client.get(AnalysisConfig, name=agent, workspace=workspace)
        return existing, False


async def _get_or_create_analysis_run_status(
    entity_client: NemoEntitiesClient,
    *,
    workspace: str,
    agent: str,
) -> AnalysisRunStatus:
    """Fetch an analysis run status, creating a default one if it is absent."""
    try:
        return await entity_client.get(AnalysisRunStatus, name=agent, workspace=workspace)
    except NemoEntityNotFoundError:
        pass
    except Exception as exc:
        logger.exception("Failed to fetch analysis run status")
        raise HTTPException(status_code=500, detail="Failed to fetch analysis run status.") from exc

    status = AnalysisRunStatus(name=agent, workspace=workspace, agent=agent)
    try:
        return await entity_client.create(status)
    except NemoEntityConflictError:
        return await entity_client.get(AnalysisRunStatus, name=agent, workspace=workspace)


def _build_analysis_configs_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/analysis-configs/{agent}/enable",
        response_model=AnalysisConfig,
        tags=["Insights Analysis Configs"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisConfigPerms.ENABLE])
    async def enable_analysis_config(
        workspace: str,
        agent: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisConfig:
        """Enable periodic insights analysis for one agent."""
        config, created = await _get_or_create_analysis_config(
            entity_client, workspace=workspace, agent=agent, enabled_if_created=True
        )
        if created:
            return config

        config.enabled = True
        try:
            return await entity_client.update(config)
        except Exception as exc:
            logger.exception("Failed to enable analysis")
            raise HTTPException(status_code=500, detail="Failed to enable analysis config.") from exc

    @router.post(
        "/analysis-configs/{agent}/disable",
        response_model=AnalysisConfig,
        tags=["Insights Analysis Configs"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisConfigPerms.DISABLE])
    async def disable_analysis_config(
        workspace: str,
        agent: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisConfig:
        """Disable periodic insights analysis for one agent."""
        config, created = await _get_or_create_analysis_config(
            entity_client, workspace=workspace, agent=agent, enabled_if_created=False
        )
        if created:
            return config

        config.enabled = False
        try:
            return await entity_client.update(config)
        except Exception as exc:
            logger.exception("Failed to disable analysis")
            raise HTTPException(status_code=500, detail="Failed to disable analysis config.") from exc

    @router.get(
        "/analysis-configs",
        response_model=AnalysisConfigPage,
        tags=["Insights Analysis Configs"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisConfigPerms.LIST])
    async def list_analysis_configs(
        workspace: str,
        page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
        page_size: int = Query(default=20, ge=1, le=100, description="Items per page."),
        sort: str = Query(default="-created_at", description="Sort field."),
        enabled: bool | None = Query(default=None, description="Filter by enabled state."),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisConfigPage:
        """List periodic analysis opt-in records."""
        filter_obj: dict[str, object] = {}
        if enabled is not None:
            filter_obj["enabled"] = enabled

        try:
            result = await entity_client.list(
                AnalysisConfig,
                workspace=workspace,
                page=page,
                page_size=page_size,
                sort=sort,
                filter_obj=filter_obj or None,
            )
        except Exception as exc:
            logger.exception("Failed to list analysis configs")
            raise HTTPException(status_code=500, detail="Failed to list analysis configs.") from exc

        pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
        return AnalysisConfigPage(
            data=result.data,
            pagination=pagination,
            sort=sort,
            filter=filter_obj or None,
        )

    @router.get(
        "/analysis-configs/{agent}",
        response_model=AnalysisConfig,
        tags=["Insights Analysis Configs"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisConfigPerms.READ])
    async def get_analysis_config(
        workspace: str,
        agent: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisConfig:
        """Get periodic analysis opt-in state for one agent."""
        try:
            return await entity_client.get(AnalysisConfig, name=agent, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=_config_not_found(agent, workspace)) from exc
        except Exception as exc:
            logger.exception("Failed to get analysis config")
            raise HTTPException(status_code=500, detail="Failed to get analysis config.") from exc

    @router.patch(
        "/analysis-configs/{agent}",
        response_model=AnalysisConfig,
        tags=["Insights Analysis Configs"],
    )
    @scope.write
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisConfigPerms.UPDATE])
    async def update_analysis_config(
        workspace: str,
        agent: str,
        body: UpdateAnalysisConfigRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisConfig:
        """Partially update periodic analysis state for one agent."""
        try:
            config = await entity_client.get(AnalysisConfig, name=agent, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=_config_not_found(agent, workspace)) from exc
        except Exception as exc:
            logger.exception("Failed to fetch analysis config")
            raise HTTPException(status_code=500, detail="Failed to fetch analysis config.") from exc

        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(config, field, value)

        try:
            return await entity_client.update(config)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=_config_not_found(agent, workspace)) from exc
        except Exception as exc:
            logger.exception("Failed to update analysis config")
            raise HTTPException(status_code=500, detail="Failed to update analysis config.") from exc

    return router


def _build_analysis_run_statuses_router() -> APIRouter:
    router = APIRouter()

    @router.get(
        "/analysis-run-statuses",
        response_model=AnalysisRunStatusPage,
        tags=["Insights Analysis Run Statuses"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisRunStatusPerms.LIST])
    async def list_analysis_run_statuses(
        workspace: str,
        page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
        page_size: int = Query(default=20, ge=1, le=100, description="Items per page."),
        sort: str = Query(default="-updated_at", description="Sort field."),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisRunStatusPage:
        """List machine-written periodic analysis run status records."""
        try:
            result = await entity_client.list(
                AnalysisRunStatus,
                workspace=workspace,
                page=page,
                page_size=page_size,
                sort=sort,
            )
        except Exception as exc:
            logger.exception("Failed to list analysis run statuses")
            raise HTTPException(status_code=500, detail="Failed to list analysis run statuses.") from exc

        pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
        return AnalysisRunStatusPage(
            data=result.data,
            pagination=pagination,
            sort=sort,
            filter=None,
        )

    @router.get(
        "/analysis-run-statuses/{agent}",
        response_model=AnalysisRunStatus,
        tags=["Insights Analysis Run Statuses"],
    )
    @scope.read
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisRunStatusPerms.READ])
    async def get_analysis_run_status(
        workspace: str,
        agent: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisRunStatus:
        """Get machine-written periodic analysis run status for one agent."""
        try:
            return await entity_client.get(AnalysisRunStatus, name=agent, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=_run_status_not_found(agent, workspace)) from exc
        except Exception as exc:
            logger.exception("Failed to get analysis run status")
            raise HTTPException(status_code=500, detail="Failed to get analysis run status.") from exc

    @router.patch(
        "/analysis-run-statuses/{agent}",
        response_model=AnalysisRunStatus,
        tags=["Insights Analysis Run Statuses"],
    )
    @scope.write
    @path_rule(
        callers=[CallerKind.PRINCIPAL, CallerKind.SERVICE_PRINCIPAL],
        permissions=[AnalysisRunStatusPerms.UPDATE],
    )
    async def update_analysis_run_status(
        workspace: str,
        agent: str,
        body: UpdateAnalysisRunStatusRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AnalysisRunStatus:
        """Create or partially update periodic analysis run status for one agent."""
        status = await _get_or_create_analysis_run_status(entity_client, workspace=workspace, agent=agent)
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(status, field, value)

        try:
            return await entity_client.update(status)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=_run_status_not_found(agent, workspace)) from exc
        except Exception as exc:
            logger.exception("Failed to update analysis run status")
            raise HTTPException(status_code=500, detail="Failed to update analysis run status.") from exc

    return router
