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

import httpx

from ..._types import Body, Query, Headers, NotGiven, not_given
from ..._utils import path_template
from ..._compat import cached_property
from ..._resource import SyncAPIResource, AsyncAPIResource
from ..._response import (
    to_raw_response_wrapper,
    to_streamed_response_wrapper,
    async_to_raw_response_wrapper,
    async_to_streamed_response_wrapper,
)
from ..._base_client import make_request_options
from ...types.evaluations.evaluation_response import EvaluationResponse

__all__ = ["ExperimentsResource", "AsyncExperimentsResource"]


class ExperimentsResource(SyncAPIResource):
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

    def reviewme_create(
        self,
        experiment_id: str,
        *,
        workspace: str | None = None,
        name: str,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> EvaluationResponse:
        """
        Add an evaluation to an Experiment so it appears on that experiment's board.

        Curates an existing run into another comparison experiment (e.g. an
        all-benchmarks view). The experiment must exist and be live. Idempotent: adding
        an experiment the evaluation already belongs to is a no-op.

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
        if not experiment_id:
            raise ValueError(f"Expected a non-empty value for `experiment_id` but received {experiment_id!r}")
        return self._post(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/evaluations/{name}/experiments/{experiment_id}",
                workspace=workspace,
                name=name,
                experiment_id=experiment_id,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=EvaluationResponse,
        )

    def reviewme_delete(
        self,
        experiment_id: str,
        *,
        workspace: str | None = None,
        name: str,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> EvaluationResponse:
        """
        Remove an evaluation from an Experiment.

        Preserves the >=1-experiment invariant: removing the evaluation's _last_
        experiment is rejected with 409 — delete the evaluation instead. Idempotent:
        removing an experiment the evaluation isn't in is a no-op.

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
        if not experiment_id:
            raise ValueError(f"Expected a non-empty value for `experiment_id` but received {experiment_id!r}")
        return self._delete(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/evaluations/{name}/experiments/{experiment_id}",
                workspace=workspace,
                name=name,
                experiment_id=experiment_id,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=EvaluationResponse,
        )


class AsyncExperimentsResource(AsyncAPIResource):
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

    async def reviewme_create(
        self,
        experiment_id: str,
        *,
        workspace: str | None = None,
        name: str,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> EvaluationResponse:
        """
        Add an evaluation to an Experiment so it appears on that experiment's board.

        Curates an existing run into another comparison experiment (e.g. an
        all-benchmarks view). The experiment must exist and be live. Idempotent: adding
        an experiment the evaluation already belongs to is a no-op.

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
        if not experiment_id:
            raise ValueError(f"Expected a non-empty value for `experiment_id` but received {experiment_id!r}")
        return await self._post(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/evaluations/{name}/experiments/{experiment_id}",
                workspace=workspace,
                name=name,
                experiment_id=experiment_id,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=EvaluationResponse,
        )

    async def reviewme_delete(
        self,
        experiment_id: str,
        *,
        workspace: str | None = None,
        name: str,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> EvaluationResponse:
        """
        Remove an evaluation from an Experiment.

        Preserves the >=1-experiment invariant: removing the evaluation's _last_
        experiment is rejected with 409 — delete the evaluation instead. Idempotent:
        removing an experiment the evaluation isn't in is a no-op.

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
        if not experiment_id:
            raise ValueError(f"Expected a non-empty value for `experiment_id` but received {experiment_id!r}")
        return await self._delete(
            path_template(
                "/apis/intake/v2/workspaces/{workspace}/evaluations/{name}/experiments/{experiment_id}",
                workspace=workspace,
                name=name,
                experiment_id=experiment_id,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=EvaluationResponse,
        )


class ExperimentsResourceWithRawResponse:
    def __init__(self, experiments: ExperimentsResource) -> None:
        self._experiments = experiments

        self.reviewme_create = to_raw_response_wrapper(
            experiments.reviewme_create,
        )
        self.reviewme_delete = to_raw_response_wrapper(
            experiments.reviewme_delete,
        )


class AsyncExperimentsResourceWithRawResponse:
    def __init__(self, experiments: AsyncExperimentsResource) -> None:
        self._experiments = experiments

        self.reviewme_create = async_to_raw_response_wrapper(
            experiments.reviewme_create,
        )
        self.reviewme_delete = async_to_raw_response_wrapper(
            experiments.reviewme_delete,
        )


class ExperimentsResourceWithStreamingResponse:
    def __init__(self, experiments: ExperimentsResource) -> None:
        self._experiments = experiments

        self.reviewme_create = to_streamed_response_wrapper(
            experiments.reviewme_create,
        )
        self.reviewme_delete = to_streamed_response_wrapper(
            experiments.reviewme_delete,
        )


class AsyncExperimentsResourceWithStreamingResponse:
    def __init__(self, experiments: AsyncExperimentsResource) -> None:
        self._experiments = experiments

        self.reviewme_create = async_to_streamed_response_wrapper(
            experiments.reviewme_create,
        )
        self.reviewme_delete = async_to_streamed_response_wrapper(
            experiments.reviewme_delete,
        )
