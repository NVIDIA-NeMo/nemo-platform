# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Legacy ``client.jobs`` SDK resource backed by the source-owned Jobs client."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Generic, TypeVar

import httpx
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform._base_client import PageInfo
from nemo_platform._types import Body, Headers, NotGiven, Omit, Query, Timeout, not_given, omit
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.response import AsyncNemoBinaryResponse, NemoBinaryResponse
from nemo_platform_plugin.client.types import PreparedRequest
from nemo_platform_plugin.jobs import endpoints
from nemo_platform_plugin.jobs.client import AsyncJobsClient, JobsClient
from nemo_platform_plugin.jobs.endpoints import ExecutionProfile
from nemo_platform_plugin.jobs.schemas import (
    FileStorageType,
    PlatformJobLog,
    PlatformJobResultCreateRequest,
    PlatformJobResultResponse,
    PlatformJobStatus,
    PlatformJobStatusResponse,
)
from nemo_platform_plugin.jobs.spec import PlatformJobSpec
from nemo_platform_plugin.jobs.types import (
    CreatePlatformJobRequest,
    JobLogsQueryParams,
    JobStatusDetailsUpdate,
    ListJobResultsQueryParams,
    ListJobsQueryParams,
    ListStepsQueryParams,
    PlatformJobListResultResponse,
    PlatformJobListSortField,
    PlatformJobListTaskResponse,
    PlatformJobResponse,
    PlatformJobSortField,
    PlatformJobStatusUpdateRequest,
    PlatformJobStepResponse,
    PlatformJobStepWithContext,
    PlatformJobTaskResponse,
    PlatformJobTaskUpdate,
)
from nemo_platform_plugin.schema import PaginationData
from nemo_platform_plugin.sdk import NemoPluginSDKResources

ItemT = TypeVar("ItemT")
ResponseT = TypeVar("ResponseT")


@dataclass
class JobsOffsetPage(Generic[ItemT]):
    """Offset-paginated Jobs page compatible with generated SDK page helpers."""

    data: list[ItemT]
    pagination: PaginationData | None
    sort: str | None = None
    filter: dict[str, object] | None = None
    _get_page: Callable[[int], JobsOffsetPage[ItemT]] | None = field(default=None, repr=False, compare=False)

    def __iter__(self) -> Iterator[ItemT]:
        page = self
        while True:
            yield from page.data
            if not page.has_next_page():
                return
            page = page.get_next_page()

    def has_next_page(self) -> bool:
        return bool(self.data) and self.next_page_info() is not None

    def next_page_info(self) -> PageInfo | None:
        current_page = self.pagination.page if self.pagination is not None else 1
        total_pages = self.pagination.total_pages if self.pagination is not None else None
        if total_pages is not None and current_page >= total_pages:
            return None
        return PageInfo(params={"page": current_page + 1})

    def get_next_page(self) -> JobsOffsetPage[ItemT]:
        if not self.has_next_page() or self._get_page is None:
            raise RuntimeError(
                "No next page expected; please check `.has_next_page()` before calling `.get_next_page()`."
            )
        current_page = self.pagination.page if self.pagination is not None else 1
        return self._get_page(current_page + 1)


@dataclass
class JobsCursorPage(Generic[ItemT]):
    """Cursor-paginated Jobs logs page compatible with generated SDK page helpers."""

    data: list[ItemT]
    total: int
    next_page: str | None = None
    prev_page: str | None = None
    _get_page: Callable[[str], JobsCursorPage[ItemT]] | None = field(default=None, repr=False, compare=False)

    def __iter__(self) -> Iterator[ItemT]:
        page = self
        while True:
            yield from page.data
            if not page.has_next_page():
                return
            page = page.get_next_page()

    def has_next_page(self) -> bool:
        return bool(self.data) and self.next_page_info() is not None

    def next_page_info(self) -> PageInfo | None:
        if not self.next_page:
            return None
        return PageInfo(params={"page_cursor": self.next_page})

    def get_next_page(self) -> JobsCursorPage[ItemT]:
        if not self.next_page or self._get_page is None:
            raise RuntimeError(
                "No next page expected; please check `.has_next_page()` before calling `.get_next_page()`."
            )
        return self._get_page(self.next_page)


