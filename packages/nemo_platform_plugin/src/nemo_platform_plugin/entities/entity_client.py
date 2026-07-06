# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NemoClient-backed entity client.

``NemoEntityClient`` is the ergonomic, entity-model-aware client. It presents
the same operations as the legacy Stainless-backed ``EntityClient`` (create,
list, get, get_by_id, update, delete, ...), returns the same ``EntityBase``
models, and maps transport errors to the same ``Entity*Error`` hierarchy — but
talks to the Entity Store over the ``NemoClient`` typed HTTP client.

``list`` returns a ``NemoPaginatedResponse[EntityT]``, consistent with every
other NemoClient service; single-page callers use ``result.page().items``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, get_type_hints

from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.client import AsyncNemoClient
from nemo_platform_plugin.client.errors import ConflictError, NotFoundError, UnprocessableEntityError
from nemo_platform_plugin.client.response import AsyncNemoPaginatedResponse, PageResult
from nemo_platform_plugin.entities.client import AsyncEntitiesEndpointClient
from nemo_platform_plugin.entities.legacy import (
    DEFAULT_WORKSPACE,
    EntityConflictError,
    EntityNotFoundError,
    EntityT,
    EntityTypeLike,
    EntityValidationError,
    _convert_filter_obj_to_filter_str,
    _convert_sort_to_api_sort,
    _get_entity_type,
    parse_qualified_name,
)
from nemo_platform_plugin.entities.types import (
    DeleteResponse,
    EntityCreateInput,
    EntityResponse,
    EntityUpdate,
    ListEntitiesQueryParams,
    ParentQueryParams,
)
from nemo_platform_plugin.filter_ops import FilterOperation
from pydantic import TypeAdapter


def _service_principal_headers(service_name: str, *, internal: bool = False) -> dict[str, str]:
    """Headers that authenticate a request as a service principal.

    Mirrors ``client_provider._build_headers`` so both elevation paths set
    identical headers; the entity store authz (``get_accessible_workspaces``)
    keys off ``X-NMP-Principal-Id: service:*``.
    """
    headers = {"X-NMP-Principal-Id": f"service:{service_name}"}
    if internal:
        # Imported lazily: nmp.common sits above this package in the dep graph.
        from nmp.common.observability import MARK_INTERNAL_REQUEST_HEADERS

        headers.update(MARK_INTERNAL_REQUEST_HEADERS)
    return headers


class _MappedPaginatedResponse(AsyncNemoPaginatedResponse[EntityT]):
    """Wraps a paginated ``EntityResponse`` stream, yielding ``EntityT`` models.

    Preserves the ``NemoPaginatedResponse`` access pattern (``page()`` /
    ``pages()`` / ``items()``) while converting each wire entity into the
    caller's ``EntityBase`` subclass via the owning client. Delegates all
    transport concerns to the inner response.
    """

    def __init__(
        self,
        inner: AsyncNemoPaginatedResponse[EntityResponse],
        client: NemoEntityClient,
        entity_type: EntityTypeLike,
    ) -> None:
        self._inner = inner
        self._client = client
        self._entity_type = entity_type

    @property
    def http_response(self):  # noqa: ANN201 — matches base return type (httpx.Response)
        return self._inner.http_response

    def _convert(self, page: PageResult[EntityResponse]) -> PageResult[EntityT]:
        items = [self._client._convert_api_entity_to_model(e, self._entity_type) for e in page.items]
        return PageResult(
            items=items,
            page=page.page,
            page_size=page.page_size,
            total_pages=page.total_pages,
            total_results=page.total_results,
        )

    def page(self) -> PageResult[EntityT]:
        return self._convert(self._inner.page())

    async def items(self) -> AsyncIterator[EntityT]:
        async for page in self._inner.pages():
            for entity in page.items:
                yield self._client._convert_api_entity_to_model(entity, self._entity_type)

    async def pages(self) -> AsyncIterator[PageResult[EntityT]]:
        async for page in self._inner.pages():
            yield self._convert(page)


