# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Prompt Management API Endpoints v2.

Prompts are stored as a two-level hierarchy in the entity store:
  - `prompt`         — root entity holding metadata (description, tags, version_count)
  - `prompt_version` — child entity (parent = prompt.id) holding the actual template

Routes:
  POST   /v2/workspaces/{workspace}/prompts                              — Create prompt (+ version 1)
  GET    /v2/workspaces/{workspace}/prompts                              — List prompts
  GET    /v2/workspaces/{workspace}/prompts/{name}                       — Get prompt (current version inlined)
  PUT    /v2/workspaces/{workspace}/prompts/{name}                       — Update prompt metadata
  DELETE /v2/workspaces/{workspace}/prompts/{name}                       — Delete prompt + all versions

Version sub-routes are added via make_versioning_router (see bottom of file):
  POST   /v2/workspaces/{workspace}/prompts/{name}/versions
  GET    /v2/workspaces/{workspace}/prompts/{name}/versions
  GET    /v2/workspaces/{workspace}/prompts/{name}/versions/{version_number}
"""

import logging
import textwrap

from fastapi import APIRouter, HTTPException, Query, status
from nmp.common.api.common import Page, PaginationData
from nmp.core.entities.api.dependencies import EntityRepository
from nmp.core.entities.api.v2.prompts.schemas import (
    Prompt,
    PromptCreate,
    PromptModelParams,
    PromptUpdate,
    PromptVersion,
    PromptVersionCreate,
    extract_variables,
)
from nmp.core.entities.api.v2.schemas import DeleteResponse
from nmp.core.entities.api.v2.versioning import make_versioning_router
from nmp.core.entities.app.repository.exceptions import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    EntityVersionConflictError,
)
from nmp.core.entities.entities import Entity
from nmp.core.entities.utils.filter import FilterDep
from nmp.core.entities.utils.identifiers import generate_entity_name

router = APIRouter()
API_TAG = "Prompts"
logger = logging.getLogger(__name__)

PROMPT_ENTITY_TYPE = "prompt"
PROMPT_VERSION_ENTITY_TYPE = "prompt_version"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity_to_prompt_version(entity: Entity, prompt_entity: Entity) -> PromptVersion:
    data = entity.data
    raw_params = data.get("model_params")
    model_params = PromptModelParams(**raw_params) if raw_params else None
    return PromptVersion(
        id=entity.id,
        name=entity.name,
        prompt_id=prompt_entity.id,
        prompt_name=prompt_entity.name,
        workspace=entity.workspace,
        version_number=data.get("version_number", 1),
        template=data.get("template", ""),
        variables=data.get("variables", []),
        model_params=model_params,
        change_note=data.get("change_note"),
        created_at=entity.created_at,
        created_by=entity.created_by,
        updated_at=entity.updated_at,
    )


def _entity_to_prompt(entity: Entity, current_version_entity: Entity | None = None) -> Prompt:
    data = entity.data
    current_version: PromptVersion | None = None
    if current_version_entity is not None:
        current_version = _entity_to_prompt_version(current_version_entity, entity)
    return Prompt(
        id=entity.id,
        name=entity.name,
        workspace=entity.workspace,
        project=entity.project,
        description=data.get("description"),
        tags=data.get("tags", []),
        version_count=data.get("version_count", 0),
        current_version=current_version,
        created_at=entity.created_at,
        created_by=entity.created_by,
        updated_at=entity.updated_at,
        updated_by=entity.updated_by,
    )


async def _get_prompt_or_404(repository: EntityRepository, workspace: str, name: str) -> Entity:
    entity = await repository.get_entity_by_name(
        workspace=workspace,
        entity_type=PROMPT_ENTITY_TYPE,
        name=name,
    )
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{name}' not found in workspace '{workspace}'",
        )
    return entity


async def _get_current_version(repository: EntityRepository, prompt_entity: Entity) -> Entity | None:
    current_version_name = prompt_entity.data.get("current_version_name")
    if not current_version_name:
        return None
    return await repository.get_entity_by_name(
        workspace=prompt_entity.workspace,
        entity_type=PROMPT_VERSION_ENTITY_TYPE,
        name=current_version_name,
        parent=prompt_entity.id,
    )


def _build_prompt_version_data(version_in: PromptVersionCreate, version_number: int) -> dict:
    return {
        "version_number": version_number,
        "template": version_in.template,
        "variables": extract_variables(version_in.template),
        "model_params": version_in.model_params.model_dump() if version_in.model_params else None,
        "change_note": version_in.change_note,
    }


# ---------------------------------------------------------------------------
# Prompt endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/v2/workspaces/{workspace}/prompts",
    response_model=Prompt,
    tags=[API_TAG],
    status_code=201,
    summary="Create a prompt",
    description=textwrap.dedent("""
        Create a new prompt with its first version.

        The prompt entity stores metadata (description, tags, version_count).
        A `prompt_version` child entity is created atomically for the initial template.

        Example:
        ```
        POST /apis/entities/v2/workspaces/default/prompts
        {
            "name": "rag-system-prompt",
            "description": "System prompt for RAG pipeline",
            "tags": ["rag", "system"],
            "template": "Answer in {{language}} using: {{context}}",
            "change_note": "Initial version"
        }
        ```
    """),
)
async def create_prompt(
    workspace: str,
    prompt_in: PromptCreate,
    repository: EntityRepository,
) -> Prompt:
    name = prompt_in.name or generate_entity_name(PROMPT_ENTITY_TYPE)
    variables = extract_variables(prompt_in.template)
    version_name = f"{name}-v1"

    try:
        async with repository.transaction() as session:
            prompt_data = {
                "description": prompt_in.description,
                "tags": prompt_in.tags,
                "version_count": 1,
                "current_version_name": version_name,
            }
            prompt_entity = await repository.create_entity(
                workspace=workspace,
                entity_type=PROMPT_ENTITY_TYPE,
                name=name,
                data=prompt_data,
                project=prompt_in.project,
                session=session,
            )

            version_data = {
                "version_number": 1,
                "template": prompt_in.template,
                "variables": variables,
                "model_params": prompt_in.model_params.model_dump() if prompt_in.model_params else None,
                "change_note": prompt_in.change_note,
            }
            version_entity = await repository.create_entity(
                workspace=workspace,
                entity_type=PROMPT_VERSION_ENTITY_TYPE,
                name=version_name,
                data=version_data,
                parent=prompt_entity.id,
                session=session,
            )

        return _entity_to_prompt(prompt_entity, version_entity)
    except EntityAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Prompt '{name}' already exists in workspace '{workspace}'.",
        ) from e


@router.get(
    "/v2/workspaces/{workspace}/prompts",
    response_model=Page[Prompt],
    tags=[API_TAG],
    summary="List prompts",
    description=textwrap.dedent("""
        List prompts in a workspace with optional filtering and sorting.

        **Sort** — prefix field name with `-` for descending order:
        - `-created_at` (default), `created_at`, `-updated_at`, `updated_at`, `name`, `-name`

        **Filter** — supports three syntaxes:

        Text: `?filter=name:"rag"` or `?filter=name~"rag" AND project:"my-project"`

        JSON: `?filter={"name":{"$like":"rag%"},"project":"my-project"}`

        Bracket: `?filter[name][$like]=rag&filter[project]=my-project`

        Available filter operators: `$eq`, `$like`, `$lt`, `$lte`, `$gt`, `$gte`, `$in`, `$nin`, `$and`, `$or`, `$not`
    """),
)
async def list_prompts(
    workspace: str,
    repository: EntityRepository,
    filter: FilterDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    sort: str = Query(
        "-created_at", description="Sort field. Prefix with - for descending (e.g. -created_at, name, -name)."
    ),
) -> Page[Prompt]:
    entities, total = await repository.list_entities(
        workspace=workspace,
        entity_type=PROMPT_ENTITY_TYPE,
        page=page,
        page_size=page_size,
        sort=sort,
        filter_op=filter,
    )
    prompts = [_entity_to_prompt(e) for e in entities]
    return Page(
        data=prompts,
        pagination=PaginationData(
            page=page,
            page_size=page_size,
            total_results=total,
            total_pages=(total + page_size - 1) // page_size,
            current_page_size=len(prompts),
        ),
        sort=sort,
        filter=filter.to_dict() if filter else None,
    )


@router.get(
    "/v2/workspaces/{workspace}/prompts/{name}",
    response_model=Prompt,
    tags=[API_TAG],
    summary="Get prompt by name",
    description="Returns the prompt with the current version inlined.",
)
async def get_prompt(
    workspace: str,
    name: str,
    repository: EntityRepository,
) -> Prompt:
    prompt_entity = await _get_prompt_or_404(repository, workspace, name)
    current_version = await _get_current_version(repository, prompt_entity)
    return _entity_to_prompt(prompt_entity, current_version)


@router.put(
    "/v2/workspaces/{workspace}/prompts/{name}",
    response_model=Prompt,
    tags=[API_TAG],
    summary="Update prompt metadata",
    description="Update a prompt's description, tags, or project. Does not create a new version.",
)
async def update_prompt(
    workspace: str,
    name: str,
    prompt_update: PromptUpdate,
    repository: EntityRepository,
) -> Prompt:
    prompt_entity = await _get_prompt_or_404(repository, workspace, name)
    existing_data = dict(prompt_entity.data)

    if prompt_update.description is not None:
        existing_data["description"] = prompt_update.description
    if prompt_update.tags is not None:
        existing_data["tags"] = prompt_update.tags

    project_in_payload = "project" in prompt_update.model_fields_set
    new_project = prompt_update.project if project_in_payload else prompt_entity.project

    try:
        updated_entity = await repository.update_entity_by_name(
            workspace=workspace,
            entity_type=PROMPT_ENTITY_TYPE,
            name=name,
            data=existing_data,
            project=new_project,
            clear_project=project_in_payload and new_project is None,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except EntityVersionConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    current_version = await _get_current_version(repository, updated_entity)
    return _entity_to_prompt(updated_entity, current_version)


@router.delete(
    "/v2/workspaces/{workspace}/prompts/{name}",
    response_model=DeleteResponse,
    tags=[API_TAG],
    summary="Delete prompt",
    description="Delete a prompt and all its versions. Child versions are removed via CASCADE.",
)
async def delete_prompt(
    workspace: str,
    name: str,
    repository: EntityRepository,
) -> DeleteResponse:
    deleted_count = await repository.delete_entity_by_name(
        workspace=workspace,
        entity_type=PROMPT_ENTITY_TYPE,
        name=name,
    )
    if deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{name}' not found in workspace '{workspace}'",
        )
    return DeleteResponse(
        id=f"{workspace}/{PROMPT_ENTITY_TYPE}/{name}",
        deleted_count=deleted_count,
    )


# ---------------------------------------------------------------------------
# Version endpoints — delegated to the shared versioning router factory
# ---------------------------------------------------------------------------

router.include_router(
    make_versioning_router(
        parent_entity_type=PROMPT_ENTITY_TYPE,
        version_entity_type=PROMPT_VERSION_ENTITY_TYPE,
        resource_path="prompts",
        version_schema=PromptVersion,
        version_create_schema=PromptVersionCreate,
        build_version_data=_build_prompt_version_data,
        to_version_response=_entity_to_prompt_version,
        api_tag=API_TAG,
    )
)
