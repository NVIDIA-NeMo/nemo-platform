# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from __future__ import annotations

from typing import Dict

import httpx

from .steps import (
    StepsResource,
    AsyncStepsResource,
    StepsResourceWithRawResponse,
    AsyncStepsResourceWithRawResponse,
    StepsResourceWithStreamingResponse,
    AsyncStepsResourceWithStreamingResponse,
)
from .tasks import (
    TasksResource,
    AsyncTasksResource,
    TasksResourceWithRawResponse,
    AsyncTasksResourceWithRawResponse,
    TasksResourceWithStreamingResponse,
    AsyncTasksResourceWithStreamingResponse,
)
from .results import (
    ResultsResource,
    AsyncResultsResource,
    ResultsResourceWithRawResponse,
    AsyncResultsResourceWithRawResponse,
    ResultsResourceWithStreamingResponse,
    AsyncResultsResourceWithStreamingResponse,
)
from ..._types import Body, Omit, Query, Headers, NoneType, NotGiven, omit, not_given
from ..._utils import path_template, maybe_transform, async_maybe_transform
from ..._compat import cached_property
from ..._resource import SyncAPIResource, AsyncAPIResource
from ..._response import (
    to_raw_response_wrapper,
    to_streamed_response_wrapper,
    async_to_raw_response_wrapper,
    async_to_streamed_response_wrapper,
)
from ...pagination import SyncLogsPagination, AsyncLogsPagination, SyncDefaultPagination, AsyncDefaultPagination
from ...types.jobs import (
    PlatformJobSortField,
    PlatformJobSpecParam,
    job_list_params,
    job_create_params,
    job_get_logs_params,
    job_update_status_details_params,
)
from ..._base_client import AsyncPaginator, make_request_options
from ...types.shared.platform_job_log import PlatformJobLog
from ...types.jobs.platform_job_response import PlatformJobResponse
from ...types.jobs.platform_job_sort_field import PlatformJobSortField
from ...types.jobs.platform_job_spec_param import PlatformJobSpecParam
from ...types.shared.platform_job_status_response import PlatformJobStatusResponse
from ...types.jobs.platform_jobs_list_filter_param import PlatformJobsListFilterParam
from ...types.jobs.job_list_execution_profiles_response import JobListExecutionProfilesResponse

__all__ = ["JobsResource", "AsyncJobsResource"]


