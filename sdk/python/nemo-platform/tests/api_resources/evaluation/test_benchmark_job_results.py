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
from nemo_platform.pagination import SyncDefaultPagination, AsyncDefaultPagination
from nemo_platform.types.shared import DeleteResponse
from nemo_platform.types.evaluation import (
    BenchmarkJobResult,
)

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestBenchmarkJobResults:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_retrieve(self, client: NeMoPlatform) -> None:
        benchmark_job_result = client.evaluation.benchmark_job_results.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_retrieve_with_all_params(self, client: NeMoPlatform) -> None:
        benchmark_job_result = client.evaluation.benchmark_job_results.retrieve(
            name="name",
            workspace="workspace",
            aggregate_fields=["nan_count"],
        )
        assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_retrieve(self, client: NeMoPlatform) -> None:
        response = client.evaluation.benchmark_job_results.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        benchmark_job_result = response.parse()
        assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_retrieve(self, client: NeMoPlatform) -> None:
        with client.evaluation.benchmark_job_results.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            benchmark_job_result = response.parse()
            assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_retrieve(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.benchmark_job_results.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.benchmark_job_results.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list(self, client: NeMoPlatform) -> None:
        benchmark_job_result = client.evaluation.benchmark_job_results.list(
            workspace="workspace",
        )
        assert_matches_type(SyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list_with_all_params(self, client: NeMoPlatform) -> None:
        benchmark_job_result = client.evaluation.benchmark_job_results.list(
            workspace="workspace",
            aggregate_fields=["nan_count"],
            filter={
                "benchmark": "workspace/benchmark-name",
                "created_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "dataset": "string",
                "metrics": "metrics",
                "model": "workspace/model_name",
                "name": "name",
            },
            page=0,
            page_size=0,
            sort="-created_at",
        )
        assert_matches_type(SyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_list(self, client: NeMoPlatform) -> None:
        response = client.evaluation.benchmark_job_results.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        benchmark_job_result = response.parse()
        assert_matches_type(SyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_list(self, client: NeMoPlatform) -> None:
        with client.evaluation.benchmark_job_results.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            benchmark_job_result = response.parse()
            assert_matches_type(SyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_list(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.benchmark_job_results.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_delete(self, client: NeMoPlatform) -> None:
        benchmark_job_result = client.evaluation.benchmark_job_results.delete(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(DeleteResponse, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_delete(self, client: NeMoPlatform) -> None:
        response = client.evaluation.benchmark_job_results.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        benchmark_job_result = response.parse()
        assert_matches_type(DeleteResponse, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_delete(self, client: NeMoPlatform) -> None:
        with client.evaluation.benchmark_job_results.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            benchmark_job_result = response.parse()
            assert_matches_type(DeleteResponse, benchmark_job_result, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_delete(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.benchmark_job_results.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.benchmark_job_results.with_raw_response.delete(
                name="",
                workspace="workspace",
            )


class TestAsyncBenchmarkJobResults:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        benchmark_job_result = await async_client.evaluation.benchmark_job_results.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_retrieve_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        benchmark_job_result = await async_client.evaluation.benchmark_job_results.retrieve(
            name="name",
            workspace="workspace",
            aggregate_fields=["nan_count"],
        )
        assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.benchmark_job_results.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        benchmark_job_result = await response.parse()
        assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.benchmark_job_results.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            benchmark_job_result = await response.parse()
            assert_matches_type(BenchmarkJobResult, benchmark_job_result, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.benchmark_job_results.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.benchmark_job_results.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list(self, async_client: AsyncNeMoPlatform) -> None:
        benchmark_job_result = await async_client.evaluation.benchmark_job_results.list(
            workspace="workspace",
        )
        assert_matches_type(AsyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        benchmark_job_result = await async_client.evaluation.benchmark_job_results.list(
            workspace="workspace",
            aggregate_fields=["nan_count"],
            filter={
                "benchmark": "workspace/benchmark-name",
                "created_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "dataset": "string",
                "metrics": "metrics",
                "model": "workspace/model_name",
                "name": "name",
            },
            page=0,
            page_size=0,
            sort="-created_at",
        )
        assert_matches_type(AsyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.benchmark_job_results.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        benchmark_job_result = await response.parse()
        assert_matches_type(AsyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.benchmark_job_results.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            benchmark_job_result = await response.parse()
            assert_matches_type(AsyncDefaultPagination[BenchmarkJobResult], benchmark_job_result, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_list(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.benchmark_job_results.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_delete(self, async_client: AsyncNeMoPlatform) -> None:
        benchmark_job_result = await async_client.evaluation.benchmark_job_results.delete(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(DeleteResponse, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.benchmark_job_results.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        benchmark_job_result = await response.parse()
        assert_matches_type(DeleteResponse, benchmark_job_result, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.benchmark_job_results.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            benchmark_job_result = await response.parse()
            assert_matches_type(DeleteResponse, benchmark_job_result, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_delete(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.benchmark_job_results.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.benchmark_job_results.with_raw_response.delete(
                name="",
                workspace="workspace",
            )
