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
from typing_extensions import Literal

import httpx

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
from ...pagination import SyncDefaultPagination, AsyncDefaultPagination
from ..._base_client import AsyncPaginator, make_request_options
from ...types.experiment_groups import (
    experiment_group_list_params,
    experiment_group_create_params,
    experiment_group_update_params,
)
from ...types.experiment_groups.experiment_group_response import ExperimentGroupResponse
from ...types.experiment_groups.experiment_group_filter_param import ExperimentGroupFilterParam
from ..._exceptions import ConflictError

__all__ = ["ExperimentGroupsResource", "AsyncExperimentGroupsResource"]


class ExperimentGroupsResource(SyncAPIResource):
    @cached_property
    def with_raw_response(self) -> ExperimentGroupsResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return ExperimentGroupsResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> ExperimentGroupsResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return ExperimentGroupsResourceWithStreamingResponse(self)

    def create(
        self,
        *,
        workspace: str | None = None,
        name: str,
        default_sort: str | Omit = omit,
        description: str | Omit = omit,
        insight_id: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        summary: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        exist_ok: bool = False,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentGroupResponse:
        """
        Create Experiment Group

        Args:
          name: Workspace-unique group name.

          default_sort: Default sort for this group's experiments list, as a `sort`-param string
              (leading '-' = descending); defaults to '-created_at'. Accepts any field the
              experiments list `sort` param does; clients apply it as the list `sort` param.

          description: Human-readable purpose of the group.

          insight_id: Reference to an external insight that seeded this group, if any.

          metadata: Free-form producer metadata for the group.

          summary: Human- or agent-authored summary of the group's findings.


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
                path_template("/apis/intake/v2/workspaces/{workspace}/experiment-groups", workspace=workspace),
                body=maybe_transform(
                    {
                        "name": name,
                        "default_sort": default_sort,
                        "description": description,
                        "insight_id": insight_id,
                        "metadata": metadata,
                        "summary": summary,
                    },
                    experiment_group_create_params.ExperimentGroupCreateParams,
                ),
                options=make_request_options(
                    extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
                ),
                cast_to=ExperimentGroupResponse,
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
    ) -> ExperimentGroupResponse:
        """
        Get Experiment Group

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
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentGroupResponse,
        )

    def update(
        self,
        path_name: str,
        *,
        workspace: str | None = None,
        body_name: str,
        default_sort: str | Omit = omit,
        description: str | Omit = omit,
        insight_id: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        summary: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentGroupResponse:
        """
        Update Experiment Group

        Args:
          body_name: Workspace-unique group name.

          default_sort: Default sort for this group's experiments list, as a `sort`-param string
              (leading '-' = descending); defaults to '-created_at'. Accepts any field the
              experiments list `sort` param does; clients apply it as the list `sort` param.

          description: Human-readable purpose of the group.

          insight_id: Reference to an external insight that seeded this group, if any.

          metadata: Free-form producer metadata for the group.

          summary: Human- or agent-authored summary of the group's findings.

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
                "/apis/intake/v2/workspaces/{workspace}/experiment-groups/{path_name}",
                workspace=workspace,
                path_name=path_name,
            ),
            body=maybe_transform(
                {
                    "body_name": body_name,
                    "default_sort": default_sort,
                    "description": description,
                    "insight_id": insight_id,
                    "metadata": metadata,
                    "summary": summary,
                },
                experiment_group_update_params.ExperimentGroupUpdateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentGroupResponse,
        )

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: ExperimentGroupFilterParam | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"] | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> SyncDefaultPagination[ExperimentGroupResponse]:
        """
        List Experiment Groups

        Args:
          filter: Filter experiment groups by name.

          page: Page number.

          page_size: Page size.

          sort: Sort field; prefix with '-' for descending.

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiment-groups", workspace=workspace),
            page=SyncDefaultPagination[ExperimentGroupResponse],
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
                    experiment_group_list_params.ExperimentGroupListParams,
                ),
            ),
            model=ExperimentGroupResponse,
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
        Delete Experiment Group

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
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=NoneType,
        )


