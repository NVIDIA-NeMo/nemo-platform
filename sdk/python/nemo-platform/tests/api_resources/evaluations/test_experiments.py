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
from nemo_platform.types.evaluations import EvaluationResponse

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestExperiments:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_add(self, client: NeMoPlatform) -> None:
        experiment = client.evaluations.experiments.add(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_add(self, client: NeMoPlatform) -> None:
        response = client.evaluations.experiments.with_raw_response.add(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment = response.parse()
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_add(self, client: NeMoPlatform) -> None:
        with client.evaluations.experiments.with_streaming_response.add(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment = response.parse()
            assert_matches_type(EvaluationResponse, experiment, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_add(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluations.experiments.with_raw_response.add(
                experiment_id="experiment_id",
                workspace="",
                name="name",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluations.experiments.with_raw_response.add(
                experiment_id="experiment_id",
                workspace="workspace",
                name="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `experiment_id` but received ''"):
            client.evaluations.experiments.with_raw_response.add(
                experiment_id="",
                workspace="workspace",
                name="name",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_remove(self, client: NeMoPlatform) -> None:
        experiment = client.evaluations.experiments.remove(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_remove(self, client: NeMoPlatform) -> None:
        response = client.evaluations.experiments.with_raw_response.remove(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment = response.parse()
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_remove(self, client: NeMoPlatform) -> None:
        with client.evaluations.experiments.with_streaming_response.remove(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment = response.parse()
            assert_matches_type(EvaluationResponse, experiment, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_remove(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluations.experiments.with_raw_response.remove(
                experiment_id="experiment_id",
                workspace="",
                name="name",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluations.experiments.with_raw_response.remove(
                experiment_id="experiment_id",
                workspace="workspace",
                name="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `experiment_id` but received ''"):
            client.evaluations.experiments.with_raw_response.remove(
                experiment_id="",
                workspace="workspace",
                name="name",
            )


class TestAsyncExperiments:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_add(self, async_client: AsyncNeMoPlatform) -> None:
        experiment = await async_client.evaluations.experiments.add(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_add(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluations.experiments.with_raw_response.add(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment = await response.parse()
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_add(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluations.experiments.with_streaming_response.add(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment = await response.parse()
            assert_matches_type(EvaluationResponse, experiment, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_add(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluations.experiments.with_raw_response.add(
                experiment_id="experiment_id",
                workspace="",
                name="name",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluations.experiments.with_raw_response.add(
                experiment_id="experiment_id",
                workspace="workspace",
                name="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `experiment_id` but received ''"):
            await async_client.evaluations.experiments.with_raw_response.add(
                experiment_id="",
                workspace="workspace",
                name="name",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_remove(self, async_client: AsyncNeMoPlatform) -> None:
        experiment = await async_client.evaluations.experiments.remove(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_remove(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluations.experiments.with_raw_response.remove(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        experiment = await response.parse()
        assert_matches_type(EvaluationResponse, experiment, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_remove(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluations.experiments.with_streaming_response.remove(
            experiment_id="experiment_id",
            workspace="workspace",
            name="name",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            experiment = await response.parse()
            assert_matches_type(EvaluationResponse, experiment, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_remove(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluations.experiments.with_raw_response.remove(
                experiment_id="experiment_id",
                workspace="",
                name="name",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluations.experiments.with_raw_response.remove(
                experiment_id="experiment_id",
                workspace="workspace",
                name="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `experiment_id` but received ''"):
            await async_client.evaluations.experiments.with_raw_response.remove(
                experiment_id="",
                workspace="workspace",
                name="name",
            )
