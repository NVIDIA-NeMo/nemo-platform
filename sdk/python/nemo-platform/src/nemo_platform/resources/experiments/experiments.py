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

from ..._types import Body, Omit, Query, Headers, NoneType, NotGiven, omit, not_given
from ..._utils import path_template, maybe_transform, async_maybe_transform
from .sessions import (
    SessionsResource,
    AsyncSessionsResource,
    SessionsResourceWithRawResponse,
    AsyncSessionsResourceWithRawResponse,
    SessionsResourceWithStreamingResponse,
    AsyncSessionsResourceWithStreamingResponse,
)
from ..._compat import cached_property
from ..._resource import SyncAPIResource, AsyncAPIResource
from ..._response import (
    to_raw_response_wrapper,
    to_streamed_response_wrapper,
    async_to_raw_response_wrapper,
    async_to_streamed_response_wrapper,
)
from ...pagination import SyncDefaultPagination, AsyncDefaultPagination
from ..._base_client import AsyncPaginator, make_request_options
from ...types.experiments import (
    experiment_list_params,
    experiment_create_params,
    experiment_update_params,
)
from ...types.experiments.experiment_response import ExperimentResponse
from ...types.experiments.experiment_filter_param import ExperimentFilterParam
from ..._exceptions import ConflictError

__all__ = ["ExperimentsResource", "AsyncExperimentsResource"]


