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
from nemo_platform.types.intake.ingest import (
    ChatCompletionsIngestResponse,
)

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestChatCompletions:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create(self, client: NeMoPlatform) -> None:
        chat_completion = client.intake.ingest.chat_completions.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={},
        )
        assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params(self, client: NeMoPlatform) -> None:
        chat_completion = client.intake.ingest.chat_completions.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={
                "choices": [{"foo": "bar"}],
                "error": {"foo": "bar"},
            },
            cost_details={"foo": 0},
            cost_input_usd=0,
            cost_output_usd=0,
            cost_usd=0,
            evaluation_context={
                "dataset_id": "dataset_id",
                "dataset_name": "dataset_name",
                "dataset_version": "dataset_version",
                "evaluation_id": "evaluation_id",
                "evaluation_run_id": "evaluation_run_id",
                "evaluation_sha": "evaluation_sha",
                "metadata": {"foo": "bar"},
                "test_case_id": "test_case_id",
            },
            experiment_context={
                "experiment_id": "experiment_id",
                "test_case_id": "test_case_id",
            },
            provider="provider",
            session_id="session_id",
            trace_id="trace_id",
        )
        assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create(self, client: NeMoPlatform) -> None:
        response = client.intake.ingest.chat_completions.with_raw_response.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={},
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        chat_completion = response.parse()
        assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create(self, client: NeMoPlatform) -> None:
        with client.intake.ingest.chat_completions.with_streaming_response.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={},
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            chat_completion = response.parse()
            assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.intake.ingest.chat_completions.with_raw_response.create(
                workspace="",
                request={
                    "messages": [{"role": "user"}],
                    "model": "model",
                },
                response={},
            )


class TestAsyncChatCompletions:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create(self, async_client: AsyncNeMoPlatform) -> None:
        chat_completion = await async_client.intake.ingest.chat_completions.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={},
        )
        assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        chat_completion = await async_client.intake.ingest.chat_completions.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={
                "choices": [{"foo": "bar"}],
                "error": {"foo": "bar"},
            },
            cost_details={"foo": 0},
            cost_input_usd=0,
            cost_output_usd=0,
            cost_usd=0,
            evaluation_context={
                "dataset_id": "dataset_id",
                "dataset_name": "dataset_name",
                "dataset_version": "dataset_version",
                "evaluation_id": "evaluation_id",
                "evaluation_run_id": "evaluation_run_id",
                "evaluation_sha": "evaluation_sha",
                "metadata": {"foo": "bar"},
                "test_case_id": "test_case_id",
            },
            experiment_context={
                "experiment_id": "experiment_id",
                "test_case_id": "test_case_id",
            },
            provider="provider",
            session_id="session_id",
            trace_id="trace_id",
        )
        assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.intake.ingest.chat_completions.with_raw_response.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={},
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        chat_completion = await response.parse()
        assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.intake.ingest.chat_completions.with_streaming_response.create(
            workspace="workspace",
            request={
                "messages": [{"role": "user"}],
                "model": "model",
            },
            response={},
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            chat_completion = await response.parse()
            assert_matches_type(ChatCompletionsIngestResponse, chat_completion, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.intake.ingest.chat_completions.with_raw_response.create(
                workspace="",
                request={
                    "messages": [{"role": "user"}],
                    "model": "model",
                },
                response={},
            )
