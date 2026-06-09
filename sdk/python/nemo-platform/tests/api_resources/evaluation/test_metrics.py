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
    MetricCreateResponse,
    MetricRetrieveResponse,
    MetricEvaluationResponse,
)
from nemo_platform.types.evaluation.metrics_list_response import Data

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestMetrics:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_1(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                        },
                        {
                            "label": "label",
                            "value": 0,
                        },
                    ],
                }
            ],
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_1(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                            "description": "description",
                        },
                        {
                            "label": "label",
                            "value": 0,
                            "description": "description",
                        },
                    ],
                    "description": "description",
                    "parser": {
                        "json_path": "json_path",
                        "type": "json",
                    },
                }
            ],
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            labels={"foo": "string"},
            optional_fields=["reference"],
            prompt_template={
                "content": "bar",
                "type": "bar",
            },
            reasoning={
                "effort": "effort",
                "end_token": "end_token",
                "include_if_not_finished": True,
            },
            structured_output={"foo": "bar"},
            supported_job_types=["online"],
            system_prompt="system_prompt",
            type="llm-judge",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_1(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                        },
                        {
                            "label": "label",
                            "value": 0,
                        },
                    ],
                }
            ],
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_1(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                        },
                        {
                            "label": "label",
                            "value": 0,
                        },
                    ],
                }
            ],
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_1(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                model={
                    "name": "name",
                    "url": "url",
                },
                scores=[
                    {
                        "name": "name",
                        "rubric": [
                            {
                                "label": "label",
                                "value": 0,
                            },
                            {
                                "label": "label",
                                "value": 0,
                            },
                        ],
                    }
                ],
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                model={
                    "name": "name",
                    "url": "url",
                },
                scores=[
                    {
                        "name": "name",
                        "rubric": [
                            {
                                "label": "label",
                                "value": 0,
                            },
                            {
                                "label": "label",
                                "value": 0,
                            },
                        ],
                    }
                ],
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_2(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_2(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            metric_mode="f1",
            supported_job_types=["online"],
            type="topic_adherence",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_2(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_2(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_2(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_3(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_3(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="agent_goal_accuracy",
            use_reference=True,
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_3(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_3(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_3(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_4(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_4(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="answer_accuracy",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_4(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_4(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_4(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_5(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_5(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_relevance",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_5(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_5(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_5(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_6(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_6(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="response_groundedness",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_6(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_6(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_6(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_7(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_7(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_recall",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_7(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_7(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_7(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_8(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_8(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_precision",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_8(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_8(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_8(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_9(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_9(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_entity_recall",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_9(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_9(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_9(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_10(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
            },
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_10(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            strictness=0,
            supported_job_types=["online"],
            type="response_relevancy",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_10(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
            },
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_10(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
            },
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_10(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                embeddings_model={
                    "name": "name",
                    "url": "url",
                },
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                embeddings_model={
                    "name": "name",
                    "url": "url",
                },
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_11(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_11(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="faithfulness",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_11(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_11(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_11(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_12(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_12(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="noise_sensitivity",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_12(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_12(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_12(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_13(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_13(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            description="description",
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="tool_call_accuracy",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_13(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_13(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_13(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_14(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            references=["string"],
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_14(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            references=["string"],
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="bleu",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_14(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            references=["string"],
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_14(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            references=["string"],
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_14(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                references=["string"],
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                references=["string"],
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_15(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_15(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="exact-match",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_15(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_15(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_15(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_16(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_16(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="f1",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_16(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_16(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_16(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_17(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_17(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
            description="description",
            epsilon=0,
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="number-check",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_17(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_17(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_17(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text}}",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text}}",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_18(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[{"name": "name"}],
            url="url",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_18(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[
                {
                    "name": "name",
                    "description": "description",
                    "maximum": 0,
                    "minimum": 0,
                    "parser": {
                        "json_path": "json_path",
                        "type": "json",
                    },
                }
            ],
            url="url",
            api_key_secret="api_key_secret",
            description="description",
            labels={"foo": "string"},
            max_retries=0,
            supported_job_types=["online"],
            timeout_seconds=0,
            type="remote",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_18(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[{"name": "name"}],
            url="url",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_18(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[{"name": "name"}],
            url="url",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_18(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                body={"foo": "bar"},
                scores=[{"name": "name"}],
                url="url",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                body={"foo": "bar"},
                scores=[{"name": "name"}],
                url="url",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_19(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_19(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
            api_key_secret="api_key_secret",
            description="description",
            labels={"foo": "string"},
            max_retries=0,
            supported_job_types=["online"],
            timeout_seconds=0,
            type="nemo-agent-toolkit-remote",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_19(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_19(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_19(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                evaluator_name="evaluator_name",
                url="url",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                evaluator_name="evaluator_name",
                url="url",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_20(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_20(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="rouge",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_20(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_20(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_20(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_21(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_21(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="string-check",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_21(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_21(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_21(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text | trim}}",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text | trim}}",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_overload_22(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params_overload_22(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="tool-calling",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create_overload_22(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create_overload_22(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create_overload_22(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_retrieve(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(MetricRetrieveResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_retrieve(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricRetrieveResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_retrieve(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricRetrieveResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_retrieve(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.list(
            workspace="workspace",
        )
        assert_matches_type(SyncDefaultPagination[Data], metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list_with_all_params(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.list(
            workspace="workspace",
            filter={
                "created_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "description": "description",
                "labels": {"foo": "string"},
                "name": "name",
                "project": "project",
                "type": "bleu",
                "updated_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
            },
            page=0,
            page_size=0,
            sort="-created_at",
        )
        assert_matches_type(SyncDefaultPagination[Data], metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_list(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(SyncDefaultPagination[Data], metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_list(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(SyncDefaultPagination[Data], metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_list(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_delete(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.delete(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(DeleteResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_delete(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(DeleteResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_delete(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(DeleteResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_delete(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.evaluation.metrics.with_raw_response.delete(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_evaluate(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
        )
        assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_evaluate_with_all_params(self, client: NeMoPlatform) -> None:
        metric = client.evaluation.metrics.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
            aggregate_fields=["nan_count"],
        )
        assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_evaluate(self, client: NeMoPlatform) -> None:
        response = client.evaluation.metrics.with_raw_response.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = response.parse()
        assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_evaluate(self, client: NeMoPlatform) -> None:
        with client.evaluation.metrics.with_streaming_response.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = response.parse()
            assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_evaluate(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.evaluation.metrics.with_raw_response.evaluate(
                workspace="",
                dataset={"rows": [{"foo": "bar"}]},
                metric="26f1kl_-n-71/4m_-__-35-",
            )


class TestAsyncMetrics:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_1(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                        },
                        {
                            "label": "label",
                            "value": 0,
                        },
                    ],
                }
            ],
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_1(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                            "description": "description",
                        },
                        {
                            "label": "label",
                            "value": 0,
                            "description": "description",
                        },
                    ],
                    "description": "description",
                    "parser": {
                        "json_path": "json_path",
                        "type": "json",
                    },
                }
            ],
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            labels={"foo": "string"},
            optional_fields=["reference"],
            prompt_template={
                "content": "bar",
                "type": "bar",
            },
            reasoning={
                "effort": "effort",
                "end_token": "end_token",
                "include_if_not_finished": True,
            },
            structured_output={"foo": "bar"},
            supported_job_types=["online"],
            system_prompt="system_prompt",
            type="llm-judge",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_1(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                        },
                        {
                            "label": "label",
                            "value": 0,
                        },
                    ],
                }
            ],
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_1(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            model={
                "name": "name",
                "url": "url",
            },
            scores=[
                {
                    "name": "name",
                    "rubric": [
                        {
                            "label": "label",
                            "value": 0,
                        },
                        {
                            "label": "label",
                            "value": 0,
                        },
                    ],
                }
            ],
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_1(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                model={
                    "name": "name",
                    "url": "url",
                },
                scores=[
                    {
                        "name": "name",
                        "rubric": [
                            {
                                "label": "label",
                                "value": 0,
                            },
                            {
                                "label": "label",
                                "value": 0,
                            },
                        ],
                    }
                ],
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                model={
                    "name": "name",
                    "url": "url",
                },
                scores=[
                    {
                        "name": "name",
                        "rubric": [
                            {
                                "label": "label",
                                "value": 0,
                            },
                            {
                                "label": "label",
                                "value": 0,
                            },
                        ],
                    }
                ],
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_2(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_2(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            metric_mode="f1",
            supported_job_types=["online"],
            type="topic_adherence",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_2(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_2(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_2(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_3(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_3(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="agent_goal_accuracy",
            use_reference=True,
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_3(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_3(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_3(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_4(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_4(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="answer_accuracy",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_4(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_4(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_4(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_5(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_5(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_relevance",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_5(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_5(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_5(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_6(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_6(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="response_groundedness",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_6(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_6(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_6(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_7(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_7(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_recall",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_7(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_7(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_7(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_8(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_8(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_precision",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_8(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_8(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_8(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_9(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_9(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="context_entity_recall",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_9(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_9(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_9(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_10(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
            },
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_10(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            strictness=0,
            supported_job_types=["online"],
            type="response_relevancy",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_10(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
            },
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_10(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            embeddings_model={
                "name": "name",
                "url": "url",
            },
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_10(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                embeddings_model={
                    "name": "name",
                    "url": "url",
                },
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                embeddings_model={
                    "name": "name",
                    "url": "url",
                },
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_11(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_11(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="faithfulness",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_11(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_11(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_11(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_12(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_12(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
                "api_key_secret": "api_key_secret",
                "format": "nim",
            },
            description="description",
            ignore_request_failure=True,
            inference={
                "max_completion_tokens": 1,
                "max_tokens": 1,
                "stop": ["string"],
                "temperature": 0,
                "top_p": 0,
            },
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="noise_sensitivity",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_12(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_12(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            judge_model={
                "name": "name",
                "url": "url",
            },
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_12(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                judge_model={
                    "name": "name",
                    "url": "url",
                },
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_13(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_13(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            description="description",
            input_template={"foo": "bar"},
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="tool_call_accuracy",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_13(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_13(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_13(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_14(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            references=["string"],
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_14(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            references=["string"],
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="bleu",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_14(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            references=["string"],
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_14(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            references=["string"],
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_14(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                references=["string"],
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                references=["string"],
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_15(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_15(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="exact-match",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_15(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_15(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_15(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_16(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_16(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="f1",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_16(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_16(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_16(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_17(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_17(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
            description="description",
            epsilon=0,
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="number-check",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_17(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_17(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text}}",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_17(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text}}",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text}}",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_18(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[{"name": "name"}],
            url="url",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_18(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[
                {
                    "name": "name",
                    "description": "description",
                    "maximum": 0,
                    "minimum": 0,
                    "parser": {
                        "json_path": "json_path",
                        "type": "json",
                    },
                }
            ],
            url="url",
            api_key_secret="api_key_secret",
            description="description",
            labels={"foo": "string"},
            max_retries=0,
            supported_job_types=["online"],
            timeout_seconds=0,
            type="remote",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_18(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[{"name": "name"}],
            url="url",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_18(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
            scores=[{"name": "name"}],
            url="url",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_18(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                body={"foo": "bar"},
                scores=[{"name": "name"}],
                url="url",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                body={"foo": "bar"},
                scores=[{"name": "name"}],
                url="url",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_19(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_19(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
            api_key_secret="api_key_secret",
            description="description",
            labels={"foo": "string"},
            max_retries=0,
            supported_job_types=["online"],
            timeout_seconds=0,
            type="nemo-agent-toolkit-remote",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_19(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_19(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            evaluator_name="evaluator_name",
            url="url",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_19(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                evaluator_name="evaluator_name",
                url="url",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                evaluator_name="evaluator_name",
                url="url",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_20(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_20(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            candidate="candidate",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="rouge",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_20(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_20(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_20(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_21(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_21(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="string-check",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_21(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_21(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            left_template="{{item.dataset_column_name}}",
            operation="equals",
            right_template="{{sample.output_text | trim}}",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_21(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text | trim}}",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                left_template="{{item.dataset_column_name}}",
                operation="equals",
                right_template="{{sample.output_text | trim}}",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_overload_22(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params_overload_22(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.create(
            name="name",
            workspace="workspace",
            reference="reference",
            description="description",
            labels={"foo": "string"},
            supported_job_types=["online"],
            type="tool-calling",
        )
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create_overload_22(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricCreateResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create_overload_22(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.create(
            name="name",
            workspace="workspace",
            reference="reference",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricCreateResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create_overload_22(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="name",
                workspace="",
                reference="reference",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.create(
                name="",
                workspace="workspace",
                reference="reference",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(MetricRetrieveResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricRetrieveResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricRetrieveResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.list(
            workspace="workspace",
        )
        assert_matches_type(AsyncDefaultPagination[Data], metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.list(
            workspace="workspace",
            filter={
                "created_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "description": "description",
                "labels": {"foo": "string"},
                "name": "name",
                "project": "project",
                "type": "bleu",
                "updated_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
            },
            page=0,
            page_size=0,
            sort="-created_at",
        )
        assert_matches_type(AsyncDefaultPagination[Data], metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(AsyncDefaultPagination[Data], metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(AsyncDefaultPagination[Data], metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_list(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_delete(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.delete(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(DeleteResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(DeleteResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(DeleteResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_delete(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.delete(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_evaluate(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
        )
        assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_evaluate_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        metric = await async_client.evaluation.metrics.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
            aggregate_fields=["nan_count"],
        )
        assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_evaluate(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.evaluation.metrics.with_raw_response.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        metric = await response.parse()
        assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_evaluate(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.evaluation.metrics.with_streaming_response.evaluate(
            workspace="workspace",
            dataset={"rows": [{"foo": "bar"}]},
            metric="26f1kl_-n-71/4m_-__-35-",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            metric = await response.parse()
            assert_matches_type(MetricEvaluationResponse, metric, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_evaluate(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.evaluation.metrics.with_raw_response.evaluate(
                workspace="",
                dataset={"rows": [{"foo": "bar"}]},
                metric="26f1kl_-n-71/4m_-__-35-",
            )