@dataclass
class AsyncJobsOffsetPage(Generic[ItemT]):
    """Async offset-paginated Jobs page compatible with generated SDK page helpers."""

    data: list[ItemT]
    pagination: PaginationData | None
    sort: str | None = None
    filter: dict[str, object] | None = None
    _get_page: Callable[[int], Awaitable[AsyncJobsOffsetPage[ItemT]]] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    async def __aiter__(self) -> AsyncIterator[ItemT]:
        page = self
        while True:
            for item in page.data:
                yield item
            if not page.has_next_page():
                return
            page = await page.get_next_page()

    def has_next_page(self) -> bool:
        return bool(self.data) and self.next_page_info() is not None

    def next_page_info(self) -> PageInfo | None:
        current_page = self.pagination.page if self.pagination is not None else 1
        total_pages = self.pagination.total_pages if self.pagination is not None else None
        if total_pages is not None and current_page >= total_pages:
            return None
        return PageInfo(params={"page": current_page + 1})

    async def get_next_page(self) -> AsyncJobsOffsetPage[ItemT]:
        if not self.has_next_page() or self._get_page is None:
            raise RuntimeError(
                "No next page expected; please check `.has_next_page()` before calling `.get_next_page()`."
            )
        current_page = self.pagination.page if self.pagination is not None else 1
        return await self._get_page(current_page + 1)


@dataclass
class AsyncJobsCursorPage(Generic[ItemT]):
    """Async cursor-paginated Jobs logs page compatible with generated SDK page helpers."""

    data: list[ItemT]
    total: int
    next_page: str | None = None
    prev_page: str | None = None
    _get_page: Callable[[str], Awaitable[AsyncJobsCursorPage[ItemT]]] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    async def __aiter__(self) -> AsyncIterator[ItemT]:
        page = self
        while True:
            for item in page.data:
                yield item
            if not page.has_next_page():
                return
            page = await page.get_next_page()

    def has_next_page(self) -> bool:
        return bool(self.data) and self.next_page_info() is not None

    def next_page_info(self) -> PageInfo | None:
        if not self.next_page:
            return None
        return PageInfo(params={"page_cursor": self.next_page})

    async def get_next_page(self) -> AsyncJobsCursorPage[ItemT]:
        if not self.next_page or self._get_page is None:
            raise RuntimeError(
                "No next page expected; please check `.has_next_page()` before calling `.get_next_page()`."
            )
        return await self._get_page(self.next_page)


class AsyncJobsOffsetPageRequest(Generic[ItemT]):
    """Awaitable and async-iterable wrapper matching generated async list calls."""

    def __init__(self, get_page: Callable[[], Awaitable[AsyncJobsOffsetPage[ItemT]]]) -> None:
        self._get_page = get_page

    def __await__(self) -> Generator[object, None, AsyncJobsOffsetPage[ItemT]]:
        return self._get_page().__await__()

    async def __aiter__(self) -> AsyncIterator[ItemT]:
        page = await self
        async for item in page:
            yield item


class AsyncJobsCursorPageRequest(Generic[ItemT]):
    """Awaitable and async-iterable wrapper matching generated async log calls."""

    def __init__(self, get_page: Callable[[], Awaitable[AsyncJobsCursorPage[ItemT]]]) -> None:
        self._get_page = get_page

    def __await__(self) -> Generator[object, None, AsyncJobsCursorPage[ItemT]]:
        return self._get_page().__await__()

    async def __aiter__(self) -> AsyncIterator[ItemT]:
        page = await self
        async for item in page:
            yield item


def _is_omitted(value: object) -> bool:
    return isinstance(value, Omit)


def _required(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"Expected a non-empty value for `{field_name}` but received {value!r}")


def _normalized_headers(headers: Headers | None) -> dict[str, str] | None:
    if headers is None:
        return None
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if isinstance(value, Omit):
            continue
        normalized[str(key)] = str(value)
    return normalized or None


def _query_value(value: object) -> str | int | bool | None:
    if value is None or isinstance(value, str) or isinstance(value, int) or isinstance(value, bool):
        return value
    try:
        return json.dumps(value)
    except TypeError:
        return str(value)


def _normalized_query(extra_query: Query | None) -> dict[str, str | int | bool | None] | None:
    if extra_query is None:
        return None
    normalized: dict[str, str | int | bool | None] = {}
    for key, value in extra_query.items():
        if isinstance(value, Omit):
            continue
        normalized[str(key)] = _query_value(value)
    return normalized or None


def _apply_request_options(
    request: PreparedRequest[ResponseT],
    *,
    extra_headers: Headers | None,
    extra_query: Query | None,
) -> PreparedRequest[ResponseT]:
    query = _normalized_query(extra_query)
    if query is not None:
        request = replace(request, query_params={**(request.query_params or {}), **query})
    headers = _normalized_headers(extra_headers)
    if headers is not None:
        request = request.with_headers(headers)
    return request


