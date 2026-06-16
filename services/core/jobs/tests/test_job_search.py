# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from httpx import AsyncClient
from nemo_platform import AsyncNeMoPlatform
from nmp.common.entities import DEFAULT_WORKSPACE

# Skip all substring search tests until entity store supports LIKE queries (nmp-oq7)
SUBSTRING_SEARCH_SKIP = pytest.mark.skip(reason="Requires substring search support in entity store (nmp-oq7)")


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_jobs_by_name(test_sdk: AsyncNeMoPlatform):
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="training-job-v1",
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="evaluation-job",
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(extra_query={"filter[name]": ["training"]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 1
    assert "training" in response.data[0].name.lower()


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_jobs_by_project(test_sdk: AsyncNeMoPlatform):
    # TODO: Once SDK is regenerated, pass project= directly instead of extra_body
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="job1",
        source="testing",
        extra_body={"project": "nlp-project"},
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="job2",
        source="testing",
        extra_body={"project": "vision-project"},
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(extra_query={"filter[project]": ["nlp"]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 1
    assert response.data[0].project == "nlp-project"


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_jobs_multiple_values_or_logic(test_sdk: AsyncNeMoPlatform):
    await test_sdk.jobs.create(
        name="training-job",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="evaluation-job",
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="inference-job",
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(
        extra_query={"filter[name]": ["training", "evaluation"]}, workspace=DEFAULT_WORKSPACE
    )
    assert len(response.data) == 2
    names = [job.name for job in response.data]
    assert "training-job" in names
    assert "evaluation-job" in names


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_jobs_multiple_fields_and_logic(test_sdk: AsyncNeMoPlatform):
    # TODO: Once SDK is regenerated, pass project= directly instead of extra_body
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="training-job-nlp",
        source="testing",
        extra_body={"project": "nlp-project"},
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="training-job-vision",
        source="testing",
        extra_body={"project": "vision-project"},
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="evaluation-job-nlp",
        source="testing",
        extra_body={"project": "nlp-project"},
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    # Search for training jobs in nlp project - should only match training-job-nlp
    response = await test_sdk.jobs.list(
        extra_query={"filter[name]": ["training"], "filter[project]": ["nlp"]}, workspace=DEFAULT_WORKSPACE
    )
    assert len(response.data) == 1
    assert response.data[0].name == "training-job-nlp"
    assert response.data[0].project == "nlp-project"


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_jobs_case_insensitive(test_sdk: AsyncNeMoPlatform):
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="Training-Job-V1",
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(
        extra_query={"filter[name]": ["training"]},
        workspace=DEFAULT_WORKSPACE,
    )
    assert len(response.data) == 1
    assert response.data[0].name == "Training-Job-V1"


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_jobs_partial_match(test_sdk: AsyncNeMoPlatform):
    await test_sdk.jobs.create(
        workspace=DEFAULT_WORKSPACE,
        name="my-training-job-v1",
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(extra_query={"filter[name]": ["train"]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 1
    assert "train" in response.data[0].name.lower()


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_combined_with_filter(test_sdk: AsyncNeMoPlatform):
    job1 = await test_sdk.jobs.create(
        name="training-job-1",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        name="training-job-2",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    await test_sdk.jobs.cancel(job1.id, workspace=DEFAULT_WORKSPACE)

    response = await test_sdk.jobs.list(
        filter={"source": "testing", "name": "training-job-1"}, workspace=DEFAULT_WORKSPACE
    )
    assert len(response.data) == 1
    assert response.data[0].id == job1.id


@pytest.mark.asyncio
@SUBSTRING_SEARCH_SKIP
async def test_search_no_results(test_sdk: AsyncNeMoPlatform):
    await test_sdk.jobs.create(
        name="training-job",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(extra_query={"filter[name]": ["nonexistent"]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 0


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_empty_string(test_sdk: AsyncNeMoPlatform):
    await test_sdk.jobs.create(
        name="job1",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        name="job2",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(extra_query={"filter[name]": [""]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 2


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_via_http_client(test_client: AsyncClient):
    await test_client.post(
        "/v1/hello-world/jobs",
        json={
            "name": "search-test-job",
            "spec": {"config": {"key": "value"}, "target": "test"},
        },
    )

    response = await test_client.get("/v1/hello-world/jobs?filter[name]=search")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert "search" in data["data"][0]["name"]
    assert "filter" in data


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_pagination(test_sdk: AsyncNeMoPlatform):
    for i in range(15):
        await test_sdk.jobs.create(
            name=f"training-job-{i}",
            workspace=DEFAULT_WORKSPACE,
            source="testing",
            spec={},
            platform_spec={
                "steps": [
                    {
                        "name": "step1",
                        "executor": {
                            "kind": "container",
                            "provider": "cpu",
                            "profile": "default",
                            "container": {"image": "test"},
                        },
                    }
                ]
            },
        )

    response = await test_sdk.jobs.list(
        page=1, page_size=10, extra_query={"filter[name]": ["training"]}, workspace=DEFAULT_WORKSPACE
    )
    assert len(response.data) == 10
    assert response.pagination.total_results == 15

    response_page2 = await test_sdk.jobs.list(
        page=2, page_size=10, extra_query={"filter[name]": ["training"]}, workspace=DEFAULT_WORKSPACE
    )
    assert len(response_page2.data) == 5


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_underscore_behavior(test_sdk: AsyncNeMoPlatform):
    """Test that underscore is treated as a literal character in search (substring matching)."""
    await test_sdk.jobs.create(
        name="test_job_with_underscore",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )
    await test_sdk.jobs.create(
        name="test-job-with-dash",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    # Underscore is treated as a literal character - only matches jobs containing "_"
    response = await test_sdk.jobs.list(extra_query={"filter[name]": ["_"]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 1  # Only the job with underscore matches
    assert response.data[0].name == "test_job_with_underscore"

    # Create a job with a valid name containing special allowed characters
    await test_sdk.jobs.create(
        name="job-100-complete",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    # Search for the job using a substring
    response = await test_sdk.jobs.list(extra_query={"filter[name]": ["100"]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 1  # Only the job-100-complete job matches


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_long_string(test_sdk: AsyncNeMoPlatform):
    # Use a name within the 255 character limit
    long_name = "job-" + "a" * 200  # Total 204 chars, within 255 limit
    await test_sdk.jobs.create(
        name=long_name,
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    long_search = "a" * 200
    response = await test_sdk.jobs.list(extra_query={"filter[name]": [long_search]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 1
    assert long_search in response.data[0].name


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_result_limit(test_sdk: AsyncNeMoPlatform):
    for i in range(150):
        await test_sdk.jobs.create(
            name=f"batch-job-{i:03d}",
            workspace=DEFAULT_WORKSPACE,
            source="testing",
            spec={},
            platform_spec={
                "steps": [
                    {
                        "name": "step1",
                        "executor": {
                            "kind": "container",
                            "provider": "cpu",
                            "profile": "default",
                            "container": {"image": "test"},
                        },
                    }
                ]
            },
        )

    response = await test_sdk.jobs.list(
        page=1, page_size=100, extra_query={"filter[name]": ["batch"]}, workspace=DEFAULT_WORKSPACE
    )
    assert len(response.data) == 100
    assert response.pagination.total_results == 150


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_invalid_field(test_client: AsyncClient):
    """Test that invalid search fields are silently ignored (Pydantic extra='allow' behavior)."""
    await test_client.post(
        "/v1/hello-world/jobs",
        json={
            "name": "test-job",
            "spec": {"config": {"key": "value"}, "target": "test"},
        },
    )
    response = await test_client.get("/v1/hello-world/jobs?filter[invalid_field]=test")
    assert response.status_code == 422  # Invalid fields are NOT ignored


@SUBSTRING_SEARCH_SKIP
@pytest.mark.asyncio
async def test_search_special_characters(test_sdk: AsyncNeMoPlatform):
    # Use only valid special characters per the pattern ^[\w\-\+.@:]*$
    await test_sdk.jobs.create(
        name="job-with-special-chars@example.com:8080",
        workspace=DEFAULT_WORKSPACE,
        source="testing",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "step1",
                    "executor": {
                        "kind": "container",
                        "provider": "cpu",
                        "profile": "default",
                        "container": {"image": "test"},
                    },
                }
            ]
        },
    )

    response = await test_sdk.jobs.list(extra_query={"filter[name]": ["@example"]}, workspace=DEFAULT_WORKSPACE)
    assert len(response.data) == 1
    assert "@example" in response.data[0].name
