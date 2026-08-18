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

from typing import Optional

import httpx

from ..._types import Body, Omit, Query, Headers, NotGiven, omit, not_given
from ..._utils import path_template, maybe_transform, async_maybe_transform
from ..._compat import cached_property
from ..._resource import SyncAPIResource, AsyncAPIResource
from ..._response import (
    to_raw_response_wrapper,
    to_streamed_response_wrapper,
    async_to_raw_response_wrapper,
    async_to_streamed_response_wrapper,
)
from ..._base_client import make_request_options
from ...types.access_keys import access_key_list_params, access_key_create_params
from ...types.access_keys.access_key_list_response import AccessKeyListResponse
from ...types.access_keys.access_key_create_response import AccessKeyCreateResponse
from ...types.access_keys.access_key_revoke_response import AccessKeyRevokeResponse

__all__ = ["AccessKeysResource", "AsyncAccessKeysResource"]


class AccessKeysResource(SyncAPIResource):
    @cached_property
    def with_raw_response(self) -> AccessKeysResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return AccessKeysResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> AccessKeysResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return AccessKeysResourceWithStreamingResponse(self)

    def create(
        self,
        *,
        description: Optional[str] | Omit = omit,
        expires_in_seconds: Optional[int] | Omit = omit,
        name: Optional[str] | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AccessKeyCreateResponse:
        """
        Create Access Key

        Args:
          description: Optional human-readable description of the Scoped Access Key.

          expires_in_seconds: Scoped Access Key lifetime in seconds. Omit to use
              auth.access_keys.default_expires_in_seconds. Send explicit null to request a
              non-time-delimited key, which requires auth.access_keys.max_expires_in_seconds
              to be disabled.

          name: Optional human-readable Scoped Access Key label. The token jti remains the
              stable identifier.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        return self._post(
            "/apis/auth/v2/access-keys",
            body=maybe_transform(
                {
                    "description": description,
                    "expires_in_seconds": expires_in_seconds,
                    "name": name,
                },
                access_key_create_params.AccessKeyCreateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=AccessKeyCreateResponse,
        )

    def list(
        self,
        *,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AccessKeyListResponse:
        """
        List Access Keys

        Args:
          page: Page number to retrieve.

          page_size: Number of keys to retrieve per page.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        return self._get(
            "/apis/auth/v2/access-keys",
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                query=maybe_transform(
                    {
                        "page": page,
                        "page_size": page_size,
                    },
                    access_key_list_params.AccessKeyListParams,
                ),
            ),
            cast_to=AccessKeyListResponse,
        )

    def delete(
        self,
        jti: str,
        *,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AccessKeyRevokeResponse:
        """
        Revoke Access Key

        Args:
          jti: Stable JWT ID of the Scoped Access Key to revoke.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if not jti:
            raise ValueError(f"Expected a non-empty value for `jti` but received {jti!r}")
        return self._delete(
            path_template("/apis/auth/v2/access-keys/{jti}", jti=jti),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=AccessKeyRevokeResponse,
        )


class AsyncAccessKeysResource(AsyncAPIResource):
    @cached_property
    def with_raw_response(self) -> AsyncAccessKeysResourceWithRawResponse:
        """
        This property can be used as a prefix for any HTTP method call to return
        the raw response object instead of the parsed content.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#accessing-raw-response-data-e-g-headers
        """
        return AsyncAccessKeysResourceWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> AsyncAccessKeysResourceWithStreamingResponse:
        """
        An alternative to `.with_raw_response` that doesn't eagerly read the response body.

        For more information, see https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#with_streaming_response
        """
        return AsyncAccessKeysResourceWithStreamingResponse(self)

    async def create(
        self,
        *,
        description: Optional[str] | Omit = omit,
        expires_in_seconds: Optional[int] | Omit = omit,
        name: Optional[str] | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AccessKeyCreateResponse:
        """
        Create Access Key

        Args:
          description: Optional human-readable description of the Scoped Access Key.

          expires_in_seconds: Scoped Access Key lifetime in seconds. Omit to use
              auth.access_keys.default_expires_in_seconds. Send explicit null to request a
              non-time-delimited key, which requires auth.access_keys.max_expires_in_seconds
              to be disabled.

          name: Optional human-readable Scoped Access Key label. The token jti remains the
              stable identifier.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        return await self._post(
            "/apis/auth/v2/access-keys",
            body=await async_maybe_transform(
                {
                    "description": description,
                    "expires_in_seconds": expires_in_seconds,
                    "name": name,
                },
                access_key_create_params.AccessKeyCreateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=AccessKeyCreateResponse,
        )

    async def list(
        self,
        *,
        page: int | Omit = omit,
        page_size: int | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AccessKeyListResponse:
        """
        List Access Keys

        Args:
          page: Page number to retrieve.

          page_size: Number of keys to retrieve per page.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        return await self._get(
            "/apis/auth/v2/access-keys",
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                query=await async_maybe_transform(
                    {
                        "page": page,
                        "page_size": page_size,
                    },
                    access_key_list_params.AccessKeyListParams,
                ),
            ),
            cast_to=AccessKeyListResponse,
        )

    async def delete(
        self,
        jti: str,
        *,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,
    ) -> AccessKeyRevokeResponse:
        """
        Revoke Access Key

        Args:
          jti: Stable JWT ID of the Scoped Access Key to revoke.

          extra_headers: Send extra headers

          extra_query: Add additional query parameters to the request

          extra_body: Add additional JSON properties to the request

          timeout: Override the client-level default timeout for this request, in seconds
        """
        if not jti:
            raise ValueError(f"Expected a non-empty value for `jti` but received {jti!r}")
        return await self._delete(
            path_template("/apis/auth/v2/access-keys/{jti}", jti=jti),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=AccessKeyRevokeResponse,
        )


class AccessKeysResourceWithRawResponse:
    def __init__(self, access_keys: AccessKeysResource) -> None:
        self._access_keys = access_keys

        self.create = to_raw_response_wrapper(
            access_keys.create,
        )
        self.list = to_raw_response_wrapper(
            access_keys.list,
        )
        self.delete = to_raw_response_wrapper(
            access_keys.delete,
        )


class AsyncAccessKeysResourceWithRawResponse:
    def __init__(self, access_keys: AsyncAccessKeysResource) -> None:
        self._access_keys = access_keys

        self.create = async_to_raw_response_wrapper(
            access_keys.create,
        )
        self.list = async_to_raw_response_wrapper(
            access_keys.list,
        )
        self.delete = async_to_raw_response_wrapper(
            access_keys.delete,
        )


class AccessKeysResourceWithStreamingResponse:
    def __init__(self, access_keys: AccessKeysResource) -> None:
        self._access_keys = access_keys

        self.create = to_streamed_response_wrapper(
            access_keys.create,
        )
        self.list = to_streamed_response_wrapper(
            access_keys.list,
        )
        self.delete = to_streamed_response_wrapper(
            access_keys.delete,
        )


class AsyncAccessKeysResourceWithStreamingResponse:
    def __init__(self, access_keys: AsyncAccessKeysResource) -> None:
        self._access_keys = access_keys

        self.create = async_to_streamed_response_wrapper(
            access_keys.create,
        )
        self.list = async_to_streamed_response_wrapper(
            access_keys.list,
        )
        self.delete = async_to_streamed_response_wrapper(
            access_keys.delete,
        )