def _extra_body_mapping(extra_body: Body | None) -> dict[str, object] | None:
    if extra_body is None:
        return None
    if not isinstance(extra_body, Mapping):
        raise TypeError("extra_body must be a mapping when used with the Jobs compatibility resource")
    return {str(key): value for key, value in extra_body.items()}


def _add_body_value(payload: dict[str, object], key: str, value: object) -> None:
    if _is_omitted(value):
        return
    if isinstance(value, Mapping):
        payload[key] = dict(value)
        return
    payload[key] = value


def _merge_body(payload: dict[str, object], extra_body: Body | None) -> dict[str, object]:
    extra = _extra_body_mapping(extra_body)
    if extra is None:
        return payload
    merged = dict(payload)
    for key, value in extra.items():
        merged[str(key)] = value
    return merged


def _sort_value(sort: Enum | str | Omit) -> str | None:
    if isinstance(sort, Omit):
        return None
    if isinstance(sort, Enum):
        return str(sort.value)
    return sort


def _filter_value(filter: Mapping[str, object] | str | Omit) -> str | None:
    if isinstance(filter, Omit):
        return None
    if isinstance(filter, str):
        return filter
    return json.dumps(filter)


def _page_filter(filter: Mapping[str, object] | str | Omit) -> dict[str, object] | None:
    if isinstance(filter, Mapping):
        return {str(key): value for key, value in filter.items()}
    return None


def _list_jobs_query_params(
    *,
    filter: Mapping[str, object] | str | Omit,
    page: int | Omit,
    page_size: int | Omit,
    sort: PlatformJobListSortField | str | Omit,
) -> ListJobsQueryParams:
    query_params: ListJobsQueryParams = {}
    if encoded_filter := _filter_value(filter):
        query_params["filter"] = encoded_filter
    if isinstance(page, int):
        query_params["page"] = page
    if isinstance(page_size, int):
        query_params["page_size"] = page_size
    if sort_query := _sort_value(sort):
        query_params["sort"] = sort_query
    return query_params


def _list_steps_query_params(
    *,
    filter: Mapping[str, object] | str | Omit,
    page: int | Omit,
    page_size: int | Omit,
    sort: PlatformJobSortField | str | Omit,
) -> ListStepsQueryParams:
    query_params: ListStepsQueryParams = {}
    if encoded_filter := _filter_value(filter):
        query_params["filter"] = encoded_filter
    if isinstance(page, int):
        query_params["page"] = page
    if isinstance(page_size, int):
        query_params["page_size"] = page_size
    if sort_query := _sort_value(sort):
        query_params["sort"] = sort_query
    return query_params


def _job_logs_query_params(
    *,
    attempt_id: int | Omit,
    limit: int | Omit,
    page_cursor: str | Omit,
    step_id: str | Omit,
    task_id: str | Omit,
) -> JobLogsQueryParams:
    query_params: JobLogsQueryParams = {}
    if isinstance(attempt_id, int):
        query_params["attempt_id"] = attempt_id
    if isinstance(limit, int):
        query_params["limit"] = limit
    if isinstance(page_cursor, str):
        query_params["page_cursor"] = page_cursor
    if isinstance(step_id, str):
        query_params["step_id"] = step_id
    if isinstance(task_id, str):
        query_params["task_id"] = task_id
    return query_params


def _result_list_query_params(sort: PlatformJobSortField | str | Omit) -> ListJobResultsQueryParams:
    query_params: ListJobResultsQueryParams = {}
    if sort_query := _sort_value(sort):
        query_params["sort"] = sort_query
    return query_params


def _metadata_int(metadata: Mapping[str, object], key: str) -> int:
    value = metadata.get(key, 0)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"Expected `{key}` metadata to be an int-compatible value")


def _sync_client_for_timeout(
    client: JobsClient,
    timeout: float | Timeout | None | NotGiven,
) -> JobsClient:
    if isinstance(timeout, NotGiven):
        return client
    return client.with_options(timeout=httpx.Timeout(None) if timeout is None else timeout)


def _async_client_for_timeout(
    client: AsyncJobsClient,
    timeout: float | Timeout | None | NotGiven,
) -> AsyncJobsClient:
    if isinstance(timeout, NotGiven):
        return client
    return client.with_options(timeout=httpx.Timeout(None) if timeout is None else timeout)


def _offset_page(
    *,
    data: list[ItemT],
    metadata: Mapping[str, object],
    sort: str | None,
    filter: dict[str, object] | None,
    get_page: Callable[[int], JobsOffsetPage[ItemT]],
) -> JobsOffsetPage[ItemT]:
    return JobsOffsetPage(
        data=data,
        pagination=PaginationData.model_validate(metadata),
        sort=sort,
        filter=filter,
        _get_page=get_page,
    )


