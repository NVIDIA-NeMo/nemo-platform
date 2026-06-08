# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pandas as pd
import pytest
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.discovery import discover, discover_entry_points
from nemo_safe_synthesizer_plugin.sdk.job import SafeSynthesizerJob
from nemo_safe_synthesizer_plugin.sdk.job_builder import SafeSynthesizerJobBuilder
from nemo_safe_synthesizer_plugin.sdk.resources import AsyncSafeSynthesizerJobsResource, SafeSynthesizerResource


def _mock_platform(requests: list[httpx.Request]) -> NeMoPlatform:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={"name": "safe-synth-job", "status": "created", "spec": {"data_source": "default/data#input.csv"}},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return NeMoPlatform(base_url="http://nmp.test", http_client=http_client, workspace="default")


def test_safe_synthesizer_resource_creates_job_through_plugin_route() -> None:
    requests: list[httpx.Request] = []
    platform = _mock_platform(requests)
    resource = SafeSynthesizerResource(platform)

    response = resource.jobs.create(
        workspace="default",
        name="safe-synth-job",
        spec={"data_source": "default/data#input.csv", "config": {}},
    )

    assert response.name == "safe-synth-job"
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://nmp.test/apis/safe-synthesizer/v2/workspaces/default/jobs"
    assert json.loads(requests[0].read()) == {
        "spec": {"data_source": "default/data#input.csv", "config": {}},
        "name": "safe-synth-job",
    }


def test_safe_synthesizer_resource_mounts_on_platform_client() -> None:
    discover.cache_clear()
    discover_entry_points.cache_clear()
    requests: list[httpx.Request] = []
    platform = _mock_platform(requests)

    response = platform.safe_synthesizer.jobs.create(
        workspace="default",
        name="safe-synth-job",
        spec={"data_source": "default/data#input.csv", "config": {}},
    )

    assert response.name == "safe-synth-job"
    assert str(requests[0].url) == "http://nmp.test/apis/safe-synthesizer/v2/workspaces/default/jobs"


def test_safe_synthesizer_resource_includes_response_detail_in_errors() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "Failed to compile safe-synthesizer job spec"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    platform = NeMoPlatform(base_url="http://nmp.test", http_client=http_client, workspace="default")
    resource = SafeSynthesizerResource(platform)

    try:
        resource.jobs.create(workspace="default", spec={"data_source": "default/data#input.csv", "config": {}})
    except httpx.HTTPStatusError as e:
        assert "Response detail: Failed to compile safe-synthesizer job spec" in str(e)
    else:
        raise AssertionError("Expected HTTPStatusError")


@pytest.mark.asyncio
async def test_async_safe_synthesizer_resource_get_logs_awaits_platform_jobs() -> None:
    platform = MagicMock()
    platform.jobs.get_logs = AsyncMock(return_value=SimpleNamespace(data=[]))
    resource = AsyncSafeSynthesizerJobsResource(platform)

    response = await resource.get_logs("safe-synth-job", workspace="default", limit=10)

    assert response.data == []
    platform.jobs.get_logs.assert_awaited_once_with("safe-synth-job", workspace="default", limit=10)


def test_job_builder_uploads_dataframe_and_submits_spec() -> None:
    client = MagicMock()
    client.files.upload = MagicMock()
    client.safe_synthesizer.jobs.create.return_value = SimpleNamespace(name="safe-synth-job")

    builder = (
        SafeSynthesizerJobBuilder(client, workspace="default")
        .with_data_source(pd.DataFrame({"value": [1]}))
        .with_classify_model_provider("nvidia-build")
        .with_replace_pii()
        .synthesize()
        .with_generate(num_records=10)
        .with_hf_token_secret("hf-token")
    )

    job = builder.create_job(name="safe-synth-job")

    assert job.job_name == "safe-synth-job"
    client.files.upload.assert_called_once()
    create_kwargs = client.safe_synthesizer.jobs.create.call_args.kwargs
    assert create_kwargs["workspace"] == "default"
    assert create_kwargs["name"] == "safe-synth-job"
    assert create_kwargs["spec"]["data_source"].startswith("default/safe-synthesizer-inputs#dataset")
    assert create_kwargs["spec"]["hf_token_secret"] == "hf-token"
    config = create_kwargs["spec"]["config"]
    assert config["enable_synthesis"] is True
    assert config["enable_replace_pii"] is True
    assert config["generation"] == {"num_records": 10}
    assert config["replace_pii"]["globals"]["classify"]["classify_model_provider"] == "default/nvidia-build"


