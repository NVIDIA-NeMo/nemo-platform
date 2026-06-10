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
from nemo_platform._utils import parse_datetime
from nemo_platform.types.iam import (
    RoleBinding,
)
from nemo_platform.pagination import SyncDefaultPagination, AsyncDefaultPagination
from nemo_platform.types.shared import DeleteResponse

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestRoleBindings:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create(self, client: NeMoPlatform) -> None:
        role_binding = client.iam.role_bindings.create(
            principal="principal",
            role="role",
        )
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params(self, client: NeMoPlatform) -> None:
        role_binding = client.iam.role_bindings.create(
            principal="principal",
            role="role",
            wait_role_propagation=True,
            workspace="workspace",
        )
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create(self, client: NeMoPlatform) -> None:
        response = client.iam.role_bindings.with_raw_response.create(
            principal="principal",
            role="role",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = response.parse()
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create(self, client: NeMoPlatform) -> None:
        with client.iam.role_bindings.with_streaming_response.create(
            principal="principal",
            role="role",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = response.parse()
            assert_matches_type(RoleBinding, role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_retrieve(self, client: NeMoPlatform) -> None:
        role_binding = client.iam.role_bindings.retrieve(
            "name",
        )
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_retrieve(self, client: NeMoPlatform) -> None:
        response = client.iam.role_bindings.with_raw_response.retrieve(
            "name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = response.parse()
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_retrieve(self, client: NeMoPlatform) -> None:
        with client.iam.role_bindings.with_streaming_response.retrieve(
            "name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = response.parse()
            assert_matches_type(RoleBinding, role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_retrieve(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.iam.role_bindings.with_raw_response.retrieve(
                "",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list(self, client: NeMoPlatform) -> None:
        role_binding = client.iam.role_bindings.list()
        assert_matches_type(SyncDefaultPagination[RoleBinding], role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list_with_all_params(self, client: NeMoPlatform) -> None:
        role_binding = client.iam.role_bindings.list(
            filter={
                "granted_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "granted_by": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "is_active": True,
                "principal": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "revoked_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "role": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "workspace": "workspace",
            },
            page=0,
            page_size=0,
            sort="sort",
        )
        assert_matches_type(SyncDefaultPagination[RoleBinding], role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_list(self, client: NeMoPlatform) -> None:
        response = client.iam.role_bindings.with_raw_response.list()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = response.parse()
        assert_matches_type(SyncDefaultPagination[RoleBinding], role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_list(self, client: NeMoPlatform) -> None:
        with client.iam.role_bindings.with_streaming_response.list() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = response.parse()
            assert_matches_type(SyncDefaultPagination[RoleBinding], role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_delete(self, client: NeMoPlatform) -> None:
        role_binding = client.iam.role_bindings.delete(
            name="name",
        )
        assert_matches_type(DeleteResponse, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_delete_with_all_params(self, client: NeMoPlatform) -> None:
        role_binding = client.iam.role_bindings.delete(
            name="name",
            wait_role_propagation=True,
        )
        assert_matches_type(DeleteResponse, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_delete(self, client: NeMoPlatform) -> None:
        response = client.iam.role_bindings.with_raw_response.delete(
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = response.parse()
        assert_matches_type(DeleteResponse, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_delete(self, client: NeMoPlatform) -> None:
        with client.iam.role_bindings.with_streaming_response.delete(
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = response.parse()
            assert_matches_type(DeleteResponse, role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_delete(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.iam.role_bindings.with_raw_response.delete(
                name="",
            )


class TestAsyncRoleBindings:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create(self, async_client: AsyncNeMoPlatform) -> None:
        role_binding = await async_client.iam.role_bindings.create(
            principal="principal",
            role="role",
        )
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        role_binding = await async_client.iam.role_bindings.create(
            principal="principal",
            role="role",
            wait_role_propagation=True,
            workspace="workspace",
        )
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.iam.role_bindings.with_raw_response.create(
            principal="principal",
            role="role",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = await response.parse()
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.iam.role_bindings.with_streaming_response.create(
            principal="principal",
            role="role",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = await response.parse()
            assert_matches_type(RoleBinding, role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        role_binding = await async_client.iam.role_bindings.retrieve(
            "name",
        )
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.iam.role_bindings.with_raw_response.retrieve(
            "name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = await response.parse()
        assert_matches_type(RoleBinding, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.iam.role_bindings.with_streaming_response.retrieve(
            "name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = await response.parse()
            assert_matches_type(RoleBinding, role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.iam.role_bindings.with_raw_response.retrieve(
                "",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list(self, async_client: AsyncNeMoPlatform) -> None:
        role_binding = await async_client.iam.role_bindings.list()
        assert_matches_type(AsyncDefaultPagination[RoleBinding], role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        role_binding = await async_client.iam.role_bindings.list(
            filter={
                "granted_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "granted_by": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "is_active": True,
                "principal": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "revoked_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "role": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "workspace": "workspace",
            },
            page=0,
            page_size=0,
            sort="sort",
        )
        assert_matches_type(AsyncDefaultPagination[RoleBinding], role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.iam.role_bindings.with_raw_response.list()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = await response.parse()
        assert_matches_type(AsyncDefaultPagination[RoleBinding], role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.iam.role_bindings.with_streaming_response.list() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = await response.parse()
            assert_matches_type(AsyncDefaultPagination[RoleBinding], role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_delete(self, async_client: AsyncNeMoPlatform) -> None:
        role_binding = await async_client.iam.role_bindings.delete(
            name="name",
        )
        assert_matches_type(DeleteResponse, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_delete_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        role_binding = await async_client.iam.role_bindings.delete(
            name="name",
            wait_role_propagation=True,
        )
        assert_matches_type(DeleteResponse, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.iam.role_bindings.with_raw_response.delete(
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        role_binding = await response.parse()
        assert_matches_type(DeleteResponse, role_binding, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.iam.role_bindings.with_streaming_response.delete(
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            role_binding = await response.parse()
            assert_matches_type(DeleteResponse, role_binding, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_delete(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.iam.role_bindings.with_raw_response.delete(
                name="",
            )
