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
from nemo_platform.pagination import (
    SyncLogsPagination,
    AsyncLogsPagination,
    SyncDefaultPagination,
    AsyncDefaultPagination,
)
from nemo_platform.types.jobs import (
    PlatformJobResponse,
    JobListExecutionProfilesResponse,
)
from nemo_platform.types.shared import PlatformJobLog, PlatformJobStatusResponse

base_url = os.environ.get("TEST_API_BASE_URL", "http://127.0.0.1:4010")


class TestJobs:
    parametrize = pytest.mark.parametrize("client", [False, True], indirect=True, ids=["loose", "strict"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create(self, client: NeMoPlatform) -> None:
        job = client.jobs.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {"image": "image"},
                            "provider": "cpu",
                        },
                        "name": "preprocess",
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_create_with_all_params(self, client: NeMoPlatform) -> None:
        job = client.jobs.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {
                                "image": "image",
                                "command": ["string"],
                                "entrypoint": ["string"],
                            },
                            "profile": "profile",
                            "provider": "cpu",
                            "resources": {
                                "limits": {
                                    "cpu": "cpu",
                                    "memory": "memory",
                                },
                                "num_gpus": 0,
                                "num_nodes": 1,
                                "requests": {
                                    "cpu": "cpu",
                                    "memory": "memory",
                                },
                                "shm_size": "shm_size",
                            },
                        },
                        "name": "preprocess",
                        "config": {"foo": "bar"},
                        "environment": [
                            {
                                "name": "name",
                                "from_secret": {"name": "name"},
                                "value": "value",
                            }
                        ],
                        "lifecycle": {"staleness_timeout_seconds": 0},
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
            custom_fields={"foo": "bar"},
            description="description",
            name="name",
            ownership={"foo": "bar"},
            project="project",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_create(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {"image": "image"},
                            "provider": "cpu",
                        },
                        "name": "preprocess",
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_create(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {"image": "image"},
                            "provider": "cpu",
                        },
                        "name": "preprocess",
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_create(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.create(
                workspace="",
                platform_spec={
                    "steps": [
                        {
                            "executor": {
                                "container": {"image": "image"},
                                "provider": "cpu",
                            },
                            "name": "preprocess",
                        }
                    ]
                },
                source="source",
                spec={"foo": "bar"},
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_retrieve(self, client: NeMoPlatform) -> None:
        job = client.jobs.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_retrieve(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_retrieve(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_retrieve(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list(self, client: NeMoPlatform) -> None:
        job = client.jobs.list(
            workspace="workspace",
        )
        assert_matches_type(SyncDefaultPagination[PlatformJobResponse], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list_with_all_params(self, client: NeMoPlatform) -> None:
        job = client.jobs.list(
            workspace="workspace",
            filter={
                "created_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "name": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "project": "project",
                "source": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "status": "created",
                "updated_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "workspace": "workspace",
            },
            page=1,
            page_size=1,
            sort="created_at",
        )
        assert_matches_type(SyncDefaultPagination[PlatformJobResponse], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_list(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(SyncDefaultPagination[PlatformJobResponse], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_list(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(SyncDefaultPagination[PlatformJobResponse], job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_list(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_delete(self, client: NeMoPlatform) -> None:
        job = client.jobs.delete(
            name="name",
            workspace="workspace",
        )
        assert job is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_delete(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert job is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_delete(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert job is None

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_delete(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.delete(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_cancel(self, client: NeMoPlatform) -> None:
        job = client.jobs.cancel(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_cancel(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.cancel(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_cancel(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.cancel(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_cancel(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.cancel(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.cancel(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_get_logs(self, client: NeMoPlatform) -> None:
        job = client.jobs.get_logs(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(SyncLogsPagination[PlatformJobLog], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_get_logs_with_all_params(self, client: NeMoPlatform) -> None:
        job = client.jobs.get_logs(
            name="name",
            workspace="workspace",
            attempt_id=0,
            limit=1,
            page_cursor="page_cursor",
            step_id="step_id",
            task_id="task_id",
        )
        assert_matches_type(SyncLogsPagination[PlatformJobLog], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_get_logs(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.get_logs(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(SyncLogsPagination[PlatformJobLog], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_get_logs(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.get_logs(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(SyncLogsPagination[PlatformJobLog], job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_get_logs(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.get_logs(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.get_logs(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_get_status(self, client: NeMoPlatform) -> None:
        job = client.jobs.get_status(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobStatusResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_get_status(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.get_status(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(PlatformJobStatusResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_get_status(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.get_status(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(PlatformJobStatusResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_get_status(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.get_status(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.get_status(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_list_execution_profiles(self, client: NeMoPlatform) -> None:
        job = client.jobs.list_execution_profiles()
        assert_matches_type(JobListExecutionProfilesResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_list_execution_profiles(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.list_execution_profiles()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(JobListExecutionProfilesResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_list_execution_profiles(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.list_execution_profiles() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(JobListExecutionProfilesResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_pause(self, client: NeMoPlatform) -> None:
        job = client.jobs.pause(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_pause(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.pause(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_pause(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.pause(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_pause(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.pause(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.pause(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_resume(self, client: NeMoPlatform) -> None:
        job = client.jobs.resume(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_resume(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.resume(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_resume(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.resume(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_resume(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.resume(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.resume(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_method_update_status_details(self, client: NeMoPlatform) -> None:
        job = client.jobs.update_status_details(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
        )
        assert_matches_type(object, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_raw_response_update_status_details(self, client: NeMoPlatform) -> None:
        response = client.jobs.with_raw_response.update_status_details(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = response.parse()
        assert_matches_type(object, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_streaming_response_update_status_details(self, client: NeMoPlatform) -> None:
        with client.jobs.with_streaming_response.update_status_details(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = response.parse()
            assert_matches_type(object, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    def test_path_params_update_status_details(self, client: NeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            client.jobs.with_raw_response.update_status_details(
                name="name",
                workspace="",
                body={"foo": "bar"},
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            client.jobs.with_raw_response.update_status_details(
                name="",
                workspace="workspace",
                body={"foo": "bar"},
            )


class TestAsyncJobs:
    parametrize = pytest.mark.parametrize(
        "async_client", [False, True, {"http_client": "aiohttp"}], indirect=True, ids=["loose", "strict", "aiohttp"]
    )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {"image": "image"},
                            "provider": "cpu",
                        },
                        "name": "preprocess",
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_create_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {
                                "image": "image",
                                "command": ["string"],
                                "entrypoint": ["string"],
                            },
                            "profile": "profile",
                            "provider": "cpu",
                            "resources": {
                                "limits": {
                                    "cpu": "cpu",
                                    "memory": "memory",
                                },
                                "num_gpus": 0,
                                "num_nodes": 1,
                                "requests": {
                                    "cpu": "cpu",
                                    "memory": "memory",
                                },
                                "shm_size": "shm_size",
                            },
                        },
                        "name": "preprocess",
                        "config": {"foo": "bar"},
                        "environment": [
                            {
                                "name": "name",
                                "from_secret": {"name": "name"},
                                "value": "value",
                            }
                        ],
                        "lifecycle": {"staleness_timeout_seconds": 0},
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
            custom_fields={"foo": "bar"},
            description="description",
            name="name",
            ownership={"foo": "bar"},
            project="project",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {"image": "image"},
                            "provider": "cpu",
                        },
                        "name": "preprocess",
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_create(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.create(
            workspace="workspace",
            platform_spec={
                "steps": [
                    {
                        "executor": {
                            "container": {"image": "image"},
                            "provider": "cpu",
                        },
                        "name": "preprocess",
                    }
                ]
            },
            source="source",
            spec={"foo": "bar"},
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_create(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.create(
                workspace="",
                platform_spec={
                    "steps": [
                        {
                            "executor": {
                                "container": {"image": "image"},
                                "provider": "cpu",
                            },
                            "name": "preprocess",
                        }
                    ]
                },
                source="source",
                spec={"foo": "bar"},
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.retrieve(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.retrieve(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.retrieve(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_retrieve(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.retrieve(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.retrieve(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.list(
            workspace="workspace",
        )
        assert_matches_type(AsyncDefaultPagination[PlatformJobResponse], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.list(
            workspace="workspace",
            filter={
                "created_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "name": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "project": "project",
                "source": {
                    "eq": "$eq",
                    "in_": ["string"],
                    "like": "$like",
                    "nin": ["string"],
                },
                "status": "created",
                "updated_at": {
                    "gte": parse_datetime("2019-12-27T18:11:19.117Z"),
                    "lte": parse_datetime("2019-12-27T18:11:19.117Z"),
                },
                "workspace": "workspace",
            },
            page=1,
            page_size=1,
            sort="created_at",
        )
        assert_matches_type(AsyncDefaultPagination[PlatformJobResponse], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.list(
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(AsyncDefaultPagination[PlatformJobResponse], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_list(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.list(
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(AsyncDefaultPagination[PlatformJobResponse], job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_list(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.list(
                workspace="",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_delete(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.delete(
            name="name",
            workspace="workspace",
        )
        assert job is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.delete(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert job is None

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_delete(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.delete(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert job is None

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_delete(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.delete(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.delete(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_cancel(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.cancel(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_cancel(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.cancel(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_cancel(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.cancel(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_cancel(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.cancel(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.cancel(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_get_logs(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.get_logs(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(AsyncLogsPagination[PlatformJobLog], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_get_logs_with_all_params(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.get_logs(
            name="name",
            workspace="workspace",
            attempt_id=0,
            limit=1,
            page_cursor="page_cursor",
            step_id="step_id",
            task_id="task_id",
        )
        assert_matches_type(AsyncLogsPagination[PlatformJobLog], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_get_logs(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.get_logs(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(AsyncLogsPagination[PlatformJobLog], job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_get_logs(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.get_logs(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(AsyncLogsPagination[PlatformJobLog], job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_get_logs(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.get_logs(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.get_logs(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_get_status(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.get_status(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobStatusResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_get_status(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.get_status(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(PlatformJobStatusResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_get_status(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.get_status(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(PlatformJobStatusResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_get_status(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.get_status(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.get_status(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_list_execution_profiles(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.list_execution_profiles()
        assert_matches_type(JobListExecutionProfilesResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_list_execution_profiles(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.list_execution_profiles()

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(JobListExecutionProfilesResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_list_execution_profiles(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.list_execution_profiles() as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(JobListExecutionProfilesResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_pause(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.pause(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_pause(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.pause(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_pause(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.pause(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_pause(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.pause(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.pause(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_resume(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.resume(
            name="name",
            workspace="workspace",
        )
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_resume(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.resume(
            name="name",
            workspace="workspace",
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(PlatformJobResponse, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_resume(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.resume(
            name="name",
            workspace="workspace",
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(PlatformJobResponse, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_resume(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.resume(
                name="name",
                workspace="",
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.resume(
                name="",
                workspace="workspace",
            )

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_method_update_status_details(self, async_client: AsyncNeMoPlatform) -> None:
        job = await async_client.jobs.update_status_details(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
        )
        assert_matches_type(object, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_raw_response_update_status_details(self, async_client: AsyncNeMoPlatform) -> None:
        response = await async_client.jobs.with_raw_response.update_status_details(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
        )

        assert response.is_closed is True
        assert response.http_request.headers.get("X-Stainless-Lang") == "python"
        job = await response.parse()
        assert_matches_type(object, job, path=["response"])

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_streaming_response_update_status_details(self, async_client: AsyncNeMoPlatform) -> None:
        async with async_client.jobs.with_streaming_response.update_status_details(
            name="name",
            workspace="workspace",
            body={"foo": "bar"},
        ) as response:
            assert not response.is_closed
            assert response.http_request.headers.get("X-Stainless-Lang") == "python"

            job = await response.parse()
            assert_matches_type(object, job, path=["response"])

        assert cast(Any, response.is_closed) is True

    @pytest.mark.skip(reason="Mock server tests are disabled")
    @parametrize
    async def test_path_params_update_status_details(self, async_client: AsyncNeMoPlatform) -> None:
        with pytest.raises(ValueError, match=r"Expected a non-empty value for `workspace` but received ''"):
            await async_client.jobs.with_raw_response.update_status_details(
                name="name",
                workspace="",
                body={"foo": "bar"},
            )

        with pytest.raises(ValueError, match=r"Expected a non-empty value for `name` but received ''"):
            await async_client.jobs.with_raw_response.update_status_details(
                name="",
                workspace="workspace",
                body={"foo": "bar"},
            )