def test_job_builder_submits_pretrained_model_job_for_adapter_reuse() -> None:
    client = MagicMock()
    client.files.upload = MagicMock()
    client.safe_synthesizer.jobs.create.return_value = SimpleNamespace(name="adapter-reuse-job")

    builder = (
        SafeSynthesizerJobBuilder(client, workspace="default")
        .with_data_source(pd.DataFrame({"value": [1]}))
        .with_pretrained_model_job("first-synth-job")
        .with_generate(num_records=25)
    )

    job = builder.create_job(name="adapter-reuse-job")

    assert job.job_name == "adapter-reuse-job"
    create_kwargs = client.safe_synthesizer.jobs.create.call_args.kwargs
    assert create_kwargs["spec"]["pretrained_model_job"] == "first-synth-job"
    assert create_kwargs["spec"]["config"]["generation"] == {"num_records": 25}
    assert "pretrained_model" not in create_kwargs["spec"]["config"]["training"]


@pytest.mark.parametrize("status", ["error", "cancelled"])
def test_safe_synthesizer_job_wait_for_completion_raises_on_terminal_failure(status: str) -> None:
    client = MagicMock()
    client.jobs.get_status.return_value = SimpleNamespace(
        status=status,
        status_details={"reason": "failed"},
        error_details={"message": "boom"},
    )
    job = SafeSynthesizerJob("safe-synth-job", client, workspace="default")

    with pytest.raises(RuntimeError, match=f"ended with status '{status}'"):
        job.wait_for_completion(poll_interval=0, verbose=False)

    client.jobs.get_status.assert_called_once_with("safe-synth-job", workspace="default")


def test_safe_synthesizer_job_fetch_data_reads_synthetic_csv() -> None:
    client = MagicMock()
    client.jobs.results.download.return_value = BytesIO(b"name,value\nalice,1\nbob,2\n")
    job = SafeSynthesizerJob("safe-synth-job", client, workspace="default")

    result = job.fetch_data()

    client.jobs.results.download.assert_called_once_with("synthetic-data", job="safe-synth-job", workspace="default")
    assert list(result.columns) == ["name", "value"]
    assert result["value"].tolist() == [1, 2]


def test_safe_synthesizer_job_fetch_summary_parses_json() -> None:
    client = MagicMock()
    client.jobs.results.download.return_value = BytesIO(
        json.dumps(
            {
                "synthetic_data_quality_score": 8.5,
                "data_privacy_score": 9.0,
                "num_valid_records": 10,
                "num_prompts": 10,
                "timing": {"total_time_sec": 12.5},
            }
        ).encode()
    )
    job = SafeSynthesizerJob("safe-synth-job", client, workspace="default")

    summary = job.fetch_summary()

    client.jobs.results.download.assert_called_once_with("summary", job="safe-synth-job", workspace="default")
    assert summary.synthetic_data_quality_score == 8.5
    assert summary.data_privacy_score == 9.0
    assert summary.timing.total_time_sec == 12.5


def test_safe_synthesizer_job_fetch_logs_follows_pagination() -> None:
    client = MagicMock()
    log_client = MagicMock()
    client.with_options.return_value = log_client
    first_log = SimpleNamespace(
        job="safe-synth-job",
        job_step="safe-synthesizer",
        job_task="task-1",
        message="first",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    second_log = SimpleNamespace(
        job="safe-synth-job",
        job_step="safe-synthesizer",
        job_task="task-1",
        message="second",
        timestamp=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
    )
    log_client.jobs.get_logs.side_effect = [
        SimpleNamespace(data=[first_log], next_page="cursor-2"),
        SimpleNamespace(data=[second_log], next_page=None),
    ]
    job = SafeSynthesizerJob("safe-synth-job", client, workspace="default")

    logs = list(job.fetch_logs(timeout=5.0))

    assert [log.message for log in logs] == ["first", "second"]
    assert client.with_options.call_count == 2
    assert log_client.jobs.get_logs.call_args_list[1].kwargs["page_cursor"] == "cursor-2"