class JobsResource(SyncAPIResource):
    @cached_property
    def results(self) -> ResultsResource:
        return ResultsResource(self._client)

    @cached_property
    def steps(self) -> StepsResource:
        return StepsResource(self._client)

    @cached_property
    def tasks(self) -> TasksResource:
        return TasksResource(self._client)

    @cached_property
    def with_raw_response(self) -> JobsResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return JobsResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> JobsResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return JobsResourceWithStreamingResponse(self)

    def create(
        self,
        *,
        workspace: str | None = None,
        platform_spec: PlatformJobSpecParam,
        source: str,
        spec: Dict[str, object],
        custom_fields: Dict[str, object] | Omit = omit,
        description: str | Omit = omit,
        name: str | Omit = omit,
        ownership: Dict[str, object] | Omit = omit,
        project: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Create a new platform job.

        Args:
          platform_spec: Specification for a platform job, containing steps and secrets.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        return self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs", workspace=workspace),
            body=maybe_transform(
                {
                    "platform_spec": platform_spec,
                    "source": source,
                    "spec": spec,
                    "custom_fields": custom_fields,
                    "description": description,
                    "name": name,
                    "ownership": ownership,
                    "project": project,
                },
                job_create_params.JobCreateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Get a platform job by name.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._get(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: PlatformJobsListFilterParam | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: PlatformJobSortField | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> SyncDefaultPagination[PlatformJobResponse]:
        """
        List platform jobs with filtering and pagination.

        Args:
          filter: Filter jobs by workspace, project, name, status, source, created_at, and
              updated_at.

          page: Page number.

          page_size: Page size.

          sort: The field to sort by. To sort in decreasing order, use `-` in front of the field
              name.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        return self._get_api_list(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs", workspace=workspace),
            page=SyncDefaultPagination[PlatformJobResponse],
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                query=maybe_transform(
                    {
                        "filter": filter,
                        "page": page,
                        "page_size": page_size,
                        "sort": sort,
                    },
                    job_list_params.JobListParams,
                ),
            ),
            model=PlatformJobResponse,
        )

    def delete(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> None:
        """
        Delete a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        extra_headers = {"Accept": "*/*", **(extra_headers or {})}
        return self._delete(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=NoneType,
        )

    def cancel(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Cancel a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/cancel", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

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
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> SyncLogsPagination[PlatformJobLog]:
        """
        Get paginated logs for a platform job.

        Args:
          attempt_id: Filter logs by job attempt ID

          limit: Maximum number of logs to return

          page_cursor: Page cursor

          step_id: Filter logs by step name

          task_id: Filter logs by task ID

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._get_api_list(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/logs", workspace=workspace, name=name),
            page=SyncLogsPagination[PlatformJobLog],
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                query=maybe_transform(
                    {
                        "attempt_id": attempt_id,
                        "limit": limit,
                        "page_cursor": page_cursor,
                        "step_id": step_id,
                        "task_id": task_id,
                    },
                    job_get_logs_params.JobGetLogsParams,
                ),
            ),
            model=PlatformJobLog,
        )

    def get_status(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStatusResponse:
        """
        Get the status of a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._get(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/status", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobStatusResponse,
        )

    def list_execution_profiles(
        self,
        *,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> JobListExecutionProfilesResponse:
        """Get all currently configured execution profiles."""
        return self._get(
            "/apis/jobs/v2/execution-profiles",
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=JobListExecutionProfilesResponse,
        )

    def pause(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Pause a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/pause", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    def resume(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Resume a paused platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/resume", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    def update_status_details(
        self,
        name: str,
        *,
        workspace: str | None = None,
        body: Dict[str, object],
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> object:
        """
        Update the status details of a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._patch(
            path_template(
                "/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/status-details", workspace=workspace, name=name
            ),
            body=maybe_transform(body, job_update_status_details_params.JobUpdateStatusDetailsParams),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=object,
        )


class AsyncJobsResource(AsyncAPIResource):
    @cached_property
    def results(self) -> AsyncResultsResource:
        return AsyncResultsResource(self._client)

    @cached_property
    def steps(self) -> AsyncStepsResource:
        return AsyncStepsResource(self._client)

    @cached_property
    def tasks(self) -> AsyncTasksResource:
        return AsyncTasksResource(self._client)

    @cached_property
    def with_raw_response(self) -> AsyncJobsResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return AsyncJobsResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> AsyncJobsResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return AsyncJobsResourceWithStreamingResponse(self)

    async def create(
        self,
        *,
        workspace: str | None = None,
        platform_spec: PlatformJobSpecParam,
        source: str,
        spec: Dict[str, object],
        custom_fields: Dict[str, object] | Omit = omit,
        description: str | Omit = omit,
        name: str | Omit = omit,
        ownership: Dict[str, object] | Omit = omit,
        project: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Create a new platform job.

        Args:
          platform_spec: Specification for a platform job, containing steps and secrets.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        return await self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs", workspace=workspace),
            body=await async_maybe_transform(
                {
                    "platform_spec": platform_spec,
                    "source": source,
                    "spec": spec,
                    "custom_fields": custom_fields,
                    "description": description,
                    "name": name,
                    "ownership": ownership,
                    "project": project,
                },
                job_create_params.JobCreateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    async def retrieve(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Get a platform job by name.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return await self._get(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: PlatformJobsListFilterParam | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: PlatformJobSortField | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AsyncPaginator[PlatformJobResponse, AsyncDefaultPagination[PlatformJobResponse]]:
        """
        List platform jobs with filtering and pagination.

        Args:
          filter: Filter jobs by workspace, project, name, status, source, created_at, and
              updated_at.

          page: Page number.

          page_size: Page size.

          sort: The field to sort by. To sort in decreasing order, use `-` in front of the field
              name.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        return self._get_api_list(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs", workspace=workspace),
            page=AsyncDefaultPagination[PlatformJobResponse],
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                query=maybe_transform(
                    {
                        "filter": filter,
                        "page": page,
                        "page_size": page_size,
                        "sort": sort,
                    },
                    job_list_params.JobListParams,
                ),
            ),
            model=PlatformJobResponse,
        )

    async def delete(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> None:
        """
        Delete a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        extra_headers = {"Accept": "*/*", **(extra_headers or {})}
        return await self._delete(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=NoneType,
        )

    async def cancel(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Cancel a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return await self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/cancel", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

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
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AsyncPaginator[PlatformJobLog, AsyncLogsPagination[PlatformJobLog]]:
        """
        Get paginated logs for a platform job.

        Args:
          attempt_id: Filter logs by job attempt ID

          limit: Maximum number of logs to return

          page_cursor: Page cursor

          step_id: Filter logs by step name

          task_id: Filter logs by task ID

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return self._get_api_list(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/logs", workspace=workspace, name=name),
            page=AsyncLogsPagination[PlatformJobLog],
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                query=maybe_transform(
                    {
                        "attempt_id": attempt_id,
                        "limit": limit,
                        "page_cursor": page_cursor,
                        "step_id": step_id,
                        "task_id": task_id,
                    },
                    job_get_logs_params.JobGetLogsParams,
                ),
            ),
            model=PlatformJobLog,
        )

    async def get_status(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobStatusResponse:
        """
        Get the status of a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return await self._get(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/status", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobStatusResponse,
        )

    async def list_execution_profiles(
        self,
        *,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> JobListExecutionProfilesResponse:
        """Get all currently configured execution profiles."""
        return await self._get(
            "/apis/jobs/v2/execution-profiles",
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=JobListExecutionProfilesResponse,
        )

    async def pause(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Pause a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return await self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/pause", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    async def resume(
        self,
        name: str,
        *,
        workspace: str | None = None,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> PlatformJobResponse:
        """
        Resume a paused platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return await self._post(
            path_template("/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/resume", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=PlatformJobResponse,
        )

    async def update_status_details(
        self,
        name: str,
        *,
        workspace: str | None = None,
        body: Dict[str, object],
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> object:
        """
        Update the status details of a platform job.

        Args:
          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not name:
            raise ValueError(f"Expected a non-empty value for `name` but received {name!r}")
        return await self._patch(
            path_template(
                "/apis/jobs/v2/workspaces/{workspace}/jobs/{name}/status-details", workspace=workspace, name=name
            ),
            body=await async_maybe_transform(body, job_update_status_details_params.JobUpdateStatusDetailsParams),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=object,
        )


class JobsResourceWithRawResponse:
    def __init__(self, jobs: JobsResource) -> None:
        self._jobs = jobs

        self.create = to_raw_response_wrapper(
            jobs.create,
        )
        self.retrieve = to_raw_response_wrapper(
            jobs.retrieve,
        )
        self.list = to_raw_response_wrapper(
            jobs.list,
        )
        self.delete = to_raw_response_wrapper(
            jobs.delete,
        )
        self.cancel = to_raw_response_wrapper(
            jobs.cancel,
        )
        self.get_logs = to_raw_response_wrapper(
            jobs.get_logs,
        )
        self.get_status = to_raw_response_wrapper(
            jobs.get_status,
        )
        self.list_execution_profiles = to_raw_response_wrapper(
            jobs.list_execution_profiles,
        )
        self.pause = to_raw_response_wrapper(
            jobs.pause,
        )
        self.resume = to_raw_response_wrapper(
            jobs.resume,
        )
        self.update_status_details = to_raw_response_wrapper(
            jobs.update_status_details,
        )

    @cached_property
    def results(self) -> ResultsResourceWithRawResponse:
        return ResultsResourceWithRawResponse(self._jobs.results)

    @cached_property
    def steps(self) -> StepsResourceWithRawResponse:
        return StepsResourceWithRawResponse(self._jobs.steps)

    @cached_property
    def tasks(self) -> TasksResourceWithRawResponse:
        return TasksResourceWithRawResponse(self._jobs.tasks)


class AsyncJobsResourceWithRawResponse:
    def __init__(self, jobs: AsyncJobsResource) -> None:
        self._jobs = jobs

        self.create = async_to_raw_response_wrapper(
            jobs.create,
        )
        self.retrieve = async_to_raw_response_wrapper(
            jobs.retrieve,
        )
        self.list = async_to_raw_response_wrapper(
            jobs.list,
        )
        self.delete = async_to_raw_response_wrapper(
            jobs.delete,
        )
        self.cancel = async_to_raw_response_wrapper(
            jobs.cancel,
        )
        self.get_logs = async_to_raw_response_wrapper(
            jobs.get_logs,
        )
        self.get_status = async_to_raw_response_wrapper(
            jobs.get_status,
        )
        self.list_execution_profiles = async_to_raw_response_wrapper(
            jobs.list_execution_profiles,
        )
        self.pause = async_to_raw_response_wrapper(
            jobs.pause,
        )
        self.resume = async_to_raw_response_wrapper(
            jobs.resume,
        )
        self.update_status_details = async_to_raw_response_wrapper(
            jobs.update_status_details,
        )

    @cached_property
    def results(self) -> AsyncResultsResourceWithRawResponse:
        return AsyncResultsResourceWithRawResponse(self._jobs.results)

    @cached_property
    def steps(self) -> AsyncStepsResourceWithRawResponse:
        return AsyncStepsResourceWithRawResponse(self._jobs.steps)

    @cached_property
    def tasks(self) -> AsyncTasksResourceWithRawResponse:
        return AsyncTasksResourceWithRawResponse(self._jobs.tasks)


class JobsResourceWithStreamingResponse:
    def __init__(self, jobs: JobsResource) -> None:
        self._jobs = jobs

        self.create = to_streamed_response_wrapper(
            jobs.create,
        )
        self.retrieve = to_streamed_response_wrapper(
            jobs.retrieve,
        )
        self.list = to_streamed_response_wrapper(
            jobs.list,
        )
        self.delete = to_streamed_response_wrapper(
            jobs.delete,
        )
        self.cancel = to_streamed_response_wrapper(
            jobs.cancel,
        )
        self.get_logs = to_streamed_response_wrapper(
            jobs.get_logs,
        )
        self.get_status = to_streamed_response_wrapper(
            jobs.get_status,
        )
        self.list_execution_profiles = to_streamed_response_wrapper(
            jobs.list_execution_profiles,
        )
        self.pause = to_streamed_response_wrapper(
            jobs.pause,
        )
        self.resume = to_streamed_response_wrapper(
            jobs.resume,
        )
        self.update_status_details = to_streamed_response_wrapper(
            jobs.update_status_details,
        )

    @cached_property
    def results(self) -> ResultsResourceWithStreamingResponse:
        return ResultsResourceWithStreamingResponse(self._jobs.results)

    @cached_property
    def steps(self) -> StepsResourceWithStreamingResponse:
        return StepsResourceWithStreamingResponse(self._jobs.steps)

    @cached_property
    def tasks(self) -> TasksResourceWithStreamingResponse:
        return TasksResourceWithStreamingResponse(self._jobs.tasks)


class AsyncJobsResourceWithStreamingResponse:
    def __init__(self, jobs: AsyncJobsResource) -> None:
        self._jobs = jobs

        self.create = async_to_streamed_response_wrapper(
            jobs.create,
        )
        self.retrieve = async_to_streamed_response_wrapper(
            jobs.retrieve,
        )
        self.list = async_to_streamed_response_wrapper(
            jobs.list,
        )
        self.delete = async_to_streamed_response_wrapper(
            jobs.delete,
        )
        self.cancel = async_to_streamed_response_wrapper(
            jobs.cancel,
        )
        self.get_logs = async_to_streamed_response_wrapper(
            jobs.get_logs,
        )
        self.get_status = async_to_streamed_response_wrapper(
            jobs.get_status,
        )
        self.list_execution_profiles = async_to_streamed_response_wrapper(
            jobs.list_execution_profiles,
        )
        self.pause = async_to_streamed_response_wrapper(
            jobs.pause,
        )
        self.resume = async_to_streamed_response_wrapper(
            jobs.resume,
        )
        self.update_status_details = async_to_streamed_response_wrapper(
            jobs.update_status_details,
        )

    @cached_property
    def results(self) -> AsyncResultsResourceWithStreamingResponse:
        return AsyncResultsResourceWithStreamingResponse(self._jobs.results)

    @cached_property
    def steps(self) -> AsyncStepsResourceWithStreamingResponse:
        return AsyncStepsResourceWithStreamingResponse(self._jobs.steps)

    @cached_property
    def tasks(self) -> AsyncTasksResourceWithStreamingResponse:
        return AsyncTasksResourceWithStreamingResponse(self._jobs.tasks)