async def _async_offset_page(
    *,
    data: list[ItemT],
    metadata: Mapping[str, object],
    sort: str | None,
    filter: dict[str, object] | None,
    get_page: Callable[[int], Awaitable[AsyncJobsOffsetPage[ItemT]]],
) -> AsyncJobsOffsetPage[ItemT]:
    return AsyncJobsOffsetPage(
        data=data,
        pagination=PaginationData.model_validate(metadata),
        sort=sort,
        filter=filter,
        _get_page=get_page,
    )


def _cursor_page(
    *,
    data: list[ItemT],
    metadata: Mapping[str, object],
    get_page: Callable[[str], JobsCursorPage[ItemT]],
) -> JobsCursorPage[ItemT]:
    return JobsCursorPage(
        data=data,
        total=_metadata_int(metadata, "total"),
        next_page=str(metadata["next_page"]) if metadata.get("next_page") is not None else None,
        prev_page=str(metadata["prev_page"]) if metadata.get("prev_page") is not None else None,
        _get_page=get_page,
    )


async def _async_cursor_page(
    *,
    data: list[ItemT],
    metadata: Mapping[str, object],
    get_page: Callable[[str], Awaitable[AsyncJobsCursorPage[ItemT]]],
) -> AsyncJobsCursorPage[ItemT]:
    return AsyncJobsCursorPage(
        data=data,
        total=_metadata_int(metadata, "total"),
        next_page=str(metadata["next_page"]) if metadata.get("next_page") is not None else None,
        prev_page=str(metadata["prev_page"]) if metadata.get("prev_page") is not None else None,
        _get_page=get_page,
    )