class NemoEntityClient:
    """Async entity client backed by the ``NemoClient`` typed HTTP transport.

    A single client handles all entity types — pass the entity class to each
    method. Primary lookup is by name (workspace-qualified names like
    ``"prod/my-model"`` are supported), with ID lookup for debugging.
    """

    def __init__(self, client: AsyncNemoClient) -> None:
        self._client = client
        self._endpoints = AsyncEntitiesEndpointClient.from_client(client)

    @classmethod
    def from_platform(cls, platform: Any) -> NemoEntityClient:
        """Build a client from a legacy ``AsyncNeMoPlatform`` SDK instance.

        Bridges onto the SDK's transport (base URL, workspace, headers, httpx
        client) so existing SDK-construction plumbing can be reused unchanged.
        """
        return cls(client_from_platform(platform, AsyncNemoClient))

    async def close(self) -> None:
        """Close the underlying HTTP transport."""
        await self._client._http.aclose()

    def _convert_api_entity_to_model(self, entity: EntityResponse, entity_type: EntityTypeLike) -> EntityT:
        """Convert a wire ``EntityResponse`` into an ``EntityBase`` model."""
        entity_dict = entity.model_dump()
        entity_dict.update(entity.data)
        type_adapter = TypeAdapter(entity_type)
        result = type_adapter.validate_python(entity_dict)
        result._id = entity.id
        if entity.parent:
            result._parent = entity.parent
        result._created_at = entity.created_at
        result._created_by = entity.created_by
        result._updated_at = entity.updated_at
        result._updated_by = entity.updated_by
        result._db_version = entity.db_version
        # Restore PrivateAttr fields from stored data, excluding base attrs (set above).
        # Use type(result) not entity_type, since entity_type may be an Annotated union.
        type_hints = get_type_hints(type(result))
        for field_name in type(result).__private_attributes__:
            if field_name not in type(result).__base_private_attrs__ and field_name in entity.data:
                raw_value = entity.data[field_name]
                attr_type = type_hints.get(field_name)
                if attr_type is not None:
                    setattr(result, field_name, TypeAdapter(attr_type).validate_python(raw_value))
                else:
                    setattr(result, field_name, raw_value)

        # Strip _auth_context unless the effective caller is a service principal.
        # With on-behalf-of delegation the client authenticates as service:platform
        # but the real caller is in X-NMP-Principal-On-Behalf-Of.
        if hasattr(result, "_auth_context"):
            headers = self._client._default_headers
            effective = headers.get("X-NMP-Principal-On-Behalf-Of") or headers.get("X-NMP-Principal-Id", "")
            if not effective.startswith("service:"):
                setattr(result, "_auth_context", None)

        return result

    def as_service(self, service_name: str, *, internal: bool = False) -> NemoEntityClient:
        """Return a copy authenticating as ``service:<service_name>``.

        Use for background tasks, startup code, or permission elevation. The
        returned client shares this client's transport with service-principal
        headers applied; the original is unchanged.
        """
        elevated = self._client.with_headers(_service_principal_headers(service_name, internal=internal))
        return NemoEntityClient(elevated)

    async def list(
        self,
        entity_type: EntityTypeLike,
        *,
        workspace: str = DEFAULT_WORKSPACE,
        filter_operation: FilterOperation | None = None,
        filter_str: str | None = None,
        sort: str | None = None,
        filter_obj: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> AsyncNemoPaginatedResponse[EntityT]:
        """List entities with filtering and pagination.

        ``filter_operation`` and ``filter_str`` are mutually exclusive (passing
        both raises ``ValueError``). ``filter_obj`` is an exact-match shorthand,
        consulted only when neither other filter is supplied.

        Returns a paginated response; use ``result.page()`` for a single page
        (with metadata) or ``result.items()`` to iterate across all pages.
        """
        if filter_operation is not None and filter_str is not None:
            raise ValueError(
                "NemoEntityClient.list: pass either filter_operation or filter_str, not both. "
                "Merge into a single filter_operation via ParsedFilter.and_with."
            )

        if filter_operation is not None:
            effective_filter_str = json.dumps(filter_operation.to_dict())
        else:
            effective_filter_str = filter_str

        if filter_obj and not effective_filter_str:
            filter_dict = _convert_filter_obj_to_filter_str(filter_obj)
            if filter_dict:
                effective_filter_str = json.dumps(filter_dict)

        query: ListEntitiesQueryParams = {"page": page, "page_size": page_size}
        if effective_filter_str:
            query["filter"] = effective_filter_str
        if sort:
            query["sort"] = _convert_sort_to_api_sort(sort)

        inner = await self._endpoints.list_entities(
            workspace=workspace, entity_type=_get_entity_type(entity_type), query_params=query
        )
        return _MappedPaginatedResponse(inner, self, entity_type)

    async def create(self, entity: EntityT) -> EntityT:
        """Create a new entity. Raises ``EntityConflictError`` if it exists."""
        entity_type = type(entity)
        # Only include optional fields when set, so exclude_unset omits them on the
        # wire (matching the legacy client's ``omit`` sentinel behavior).
        create_kwargs: dict[str, Any] = {"data": entity._get_data_fields()}
        if entity.name:
            create_kwargs["name"] = entity.name
        if entity._parent:
            create_kwargs["parent"] = entity._parent
        if entity.project:
            create_kwargs["project"] = entity.project
        body = EntityCreateInput(**create_kwargs)
        try:
            response = await self._endpoints.create_entity(
                workspace=entity.workspace, entity_type=_get_entity_type(entity_type), body=body
            )
            return self._convert_api_entity_to_model(response.data(), entity_type)
        except ConflictError as e:
            raise EntityConflictError(
                f"Entity with name '{entity.name}' already exists in workspace '{entity.workspace}'"
            ) from e
        except UnprocessableEntityError as e:
            raise EntityValidationError(e.detail or str(e)) from e

    async def get(
        self,
        entity_type: EntityTypeLike,
        name: str,
        *,
        workspace: str | None = None,
        parent: str | None = None,
    ) -> EntityT:
        """Get an entity by name (supports workspace-qualified ``prod/name``)."""
        ws, entity_name = parse_qualified_name(name, default_workspace=workspace)
        query: ParentQueryParams = {}
        if parent is not None:
            query["parent"] = parent
        try:
            response = await self._endpoints.get_entity_by_name(
                workspace=ws,
                entity_type=_get_entity_type(entity_type),
                name=entity_name,
                query_params=query or None,
            )
            return self._convert_api_entity_to_model(response.data(), entity_type)
        except NotFoundError as e:
            raise EntityNotFoundError(f"Entity '{entity_name}' not found in workspace '{ws}'") from e

    async def get_by_id(self, entity_type: EntityTypeLike, entity_id: str) -> EntityT:
        """Get an entity by UUID (debugging/internal use)."""
        try:
            response = await self._endpoints.get_entity_by_id(id=entity_id)
            return self._convert_api_entity_to_model(response.data(), entity_type)
        except NotFoundError as e:
            raise EntityNotFoundError(f"Entity with id '{entity_id}' not found") from e

    async def update(self, entity: EntityT, *, original_name: str | None = None) -> EntityT:
        """Update an entity by name, with optimistic locking via db_version.

        Pass ``original_name`` when renaming (``entity.name`` becomes the new
        name). Raises ``EntityConflictError`` on version mismatch.
        """
        entity_type = type(entity)
        path_name = original_name or entity.name
        # Only include optional fields when applicable, so exclude_unset omits them
        # (matching the legacy client's ``omit`` sentinel behavior).
        update_kwargs: dict[str, Any] = {
            "data": entity._get_data_fields(),
            "expected_db_version": entity.db_version,
        }
        if original_name:
            update_kwargs["new_name"] = entity.name
        if entity.project:
            update_kwargs["project"] = entity.project
        body = EntityUpdate(**update_kwargs)
        query: ParentQueryParams = {}
        if entity._parent is not None:
            query["parent"] = entity._parent
        try:
            response = await self._endpoints.update_entity_by_name(
                workspace=entity.workspace,
                entity_type=_get_entity_type(entity_type),
                name=path_name,
                body=body,
                query_params=query or None,
            )
            return self._convert_api_entity_to_model(response.data(), entity_type)
        except NotFoundError as e:
            raise EntityNotFoundError(f"Entity '{path_name}' not found in workspace '{entity.workspace}'") from e
        except ConflictError as e:
            raise EntityConflictError(e.detail or str(e)) from e
        except UnprocessableEntityError as e:
            raise EntityValidationError(e.detail or str(e)) from e

    async def delete(
        self,
        entity_type: EntityTypeLike,
        name: str,
        *,
        workspace: str | None = None,
        parent: str | None = None,
    ) -> DeleteResponse:
        """Delete an entity by name (supports workspace-qualified names)."""
        ws, entity_name = parse_qualified_name(name, default_workspace=workspace)
        query: ParentQueryParams = {}
        if parent is not None:
            query["parent"] = parent
        try:
            response = await self._endpoints.delete_entity_by_name(
                workspace=ws,
                entity_type=_get_entity_type(entity_type),
                name=entity_name,
                query_params=query or None,
            )
            return response.data()
        except NotFoundError as e:
            raise EntityNotFoundError(f"Entity '{entity_name}' not found in workspace '{ws}'") from e

    async def delete_by_id(self, entity_type: EntityTypeLike, entity_id: str) -> DeleteResponse:
        """Delete an entity by UUID (fetches it first to resolve name/workspace)."""
        try:
            entity = (await self._endpoints.get_entity_by_id(id=entity_id)).data()
            query: ParentQueryParams = {}
            if entity.parent is not None:
                query["parent"] = entity.parent
            response = await self._endpoints.delete_entity_by_name(
                workspace=entity.workspace,
                entity_type=entity.entity_type,
                name=entity.name,
                query_params=query or None,
            )
            return response.data()
        except NotFoundError as e:
            raise EntityNotFoundError(f"Entity with id '{entity_id}' not found") from e

    async def save(self, entity: EntityT) -> EntityT:
        """Create the entity, or update it if it already exists."""
        if entity.id:
            try:
                return await self.update(entity)
            except EntityNotFoundError:
                pass
        try:
            return await self.create(entity)
        except EntityConflictError:
            if entity.id:
                try:
                    return await self.update(entity)
                except EntityNotFoundError as e:
                    raise EntityNotFoundError(f"Entity with id '{entity.id}' not found") from e
            raise

    async def add(self, entity: EntityT) -> EntityT:
        """Create a new entity (always creates, never updates)."""
        return await self.create(entity)

    async def get_by_field(self, entity_type: EntityTypeLike, workspace: str, **field_filters: Any) -> EntityT:
        """Get the first entity matching exact-match field filters."""
        if not field_filters:
            raise ValueError("At least one field filter is required")

        result = await self.list(entity_type, workspace=workspace, filter_obj=field_filters, page_size=1)
        items = result.page().items
        if not items:
            filter_desc = ", ".join(f"{k}={v!r}" for k, v in field_filters.items())
            raise EntityNotFoundError(f"Entity not found matching: {filter_desc}")
        return items[0]
