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
from nemo_platform.pagination import SyncDefaultPagination, AsyncDefaultPagination
from nemo_platform.types.experiment_groups import (
    ExperimentGroupResponse,
)

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestExperimentGroups:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.create(
            workspace="workspace",
            name="name",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.create(
            workspace="workspace",
            name="name",
            description="description",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create(self, client: NeMoPlatform) -> None:
        response = client.experiment_groups.with_raw_response.create(
            workspace="workspace",
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = response.parse()
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create(self, client: NeMoPlatform) -> None:
        with client.experiment_groups.with_streaming_response.create(
            workspace="workspace",
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = response.parse()
            assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.experiment_groups.with_raw_response.create(
                workspace="",
                name="name",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_retrieve(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_retrieve(self, client: NeMoPlatform) -> None:
        response = client.experiment_groups.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = response.parse()
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_retrieve(self, client: NeMoPlatform) -> None:
        with client.experiment_groups.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = response.parse()
            assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_retrieve(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.experiment_groups.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.experiment_groups.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_update(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_update_with_all_params(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
            description="description",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_update(self, client: NeMoPlatform) -> None:
        response = client.experiment_groups.with_raw_response.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = response.parse()
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_update(self, client: NeMoPlatform) -> None:
        with client.experiment_groups.with_streaming_response.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = response.parse()
            assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_update(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.experiment_groups.with_raw_response.update(
                path_name="name",
                workspace="",
                body_name="name",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `path_name` but received ''"):
            client.experiment_groups.with_raw_response.update(
                path_name="",
                workspace="workspace",
                body_name="name",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.list(
            workspace="workspace",
        )
        assert_matches_type(SyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list_with_all_params(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.list(
            workspace="workspace",
            filter={
                "is_deleted": True,
                "name": "name",
            },
            page=1,
            page_size=1,
            sort="-created_at",
        )
        assert_matches_type(SyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_list(self, client: NeMoPlatform) -> None:
        response = client.experiment_groups.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = response.parse()
        assert_matches_type(SyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_list(self, client: NeMoPlatform) -> None:
        with client.experiment_groups.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = response.parse()
            assert_matches_type(SyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_list(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.experiment_groups.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_delete(self, client: NeMoPlatform) -> None:
        experiment_group = client.experiment_groups.delete(
            name="name",
            workspace="workspace",
        )
        assert experiment_group is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_delete(self, client: NeMoPlatform) -> None:
        response = client.experiment_groups.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = response.parse()
        assert experiment_group is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_delete(self, client: NeMoPlatform) -> None:
        with client.experiment_groups.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = response.parse()
            assert experiment_group is None

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_delete(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.experiment_groups.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.experiment_groups.with_raw_response.delete(
                name="",
                workspace="workspace",
            )


class TestAsyncExperimentGroups:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.create(
            workspace="workspace",
            name="name",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.create(
            workspace="workspace",
            name="name",
            description="description",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.experiment_groups.with_raw_response.create(
            workspace="workspace",
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = await response.parse()
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.experiment_groups.with_streaming_response.create(
            workspace="workspace",
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = await response.parse()
            assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.experiment_groups.with_raw_response.create(
                workspace="",
                name="name",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.experiment_groups.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = await response.parse()
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.experiment_groups.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = await response.parse()
            assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.experiment_groups.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.experiment_groups.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_update(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_update_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
            description="description",
        )
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_update(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.experiment_groups.with_raw_response.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = await response.parse()
        assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_update(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.experiment_groups.with_streaming_response.update(
            path_name="name",
            workspace="workspace",
            body_name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = await response.parse()
            assert_matches_type(ExperimentGroupResponse, experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_update(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.experiment_groups.with_raw_response.update(
                path_name="name",
                workspace="",
                body_name="name",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `path_name` but received ''"):
            await async_client.experiment_groups.with_raw_response.update(
                path_name="",
                workspace="workspace",
                body_name="name",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.list(
            workspace="workspace",
        )
        assert_matches_type(AsyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.list(
            workspace="workspace",
            filter={
                "is_deleted": True,
                "name": "name",
            },
            page=1,
            page_size=1,
            sort="-created_at",
        )
        assert_matches_type(AsyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.experiment_groups.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = await response.parse()
        assert_matches_type(AsyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.experiment_groups.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = await response.parse()
            assert_matches_type(AsyncDefaultPagination[ExperimentGroupResponse], experiment_group, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_list(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.experiment_groups.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_delete(self, async_client: AsyncNeMoPlatform) -> None:
        experiment_group = await async_client.experiment_groups.delete(
            name="name",
            workspace="workspace",
        )
        assert experiment_group is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.experiment_groups.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment_group = await response.parse()
        assert experiment_group is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.experiment_groups.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment_group = await response.parse()
            assert experiment_group is None

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_delete(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.experiment_groups.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.experiment_groups.with_raw_response.delete(
                name="",
                workspace="workspace",
            )