class ExperimentsResource(SyncAPIResource):
    @cached_property
    def sessions(self) -> SessionsResource:
        return SessionsResource(self._client)

    @cached_property
    def with_raw_response(self) -> ExperimentsResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return ExperimentsResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> ExperimentsResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return ExperimentsResourceWithStreamingResponse(self)

    def create(
        self,
        *,
        workspace: str | None = None,
        dataset_name: str,
        experiment_group_id: str,
        name: str,
        dataset_version: str | Omit = omit,
        description: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        source_link: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        exist_ok: bool = False,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentResponse:
        """
        Create Experiment

        Args:
          dataset_name: Producer-supplied dataset name.

          experiment_group_id: Entity id of the owning ExperimentGroup. Required — the group must already
              exist.

          name: Producer-supplied, workspace-unique experiment id.

          dataset_version: Producer-supplied dataset version.

          description: Human-readable description.

          metadata: Free-form producer metadata.

          source_link: Optional URL for the source experiment.


          exist_ok: Do not raise an error if the resource already exists. Returns the existing resource.


          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        try:
            if workspace is None:
                workspace = self._client._get_workspace_path_param()
            if not workspace:
                raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
            return self._post(
                path_template("/apis/intake/v2/workspaces/{workspace}/experiments", workspace=workspace),
                body=maybe_transform(
                    {
                        "dataset_name": dataset_name,
                        "experiment_group_id": experiment_group_id,
                        "name": name,
                        "dataset_version": dataset_version,
                        "description": description,
                        "metadata": metadata,
                        "source_link": source_link,
                    },
                    experiment_create_params.ExperimentCreateParams,
                ),
                options=make_request_options(
                    extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
                ),
                cast_to=ExperimentResponse,
            )
        except ConflictError:
            if not exist_ok:
                raise
            return self.retrieve(name = name, workspace = workspace)

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
    ) -> ExperimentResponse:
        """
        Get Experiment

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiments/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )

    def update(
        self,
        path_name: str,
        *,
        workspace: str | None = None,
        dataset_name: str,
        experiment_group_id: str,
        body_name: str,
        dataset_version: str | Omit = omit,
        description: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        source_link: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentResponse:
        """
        Update Experiment

        Args:
          dataset_name: Producer-supplied dataset name.

          experiment_group_id: Entity id of the owning ExperimentGroup. Required — the group must already
              exist.

          body_name: Producer-supplied, workspace-unique experiment id.

          dataset_version: Producer-supplied dataset version.

          description: Human-readable description.

          metadata: Free-form producer metadata.

          source_link: Optional URL for the source experiment.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not path_name:
            raise ValueError(f"Expected a non-empty value for `path_name` but received {path_name!r}")
        return self._put(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiments/{path_name}",
                workspace=workspace,
                path_name=path_name,
            ),
            body=maybe_transform(
                {
                    "dataset_name": dataset_name,
                    "experiment_group_id": experiment_group_id,
                    "body_name": body_name,
                    "dataset_version": dataset_version,
                    "description": description,
                    "metadata": metadata,
                    "source_link": source_link,
                },
                experiment_update_params.ExperimentUpdateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: ExperimentFilterParam | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> SyncDefaultPagination[ExperimentResponse]:
        """
        List Experiments

        Args:
          filter: Filter experiments by name, experiment_group_id, dataset_name, dataset_version,
              created_by, created_at, or updated_at. Pass is_deleted=true to return only
              soft-deleted experiments; omit to see only live ones. Pass is_pinned=true (or
              false) to filter by pinned state; omit to return both. Filter by a rollup metric
              with numeric range operators ($gte/$lte/$gt/$lt/$eq): filter[run_count][$gte]=5,
              filter[cost_usd.mean][$lte]=0.5, filter[latency_ms.p95][$lte]=1000, or
              filter[evaluators.<name>.mean][$gte]=0.8.

          page: Page number.

          page_size: Page size.

          sort: Field to sort by; prefix with '-' for descending. Sort by an experiment
              attribute (name, created_at, updated_at, pinned_at) or by an aggregate metric:
              run_count, cost_usd.<stat>, latency_ms.<stat>, or evaluators.<name>.<stat>,
              where <stat> is one of mean, median, p90, p95, p99, sum, count.

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiments", workspace=workspace),
            page=SyncDefaultPagination[ExperimentResponse],
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
                    experiment_list_params.ExperimentListParams,
                ),
            ),
            model=ExperimentResponse,
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
        Delete Experiment

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiments/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=NoneType,
        )

    def pin(
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
    ) -> ExperimentResponse:
        """
        Pin an experiment to the top of the list (workspace-shared).

        Re-pinning an already-pinned experiment refreshes `pinned_at` to the current
        timestamp, which is intentional (most-recently-pinned sorts first).

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
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiments/{name}/pin", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )

    def unpin(
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
    ) -> ExperimentResponse:
        """Unpin an experiment.

        Idempotent: unpinning an already-unpinned experiment is a
        no-op.

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
        return self._delete(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiments/{name}/pin", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )


class AsyncExperimentsResource(AsyncAPIResource):
    @cached_property
    def sessions(self) -> AsyncSessionsResource:
        return AsyncSessionsResource(self._client)

    @cached_property
    def with_raw_response(self) -> AsyncExperimentsResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return AsyncExperimentsResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> AsyncExperimentsResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return AsyncExperimentsResourceWithStreamingResponse(self)

    async def create(
        self,
        *,
        workspace: str | None = None,
        dataset_name: str,
        experiment_group_id: str,
        name: str,
        dataset_version: str | Omit = omit,
        description: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        source_link: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        exist_ok: bool = False,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentResponse:
        """
        Create Experiment

        Args:
          dataset_name: Producer-supplied dataset name.

          experiment_group_id: Entity id of the owning ExperimentGroup. Required — the group must already
              exist.

          name: Producer-supplied, workspace-unique experiment id.

          dataset_version: Producer-supplied dataset version.

          description: Human-readable description.

          metadata: Free-form producer metadata.

          source_link: Optional URL for the source experiment.


          exist_ok: Do not raise an error if the resource already exists. Returns the existing resource.


          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        try:
            if workspace is None:
                workspace = self._client._get_workspace_path_param()
            if not workspace:
                raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
            return await self._post(
                path_template("/apis/intake/v2/workspaces/{workspace}/experiments", workspace=workspace),
                body=await async_maybe_transform(
                    {
                        "dataset_name": dataset_name,
                        "experiment_group_id": experiment_group_id,
                        "name": name,
                        "dataset_version": dataset_version,
                        "description": description,
                        "metadata": metadata,
                        "source_link": source_link,
                    },
                    experiment_create_params.ExperimentCreateParams,
                ),
                options=make_request_options(
                    extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
                ),
                cast_to=ExperimentResponse,
            )
        except ConflictError:
            if not exist_ok:
                raise
            return await self.retrieve(name = name, workspace = workspace)

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
    ) -> ExperimentResponse:
        """
        Get Experiment

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiments/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )

    async def update(
        self,
        path_name: str,
        *,
        workspace: str | None = None,
        dataset_name: str,
        experiment_group_id: str,
        body_name: str,
        dataset_version: str | Omit = omit,
        description: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        source_link: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentResponse:
        """
        Update Experiment

        Args:
          dataset_name: Producer-supplied dataset name.

          experiment_group_id: Entity id of the owning ExperimentGroup. Required — the group must already
              exist.

          body_name: Producer-supplied, workspace-unique experiment id.

          dataset_version: Producer-supplied dataset version.

          description: Human-readable description.

          metadata: Free-form producer metadata.

          source_link: Optional URL for the source experiment.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if workspace is None:
            workspace = self._client._get_workspace_path_param()
        if not workspace:
            raise ValueError(f"Expected a non-empty value for `workspace` but received {workspace!r}")
        if not path_name:
            raise ValueError(f"Expected a non-empty value for `path_name` but received {path_name!r}")
        return await self._put(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiments/{path_name}",
                workspace=workspace,
                path_name=path_name,
            ),
            body=await async_maybe_transform(
                {
                    "dataset_name": dataset_name,
                    "experiment_group_id": experiment_group_id,
                    "body_name": body_name,
                    "dataset_version": dataset_version,
                    "description": description,
                    "metadata": metadata,
                    "source_link": source_link,
                },
                experiment_update_params.ExperimentUpdateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: ExperimentFilterParam | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AsyncPaginator[ExperimentResponse, AsyncDefaultPagination[ExperimentResponse]]:
        """
        List Experiments

        Args:
          filter: Filter experiments by name, experiment_group_id, dataset_name, dataset_version,
              created_by, created_at, or updated_at. Pass is_deleted=true to return only
              soft-deleted experiments; omit to see only live ones. Pass is_pinned=true (or
              false) to filter by pinned state; omit to return both. Filter by a rollup metric
              with numeric range operators ($gte/$lte/$gt/$lt/$eq): filter[run_count][$gte]=5,
              filter[cost_usd.mean][$lte]=0.5, filter[latency_ms.p95][$lte]=1000, or
              filter[evaluators.<name>.mean][$gte]=0.8.

          page: Page number.

          page_size: Page size.

          sort: Field to sort by; prefix with '-' for descending. Sort by an experiment
              attribute (name, created_at, updated_at, pinned_at) or by an aggregate metric:
              run_count, cost_usd.<stat>, latency_ms.<stat>, or evaluators.<name>.<stat>,
              where <stat> is one of mean, median, p90, p95, p99, sum, count.

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiments", workspace=workspace),
            page=AsyncDefaultPagination[ExperimentResponse],
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
                    experiment_list_params.ExperimentListParams,
                ),
            ),
            model=ExperimentResponse,
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
        Delete Experiment

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiments/{name}", workspace=workspace, name=name),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=NoneType,
        )

    async def pin(
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
    ) -> ExperimentResponse:
        """
        Pin an experiment to the top of the list (workspace-shared).

        Re-pinning an already-pinned experiment refreshes `pinned_at` to the current
        timestamp, which is intentional (most-recently-pinned sorts first).

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
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiments/{name}/pin", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )

    async def unpin(
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
    ) -> ExperimentResponse:
        """Unpin an experiment.

        Idempotent: unpinning an already-unpinned experiment is a
        no-op.

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
        return await self._delete(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiments/{name}/pin", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentResponse,
        )


