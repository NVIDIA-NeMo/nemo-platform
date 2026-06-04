# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pandas as pd
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.discovery import discover, discover_entry_points
from nemo_safe_synthesizer_plugin.sdk.job_builder import SafeSynthesizerJobBuilder
from nemo_safe_synthesizer_plugin.sdk.resources import SafeSynthesizerResource


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
