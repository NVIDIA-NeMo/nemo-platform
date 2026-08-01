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

import os
from typing import Any, cast

import pytest

from tests.utils import assert_matches_type
from nemo_platform import NeMoPlatform, AsyncNeMoPlatform
from nemo_platform.types.auth import AuthenticateResponse

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestAuth:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_authenticate(self, client: NeMoPlatform) -> None:
        auth = client.auth.authenticate()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_authenticate(self, client: NeMoPlatform) -> None:
        response = client.auth.with_raw_response.authenticate()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        auth = response.parse()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_authenticate(self, client: NeMoPlatform) -> None:
        with client.auth.with_streaming_response.authenticate() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            auth = response.parse()
            assert_matches_type(AuthenticateResponse, auth, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_authenticate_get(self, client: NeMoPlatform) -> None:
        auth = client.auth.authenticate_get()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_authenticate_get(self, client: NeMoPlatform) -> None:
        response = client.auth.with_raw_response.authenticate_get()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        auth = response.parse()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_authenticate_get(self, client: NeMoPlatform) -> None:
        with client.auth.with_streaming_response.authenticate_get() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            auth = response.parse()
            assert_matches_type(AuthenticateResponse, auth, path=["response"])

        assert cast(Any, response.is_closed) is True


class TestAsyncAuth:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_authenticate(self, async_client: AsyncNeMoPlatform) -> None:
        auth = await async_client.auth.authenticate()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_authenticate(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.auth.with_raw_response.authenticate()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        auth = await response.parse()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_authenticate(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.auth.with_streaming_response.authenticate() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            auth = await response.parse()
            assert_matches_type(AuthenticateResponse, auth, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_authenticate_get(self, async_client: AsyncNeMoPlatform) -> None:
        auth = await async_client.auth.authenticate_get()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_authenticate_get(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.auth.with_raw_response.authenticate_get()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        auth = await response.parse()
        assert_matches_type(AuthenticateResponse, auth, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_authenticate_get(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.auth.with_streaming_response.authenticate_get() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            auth = await response.parse()
            assert_matches_type(AuthenticateResponse, auth, path=["response"])

        assert cast(Any, response.is_closed) is True