class JobResultsResource:
    """Compatibility surface for ``client.jobs.results``."""

    def __init__(self, client: JobsClient) -> None:
        self._client = client

    def create(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        artifact_storage_type: FileStorageType | str,
        artifact_url: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResultResponse:
        _required(job, "job")
        _required(name, "name")
        body = PlatformJobResultCreateRequest.model_validate(
            _merge_body(
                {"artifact_storage_type": artifact_storage_type, "artifact_url": artifact_url},
                extra_body,
            )
        )
        request = _apply_request_options(
            endpoints.create_job_result(workspace=workspace, job=job, name=name, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResultResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_result(workspace=workspace, job=job, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def list(
        self,
        name: str,
        *,
        workspace: str | None = None,
        sort: PlatformJobSortField | str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobListResultResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.list_job_results(
                workspace=workspace,
                name=name,
                query_params=_result_list_query_params(sort),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def download(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> NemoBinaryResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.download_job_result(workspace=workspace, job=job, name=name),
            extra_headers={"Accept": "application/octet-stream", **(extra_headers or {})},
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request)


class JobStepsResource:
    """Compatibility surface for ``client.jobs.steps``."""

    def __init__(self, client: JobsClient) -> None:
        self._client = client

    def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStepResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_step(workspace=workspace, job=job, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def list(
        self,
        name: str,
        *,
        workspace: str | None = None,
        filter: Mapping[str, object] | str | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: PlatformJobSortField | str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> JobsOffsetPage[PlatformJobStepWithContext]:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        sort_text = _sort_value(sort)
        filter_text = _page_filter(filter)
        request = _apply_request_options(
            endpoints.list_steps(
                workspace=workspace,
                name=name,
                query_params=_list_steps_query_params(filter=filter, page=page, page_size=page_size, sort=sort),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        response = _sync_client_for_timeout(self._client, timeout).send(request)
        first_page = response.page()

        def get_page(page_number: int) -> JobsOffsetPage[PlatformJobStepWithContext]:
            return self.list(
                name,
                workspace=workspace,
                filter=filter,
                page=page_number,
                page_size=page_size,
                sort=sort,
                extra_headers=extra_headers,
                extra_query=extra_query,
                timeout=timeout,
            )

        return _offset_page(
            data=first_page.items,
            metadata=first_page.metadata,
            sort=sort_text,
            filter=filter_text,
            get_page=get_page,
        )

    def update_status(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        status: PlatformJobStatus | str,
        error_details: Mapping[str, object] | Omit = omit,
        status_details: Mapping[str, object] | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStepResponse:
        _required(job, "job")
        _required(name, "name")
        payload: dict[str, object] = {"status": status}
        _add_body_value(payload, "error_details", error_details)
        _add_body_value(payload, "status_details", status_details)
        body = PlatformJobStatusUpdateRequest.model_validate(_merge_body(payload, extra_body))
        request = _apply_request_options(
            endpoints.update_job_step_status(workspace=workspace, job=job, name=name, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()


class JobTasksResource:
    """Compatibility surface for ``client.jobs.tasks``."""

    def __init__(self, client: JobsClient) -> None:
        self._client = client

    def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        step: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobTaskResponse:
        _required(job, "job")
        _required(step, "step")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_step_task(workspace=workspace, job=job, step=step, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def list(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobListTaskResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.list_job_step_tasks(workspace=workspace, job=job, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def create_or_update(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        step: str,
        error_details: Mapping[str, object] | Omit = omit,
        error_stack: str | Omit = omit,
        status: PlatformJobStatus | str | Omit = omit,
        status_details: Mapping[str, object] | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobTaskResponse:
        _required(job, "job")
        _required(step, "step")
        _required(name, "name")
        payload: dict[str, object] = {}
        _add_body_value(payload, "error_details", error_details)
        _add_body_value(payload, "error_stack", error_stack)
        _add_body_value(payload, "status", status)
        _add_body_value(payload, "status_details", status_details)
        body = PlatformJobTaskUpdate.model_validate(_merge_body(payload, extra_body))
        request = _apply_request_options(
            endpoints.update_job_step_task(workspace=workspace, job=job, step=step, name=name, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()


class JobsResource:
    """Compatibility surface for the generated ``client.jobs`` resource."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self._client = client_from_platform(platform, JobsClient)
        self.results = JobResultsResource(self._client)
        self.steps = JobStepsResource(self._client)
        self.tasks = JobTasksResource(self._client)

    def create(
        self,
        *,
        workspace: str | None = None,
        platform_spec: PlatformJobSpec | Mapping[str, object],
        source: str,
        spec: Mapping[str, object],
        custom_fields: Mapping[str, object] | Omit = omit,
        description: str | Omit = omit,
        name: str | Omit = omit,
        output_location: str | Omit = omit,
        ownership: Mapping[str, object] | Omit = omit,
        project: str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        payload: dict[str, object] = {
            "platform_spec": platform_spec,
            "source": source,
            "spec": dict(spec),
        }
        _add_body_value(payload, "custom_fields", custom_fields)
        _add_body_value(payload, "description", description)
        _add_body_value(payload, "name", name)
        _add_body_value(payload, "output_location", output_location)
        _add_body_value(payload, "ownership", ownership)
        _add_body_value(payload, "project", project)
        body = CreatePlatformJobRequest.model_validate(_merge_body(payload, extra_body))
        request = _apply_request_options(
            endpoints.create_job(workspace=workspace, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: Mapping[str, object] | str | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: PlatformJobListSortField | str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> JobsOffsetPage[PlatformJobResponse]:
        _extra_body_mapping(extra_body)
        sort_text = _sort_value(sort)
        filter_text = _page_filter(filter)
        request = _apply_request_options(
            endpoints.list_jobs(
                workspace=workspace,
                query_params=_list_jobs_query_params(filter=filter, page=page, page_size=page_size, sort=sort),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        response = _sync_client_for_timeout(self._client, timeout).send(request)
        first_page = response.page()

        def get_page(page_number: int) -> JobsOffsetPage[PlatformJobResponse]:
            return self.list(
                workspace=workspace,
                filter=filter,
                page=page_number,
                page_size=page_size,
                sort=sort,
                extra_headers=extra_headers,
                extra_query=extra_query,
                timeout=timeout,
            )

        return _offset_page(
            data=first_page.items,
            metadata=first_page.metadata,
            sort=sort_text,
            filter=filter_text,
            get_page=get_page,
        )

    def delete(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> None:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.delete_job(workspace=workspace, name=name),
            extra_headers={"Accept": "*/*", **(extra_headers or {})},
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def cancel(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.cancel_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def get_logs(
        self,
        name: str,
        *,
        workspace: str | None = None,
        attempt_id: int | Omit = omit,
        limit: int | Omit = omit,
        page_cursor: str | Omit = omit,
        step_id: str | Omit = omit,
        task_id: str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> JobsCursorPage[PlatformJobLog]:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.list_job_logs(
                workspace=workspace,
                name=name,
                query_params=_job_logs_query_params(
                    attempt_id=attempt_id,
                    limit=limit,
                    page_cursor=page_cursor,
                    step_id=step_id,
                    task_id=task_id,
                ),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        response = _sync_client_for_timeout(self._client, timeout).send(request)
        first_page = response.page()

        def get_page(next_cursor: str) -> JobsCursorPage[PlatformJobLog]:
            return self.get_logs(
                name,
                workspace=workspace,
                attempt_id=attempt_id,
                limit=limit,
                page_cursor=next_cursor,
                step_id=step_id,
                task_id=task_id,
                extra_headers=extra_headers,
                extra_query=extra_query,
                timeout=timeout,
            )

        return _cursor_page(data=first_page.items, metadata=first_page.metadata, get_page=get_page)

    def get_status(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStatusResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_status(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def list_execution_profiles(
        self,
        *,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> Sequence[ExecutionProfile]:
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_execution_profiles(),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def pause(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.pause_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def resume(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.resume_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return _sync_client_for_timeout(self._client, timeout).send(request).data()

    def update_status_details(
        self,
        name: str,
        *,
        workspace: str | None = None,
        body: Mapping[str, object],
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> object:
        _required(name, "name")
        request_body = JobStatusDetailsUpdate.model_validate(_merge_body(dict(body), extra_body))
        request = _apply_request_options(
            endpoints.update_job_status_details(workspace=workspace, name=name, body=request_body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        _sync_client_for_timeout(self._client, timeout).send(request).data()
        return None


class AsyncJobResultsResource:
    """Async compatibility surface for ``client.jobs.results``."""

    def __init__(self, client: AsyncJobsClient) -> None:
        self._client = client

    async def create(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        artifact_storage_type: FileStorageType | str,
        artifact_url: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResultResponse:
        _required(job, "job")
        _required(name, "name")
        body = PlatformJobResultCreateRequest.model_validate(
            _merge_body(
                {"artifact_storage_type": artifact_storage_type, "artifact_url": artifact_url},
                extra_body,
            )
        )
        request = _apply_request_options(
            endpoints.create_job_result(workspace=workspace, job=job, name=name, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResultResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_result(workspace=workspace, job=job, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def list(
        self,
        name: str,
        *,
        workspace: str | None = None,
        sort: PlatformJobSortField | str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobListResultResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.list_job_results(
                workspace=workspace,
                name=name,
                query_params=_result_list_query_params(sort),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def download(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> AsyncNemoBinaryResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.download_job_result(workspace=workspace, job=job, name=name),
            extra_headers={"Accept": "application/octet-stream", **(extra_headers or {})},
            extra_query=extra_query,
        )
        return await _async_client_for_timeout(self._client, timeout).send(request)


class AsyncJobStepsResource:
    """Async compatibility surface for ``client.jobs.steps``."""

    def __init__(self, client: AsyncJobsClient) -> None:
        self._client = client

    async def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStepResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_step(workspace=workspace, job=job, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    def list(
        self,
        name: str,
        *,
        workspace: str | None = None,
        filter: Mapping[str, object] | str | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: PlatformJobSortField | str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> AsyncJobsOffsetPageRequest[PlatformJobStepWithContext]:
        async def get_first_page() -> AsyncJobsOffsetPage[PlatformJobStepWithContext]:
            return await self._list_page(
                name,
                workspace=workspace,
                filter=filter,
                page=page,
                page_size=page_size,
                sort=sort,
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
            )

        return AsyncJobsOffsetPageRequest(get_first_page)

    async def _list_page(
        self,
        name: str,
        *,
        workspace: str | None,
        filter: Mapping[str, object] | str | Omit,
        page: int | Omit,
        page_size: int | Omit,
        sort: PlatformJobSortField | str | Omit,
        extra_headers: Headers | None,
        extra_query: Query | None,
        extra_body: Body | None,
        timeout: float | Timeout | None | NotGiven,
    ) -> AsyncJobsOffsetPage[PlatformJobStepWithContext]:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        sort_text = _sort_value(sort)
        filter_text = _page_filter(filter)
        request = _apply_request_options(
            endpoints.list_steps(
                workspace=workspace,
                name=name,
                query_params=_list_steps_query_params(filter=filter, page=page, page_size=page_size, sort=sort),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        response = await _async_client_for_timeout(self._client, timeout).send(request)
        first_page = response.page()

        async def get_page(page_number: int) -> AsyncJobsOffsetPage[PlatformJobStepWithContext]:
            return await self._list_page(
                name,
                workspace=workspace,
                filter=filter,
                page=page_number,
                page_size=page_size,
                sort=sort,
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=None,
                timeout=timeout,
            )

        return await _async_offset_page(
            data=first_page.items,
            metadata=first_page.metadata,
            sort=sort_text,
            filter=filter_text,
            get_page=get_page,
        )

    async def update_status(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        status: PlatformJobStatus | str,
        error_details: Mapping[str, object] | Omit = omit,
        status_details: Mapping[str, object] | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStepResponse:
        _required(job, "job")
        _required(name, "name")
        payload: dict[str, object] = {"status": status}
        _add_body_value(payload, "error_details", error_details)
        _add_body_value(payload, "status_details", status_details)
        body = PlatformJobStatusUpdateRequest.model_validate(_merge_body(payload, extra_body))
        request = _apply_request_options(
            endpoints.update_job_step_status(workspace=workspace, job=job, name=name, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()


class AsyncJobTasksResource:
    """Async compatibility surface for ``client.jobs.tasks``."""

    def __init__(self, client: AsyncJobsClient) -> None:
        self._client = client

    async def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        step: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobTaskResponse:
        _required(job, "job")
        _required(step, "step")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_step_task(workspace=workspace, job=job, step=step, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def list(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobListTaskResponse:
        _required(job, "job")
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.list_job_step_tasks(workspace=workspace, job=job, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def create_or_update(
        self,
        name: str,
        *,
        workspace: str | None = None,
        job: str,
        step: str,
        error_details: Mapping[str, object] | Omit = omit,
        error_stack: str | Omit = omit,
        status: PlatformJobStatus | str | Omit = omit,
        status_details: Mapping[str, object] | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobTaskResponse:
        _required(job, "job")
        _required(step, "step")
        _required(name, "name")
        payload: dict[str, object] = {}
        _add_body_value(payload, "error_details", error_details)
        _add_body_value(payload, "error_stack", error_stack)
        _add_body_value(payload, "status", status)
        _add_body_value(payload, "status_details", status_details)
        body = PlatformJobTaskUpdate.model_validate(_merge_body(payload, extra_body))
        request = _apply_request_options(
            endpoints.update_job_step_task(workspace=workspace, job=job, step=step, name=name, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()


class AsyncJobsResource:
    """Async compatibility surface for the generated ``client.jobs`` resource."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._client = client_from_platform(platform, AsyncJobsClient)
        self.results = AsyncJobResultsResource(self._client)
        self.steps = AsyncJobStepsResource(self._client)
        self.tasks = AsyncJobTasksResource(self._client)

    async def create(
        self,
        *,
        workspace: str | None = None,
        platform_spec: PlatformJobSpec | Mapping[str, object],
        source: str,
        spec: Mapping[str, object],
        custom_fields: Mapping[str, object] | Omit = omit,
        description: str | Omit = omit,
        name: str | Omit = omit,
        output_location: str | Omit = omit,
        ownership: Mapping[str, object] | Omit = omit,
        project: str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        payload: dict[str, object] = {
            "platform_spec": platform_spec,
            "source": source,
            "spec": dict(spec),
        }
        _add_body_value(payload, "custom_fields", custom_fields)
        _add_body_value(payload, "description", description)
        _add_body_value(payload, "name", name)
        _add_body_value(payload, "output_location", output_location)
        _add_body_value(payload, "ownership", ownership)
        _add_body_value(payload, "project", project)
        body = CreatePlatformJobRequest.model_validate(_merge_body(payload, extra_body))
        request = _apply_request_options(
            endpoints.create_job(workspace=workspace, body=body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: Mapping[str, object] | str | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: PlatformJobListSortField | str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> AsyncJobsOffsetPageRequest[PlatformJobResponse]:
        async def get_first_page() -> AsyncJobsOffsetPage[PlatformJobResponse]:
            return await self._list_page(
                workspace=workspace,
                filter=filter,
                page=page,
                page_size=page_size,
                sort=sort,
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
            )

        return AsyncJobsOffsetPageRequest(get_first_page)

    async def _list_page(
        self,
        *,
        workspace: str | None,
        filter: Mapping[str, object] | str | Omit,
        page: int | Omit,
        page_size: int | Omit,
        sort: PlatformJobListSortField | str | Omit,
        extra_headers: Headers | None,
        extra_query: Query | None,
        extra_body: Body | None,
        timeout: float | Timeout | None | NotGiven,
    ) -> AsyncJobsOffsetPage[PlatformJobResponse]:
        _extra_body_mapping(extra_body)
        sort_text = _sort_value(sort)
        filter_text = _page_filter(filter)
        request = _apply_request_options(
            endpoints.list_jobs(
                workspace=workspace,
                query_params=_list_jobs_query_params(filter=filter, page=page, page_size=page_size, sort=sort),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        response = await _async_client_for_timeout(self._client, timeout).send(request)
        first_page = response.page()

        async def get_page(page_number: int) -> AsyncJobsOffsetPage[PlatformJobResponse]:
            return await self._list_page(
                workspace=workspace,
                filter=filter,
                page=page_number,
                page_size=page_size,
                sort=sort,
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=None,
                timeout=timeout,
            )

        return await _async_offset_page(
            data=first_page.items,
            metadata=first_page.metadata,
            sort=sort_text,
            filter=filter_text,
            get_page=get_page,
        )

    async def delete(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> None:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.delete_job(workspace=workspace, name=name),
            extra_headers={"Accept": "*/*", **(extra_headers or {})},
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def cancel(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.cancel_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    def get_logs(
        self,
        name: str,
        *,
        workspace: str | None = None,
        attempt_id: int | Omit = omit,
        limit: int | Omit = omit,
        page_cursor: str | Omit = omit,
        step_id: str | Omit = omit,
        task_id: str | Omit = omit,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> AsyncJobsCursorPageRequest[PlatformJobLog]:
        async def get_first_page() -> AsyncJobsCursorPage[PlatformJobLog]:
            return await self._logs_page(
                name,
                workspace=workspace,
                attempt_id=attempt_id,
                limit=limit,
                page_cursor=page_cursor,
                step_id=step_id,
                task_id=task_id,
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
            )

        return AsyncJobsCursorPageRequest(get_first_page)

    async def _logs_page(
        self,
        name: str,
        *,
        workspace: str | None,
        attempt_id: int | Omit,
        limit: int | Omit,
        page_cursor: str | Omit,
        step_id: str | Omit,
        task_id: str | Omit,
        extra_headers: Headers | None,
        extra_query: Query | None,
        extra_body: Body | None,
        timeout: float | Timeout | None | NotGiven,
    ) -> AsyncJobsCursorPage[PlatformJobLog]:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.list_job_logs(
                workspace=workspace,
                name=name,
                query_params=_job_logs_query_params(
                    attempt_id=attempt_id,
                    limit=limit,
                    page_cursor=page_cursor,
                    step_id=step_id,
                    task_id=task_id,
                ),
            ),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        response = await _async_client_for_timeout(self._client, timeout).send(request)
        first_page = response.page()

        async def get_page(next_cursor: str) -> AsyncJobsCursorPage[PlatformJobLog]:
            return await self._logs_page(
                name,
                workspace=workspace,
                attempt_id=attempt_id,
                limit=limit,
                page_cursor=next_cursor,
                step_id=step_id,
                task_id=task_id,
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=None,
                timeout=timeout,
            )

        return await _async_cursor_page(data=first_page.items, metadata=first_page.metadata, get_page=get_page)

    async def get_status(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStatusResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_job_status(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def list_execution_profiles(
        self,
        *,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> Sequence[ExecutionProfile]:
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.get_execution_profiles(),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def pause(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.pause_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def resume(
        self,
        name: str,
        *,
        workspace: str | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        _required(name, "name")
        _extra_body_mapping(extra_body)
        request = _apply_request_options(
            endpoints.resume_job(workspace=workspace, name=name),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        return (await _async_client_for_timeout(self._client, timeout).send(request)).data()

    async def update_status_details(
        self,
        name: str,
        *,
        workspace: str | None = None,
        body: Mapping[str, object],
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
    ) -> object:
        _required(name, "name")
        request_body = JobStatusDetailsUpdate.model_validate(_merge_body(dict(body), extra_body))
        request = _apply_request_options(
            endpoints.update_job_status_details(workspace=workspace, name=name, body=request_body),
            extra_headers=extra_headers,
            extra_query=extra_query,
        )
        (await _async_client_for_timeout(self._client, timeout).send(request)).data()
        return None


jobs_sdk_resources: NemoPluginSDKResources[JobsResource, AsyncJobsResource] = NemoPluginSDKResources(
    sync_resource=JobsResource,
    async_resource=AsyncJobsResource,
)

__all__ = [
    "AsyncJobResultsResource",
    "AsyncJobStepsResource",
    "AsyncJobTasksResource",
    "AsyncJobsCursorPage",
    "AsyncJobsCursorPageRequest",
    "AsyncJobsOffsetPage",
    "AsyncJobsOffsetPageRequest",
    "AsyncJobsResource",
    "JobResultsResource",
    "JobStepsResource",
    "JobTasksResource",
    "JobsCursorPage",
    "JobsOffsetPage",
    "JobsResource",
    "jobs_sdk_resources",
]