class AsyncExperimentGroupsResource(AsyncAPIResource):
    @cached_property
    def with_raw_response(self) -> AsyncExperimentGroupsResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return AsyncExperimentGroupsResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> AsyncExperimentGroupsResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return AsyncExperimentGroupsResourceWithStreamingResponse(self)

    async def create(
        self,
        *,
        workspace: str | None = None,
        name: str,
        default_sort: str | Omit = omit,
        description: str | Omit = omit,
        insight_id: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        summary: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        exist_ok: bool = False,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentGroupResponse:
        """
        Create Experiment Group

        Args:
          name: Workspace-unique group name.

          default_sort: Default sort for this group's experiments list, as a `sort`-param string
              (leading '-' = descending); defaults to '-created_at'. Accepts any field the
              experiments list `sort` param does; clients apply it as the list `sort` param.

          description: Human-readable purpose of the group.

          insight_id: Reference to an external insight that seeded this group, if any.

          metadata: Free-form producer metadata for the group.

          summary: Human- or agent-authored summary of the group's findings.


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
                path_template("/apis/intake/v2/workspaces/{workspace}/experiment-groups", workspace=workspace),
                body=await async_maybe_transform(
                    {
                        "name": name,
                        "default_sort": default_sort,
                        "description": description,
                        "insight_id": insight_id,
                        "metadata": metadata,
                        "summary": summary,
                    },
                    experiment_group_create_params.ExperimentGroupCreateParams,
                ),
                options=make_request_options(
                    extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
                ),
                cast_to=ExperimentGroupResponse,
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
    ) -> ExperimentGroupResponse:
        """
        Get Experiment Group

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
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentGroupResponse,
        )

    async def update(
        self,
        path_name: str,
        *,
        workspace: str | None = None,
        body_name: str,
        default_sort: str | Omit = omit,
        description: str | Omit = omit,
        insight_id: str | Omit = omit,
        metadata: Dict[str, object] | Omit = omit,
        summary: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> ExperimentGroupResponse:
        """
        Update Experiment Group

        Args:
          body_name: Workspace-unique group name.

          default_sort: Default sort for this group's experiments list, as a `sort`-param string
              (leading '-' = descending); defaults to '-created_at'. Accepts any field the
              experiments list `sort` param does; clients apply it as the list `sort` param.

          description: Human-readable purpose of the group.

          insight_id: Reference to an external insight that seeded this group, if any.

          metadata: Free-form producer metadata for the group.

          summary: Human- or agent-authored summary of the group's findings.

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
                "/apis/intake/v2/workspaces/{workspace}/experiment-groups/{path_name}",
                workspace=workspace,
                path_name=path_name,
            ),
            body=await async_maybe_transform(
                {
                    "body_name": body_name,
                    "default_sort": default_sort,
                    "description": description,
                    "insight_id": insight_id,
                    "metadata": metadata,
                    "summary": summary,
                },
                experiment_group_update_params.ExperimentGroupUpdateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ExperimentGroupResponse,
        )

    def list(
        self,
        *,
        workspace: str | None = None,
        filter: ExperimentGroupFilterParam | Omit = omit,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        sort: Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"] | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AsyncPaginator[ExperimentGroupResponse, AsyncDefaultPagination[ExperimentGroupResponse]]:
        """
        List Experiment Groups

        Args:
          filter: Filter experiment groups by name.

          page: Page number.

          page_size: Page size.

          sort: Sort field; prefix with '-' for descending.

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
            path_template("/apis/intake/v2/workspaces/{workspace}/experiment-groups", workspace=workspace),
            page=AsyncDefaultPagination[ExperimentGroupResponse],
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
                    experiment_group_list_params.ExperimentGroupListParams,
                ),
            ),
            model=ExperimentGroupResponse,
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
        Delete Experiment Group

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
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}", workspace=workspace, name=name
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=NoneType,
        )


class ExperimentGroupsResourceWithRawResponse:
    def __init__(self, experiment_groups: ExperimentGroupsResource) -> None:
        self._experiment_groups = experiment_groups

        self.create = to_raw_response_wrapper(
            experiment_groups.create,
        )
        self.retrieve = to_raw_response_wrapper(
            experiment_groups.retrieve,
        )
        self.update = to_raw_response_wrapper(
            experiment_groups.update,
        )
        self.list = to_raw_response_wrapper(
            experiment_groups.list,
        )
        self.delete = to_raw_response_wrapper(
            experiment_groups.delete,
        )


class AsyncExperimentGroupsResourceWithRawResponse:
    def __init__(self, experiment_groups: AsyncExperimentGroupsResource) -> None:
        self._experiment_groups = experiment_groups

        self.create = async_to_raw_response_wrapper(
            experiment_groups.create,
        )
        self.retrieve = async_to_raw_response_wrapper(
            experiment_groups.retrieve,
        )
        self.update = async_to_raw_response_wrapper(
            experiment_groups.update,
        )
        self.list = async_to_raw_response_wrapper(
            experiment_groups.list,
        )
        self.delete = async_to_raw_response_wrapper(
            experiment_groups.delete,
        )


class ExperimentGroupsResourceWithStreamingResponse:
    def __init__(self, experiment_groups: ExperimentGroupsResource) -> None:
        self._experiment_groups = experiment_groups

        self.create = to_streamed_response_wrapper(
            experiment_groups.create,
        )
        self.retrieve = to_streamed_response_wrapper(
            experiment_groups.retrieve,
        )
        self.update = to_streamed_response_wrapper(
            experiment_groups.update,
        )
        self.list = to_streamed_response_wrapper(
            experiment_groups.list,
        )
        self.delete = to_streamed_response_wrapper(
            experiment_groups.delete,
        )


class AsyncExperimentGroupsResourceWithStreamingResponse:
    def __init__(self, experiment_groups: AsyncExperimentGroupsResource) -> None:
        self._experiment_groups = experiment_groups

        self.create = async_to_streamed_response_wrapper(
            experiment_groups.create,
        )
        self.retrieve = async_to_streamed_response_wrapper(
            experiment_groups.retrieve,
        )
        self.update = async_to_streamed_response_wrapper(
            experiment_groups.update,
        )
        self.list = async_to_streamed_response_wrapper(
            experiment_groups.list,
        )
        self.delete = async_to_streamed_response_wrapper(
            experiment_groups.delete,
        )
