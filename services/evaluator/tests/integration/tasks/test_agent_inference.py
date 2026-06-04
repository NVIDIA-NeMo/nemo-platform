# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for agent inference in BenchmarkOnlineAgentJob and MetricOnlineAgentJob.

Verifies that agent inference dispatches HTTP POST requests correctly for both
NAT (nemo_agent_toolkit) and generic agent formats.
"""

from typing import cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from nemo_evaluator_sdk.agent_inference import make_agent_inference_request
from nemo_evaluator_sdk.enums import AgentFormat
from nemo_evaluator_sdk.execution.metric_execution import ComputeMetricPipeline, generate_online_sample_agent
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values.agents import Agent
from nmp.evaluator.app.values import BenchmarkOnlineAgentJob
from nmp.evaluator.app.values.metrics_job import MetricOnlineAgentJob


def _nat_agent() -> Agent:
    return Agent(
        url="http://nat-agent.test:8080",
        name="test-nat-agent",
        format=AgentFormat.NEMO_AGENT_TOOLKIT,
    )


def _generic_agent() -> Agent:
    return Agent(
        url="http://generic-agent.test:9090/run",
        name="test-generic-agent",
        format=AgentFormat.GENERIC,
        body={"input_message": "{{ messages[-1].content }}"},
        response_path="$.output",
        trajectory_path="$.trajectory",
    )


class _TestMetric:
    type = "exact-match"

    def metric(self, item: dict, sample: dict, trace=None) -> float:
        del item, sample, trace
        return 1.0

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        del input
        raise AssertionError("compute_scores is not used in these generation-only tests")

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("exact-match")]


def _test_metric() -> Metric:
    return cast(Metric, _TestMetric())


def _benchmark_agent_job(agent: Agent) -> BenchmarkOnlineAgentJob:
    return BenchmarkOnlineAgentJob.model_validate(
        {
            "benchmark": {
                "name": "agent-benchmark",
                "dataset": "test-workspace/test-dataset",
                "metrics": [
                    {
                        "metric_ref": "default/exact-match",
                        "metric": {"type": "exact-match", "reference": "{{item.expected}}"},
                    }
                ],
            },
            "agent": agent.model_dump(),
            "prompt_template": {"messages": [{"role": "user", "content": "{{item.input}}"}]},
        }
    )


def _metric_agent_job(agent: Agent) -> MetricOnlineAgentJob:
    return MetricOnlineAgentJob.model_validate(
        {
            "metric": {"type": "exact-match", "reference": "{{item.expected}}"},
            "agent": agent.model_dump(),
            "dataset": {"rows": [{"input": "What is 1+1?", "expected": "2"}]},
            "prompt_template": {"messages": [{"role": "user", "content": "{{item.input}}"}]},
        }
    )


# ---------------------------------------------------------------------------
# Test 1: BenchmarkOnlineAgentJob with NAT agent — SSE streaming POST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_benchmark_nat_agent_sends_post_to_generate_full():
    """NAT agent benchmark inference POSTs to /generate/full with SSE streaming."""
    agent = _nat_agent()
    job = _benchmark_agent_job(agent)

    captured_calls = []

    with patch("nemo_evaluator_sdk.agent_inference.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value = client_instance
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)

        stream_ctx = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None

        async def aiter_lines():
            yield 'data: {"value": "The answer is 2"}'

        mock_resp.aiter_lines = aiter_lines
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        def capture_stream(method, url, **kwargs):
            captured_calls.append({"method": method, "url": url, **kwargs})
            return stream_ctx

        client_instance.stream = capture_stream

        sample = await generate_online_sample_agent(
            agent=agent,
            row={"input": "What is 1+1?", "expected": "2"},
            index=0,
            prompt_template=job.prompt_template,
            agent_inference_fn=make_agent_inference_request,
        )

    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://nat-agent.test:8080/generate/full"
    assert call["params"] == {"filter_steps": "none"}
    assert call["json"]["input_message"] == "What is 1+1?"

    assert sample["output_text"] == "The answer is 2"
    assert sample["response"]["choices"][0]["message"]["content"] == "The answer is 2"


# ---------------------------------------------------------------------------
# Test 2: BenchmarkOnlineAgentJob with generic agent — direct POST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_benchmark_generic_agent_sends_post_with_body_template():
    """Generic agent benchmark inference POSTs rendered body and extracts via JSONPath."""
    agent = _generic_agent()
    job = _benchmark_agent_job(agent)

    captured_calls = []

    with patch("nemo_evaluator_sdk.agent_inference.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value = client_instance
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)

        agent_response = {
            "output": "The answer is 2",
            "trajectory": [{"step": "think", "content": "1+1 = 2"}],
        }

        async def capture_post(url, **kwargs):
            captured_calls.append({"url": url, **kwargs})
            return httpx.Response(200, json=agent_response, request=httpx.Request("POST", url))

        client_instance.post = capture_post

        sample = await generate_online_sample_agent(
            agent=agent,
            row={"input": "What is 1+1?", "expected": "2"},
            index=0,
            prompt_template=job.prompt_template,
            agent_inference_fn=make_agent_inference_request,
        )

    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["url"] == "http://generic-agent.test:9090/run"
    assert call["json"]["input_message"] == "What is 1+1?"

    assert sample["output_text"] == "The answer is 2"
    assert sample["trajectory"] == [{"step": "think", "content": "1+1 = 2"}]


# ---------------------------------------------------------------------------
# Test 3: MetricOnlineAgentJob with NAT agent — full pipeline integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metric_nat_agent_pipeline_calls_agent_inference():
    """MetricOnlineAgentJob pipeline dispatches to agent inference, not model inference."""
    agent = _nat_agent()
    job = _metric_agent_job(agent)

    captured_calls = []

    with patch("nemo_evaluator_sdk.agent_inference.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value = client_instance
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)

        stream_ctx = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None

        async def aiter_lines():
            yield 'data: {"value": "2"}'

        mock_resp.aiter_lines = aiter_lines
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        def capture_stream(method, url, **kwargs):
            captured_calls.append({"method": method, "url": url, **kwargs})
            return stream_ctx

        client_instance.stream = capture_stream

        pipeline = ComputeMetricPipeline(
            rows=[{"input": "What is 1+1?", "expected": "2"}],
            parallelism=1,
            metric=_test_metric(),
            target=agent,
            params=job.params,
            prompt_template=job.prompt_template,
            metric_key="exact-match",
            inference_fn=make_agent_inference_request,
        )

        sample = await pipeline.generate_sample(0, {"input": "What is 1+1?", "expected": "2"})

    assert len(captured_calls) == 1
    assert captured_calls[0]["method"] == "POST"
    assert "generate/full" in captured_calls[0]["url"]
    assert sample["output_text"] == "2"


# ---------------------------------------------------------------------------
# Test 4: MetricOnlineAgentJob with generic agent — full pipeline integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metric_generic_agent_pipeline_calls_agent_inference():
    """MetricOnlineAgentJob pipeline dispatches to generic agent via HTTP POST."""
    agent = _generic_agent()
    job = _metric_agent_job(agent)

    captured_calls = []

    with patch("nemo_evaluator_sdk.agent_inference.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value = client_instance
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)

        agent_response = {
            "output": "2",
            "trajectory": [{"step": "compute", "content": "1+1=2"}],
        }

        async def capture_post(url, **kwargs):
            captured_calls.append({"url": url, **kwargs})
            return httpx.Response(200, json=agent_response, request=httpx.Request("POST", url))

        client_instance.post = capture_post

        pipeline = ComputeMetricPipeline(
            rows=[{"input": "What is 1+1?", "expected": "2"}],
            parallelism=1,
            metric=_test_metric(),
            target=agent,
            params=job.params,
            prompt_template=job.prompt_template,
            metric_key="exact-match",
            inference_fn=make_agent_inference_request,
        )

        sample = await pipeline.generate_sample(0, {"input": "What is 1+1?", "expected": "2"})

    assert len(captured_calls) == 1
    assert captured_calls[0]["url"] == "http://generic-agent.test:9090/run"
    assert sample["output_text"] == "2"
    assert sample["response"]["trajectory"] == [{"step": "compute", "content": "1+1=2"}]