class ExperimentsResourceWithRawResponse:
    def __init__(self, experiments: ExperimentsResource) -> None:
        self._experiments = experiments

        self.create = to_raw_response_wrapper(
            experiments.create,
        )
        self.retrieve = to_raw_response_wrapper(
            experiments.retrieve,
        )
        self.update = to_raw_response_wrapper(
            experiments.update,
        )
        self.list = to_raw_response_wrapper(
            experiments.list,
        )
        self.delete = to_raw_response_wrapper(
            experiments.delete,
        )
        self.pin = to_raw_response_wrapper(
            experiments.pin,
        )
        self.unpin = to_raw_response_wrapper(
            experiments.unpin,
        )

    @cached_property
    def sessions(self) -> SessionsResourceWithRawResponse:
        return SessionsResourceWithRawResponse(self._experiments.sessions)


class AsyncExperimentsResourceWithRawResponse:
    def __init__(self, experiments: AsyncExperimentsResource) -> None:
        self._experiments = experiments

        self.create = async_to_raw_response_wrapper(
            experiments.create,
        )
        self.retrieve = async_to_raw_response_wrapper(
            experiments.retrieve,
        )
        self.update = async_to_raw_response_wrapper(
            experiments.update,
        )
        self.list = async_to_raw_response_wrapper(
            experiments.list,
        )
        self.delete = async_to_raw_response_wrapper(
            experiments.delete,
        )
        self.pin = async_to_raw_response_wrapper(
            experiments.pin,
        )
        self.unpin = async_to_raw_response_wrapper(
            experiments.unpin,
        )

    @cached_property
    def sessions(self) -> AsyncSessionsResourceWithRawResponse:
        return AsyncSessionsResourceWithRawResponse(self._experiments.sessions)


class ExperimentsResourceWithStreamingResponse:
    def __init__(self, experiments: ExperimentsResource) -> None:
        self._experiments = experiments

        self.create = to_streamed_response_wrapper(
            experiments.create,
        )
        self.retrieve = to_streamed_response_wrapper(
            experiments.retrieve,
        )
        self.update = to_streamed_response_wrapper(
            experiments.update,
        )
        self.list = to_streamed_response_wrapper(
            experiments.list,
        )
        self.delete = to_streamed_response_wrapper(
            experiments.delete,
        )
        self.pin = to_streamed_response_wrapper(
            experiments.pin,
        )
        self.unpin = to_streamed_response_wrapper(
            experiments.unpin,
        )

    @cached_property
    def sessions(self) -> SessionsResourceWithStreamingResponse:
        return SessionsResourceWithStreamingResponse(self._experiments.sessions)


class AsyncExperimentsResourceWithStreamingResponse:
    def __init__(self, experiments: AsyncExperimentsResource) -> None:
        self._experiments = experiments

        self.create = async_to_streamed_response_wrapper(
            experiments.create,
        )
        self.retrieve = async_to_streamed_response_wrapper(
            experiments.retrieve,
        )
        self.update = async_to_streamed_response_wrapper(
            experiments.update,
        )
        self.list = async_to_streamed_response_wrapper(
            experiments.list,
        )
        self.delete = async_to_streamed_response_wrapper(
            experiments.delete,
        )
        self.pin = async_to_streamed_response_wrapper(
            experiments.pin,
        )
        self.unpin = async_to_streamed_response_wrapper(
            experiments.unpin,
        )

    @cached_property
    def sessions(self) -> AsyncSessionsResourceWithStreamingResponse:
        return AsyncSessionsResourceWithStreamingResponse(self._experiments.sessions)
