# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import inspect
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import ResourceRef, TrialResult
from nemo_platform import AsyncNeMoPlatform
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = PLUGIN_ROOT / "examples" / "tau3-nooa-agent"
RUNNER_PATH = AGENT_ROOT / "run_airline_insights.py"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tau3_nooa_insights_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_agent() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tau3_nooa_agent", AGENT_ROOT / "agent.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_stop_aware_mcp_manager_exits_on_tau3_stop_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEMO_AGENT_TRACE_DIR", str(tmp_path / "traces"))
    agent = _load_agent()

    class FakeManager:
        async def send_message_to_user(self) -> str:
            return "The user is finished. ###STOP###"

        async def domain_tool(self, reservation_id: str) -> str:
            """Cancel a reservation by ID."""
            return "Conversation has already ended with reason 'max_steps'."

    manager = agent.StopAwareMCPManager(FakeManager())

    assert "domain_tool" in dir(manager)
    assert inspect.signature(manager.domain_tool) == inspect.signature(FakeManager().domain_tool)
    assert inspect.getdoc(manager.domain_tool) == "Cancel a reservation by ID."
    with pytest.raises(agent.ConversationEnded):
        await manager.send_message_to_user()
    with pytest.raises(agent.ConversationEnded):
        await manager.domain_tool("ABC123")


def test_configure_models_exports_tau3_runtime_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()
    monkeypatch.setenv("INFERENCE_API_KEY", "key-123")
    monkeypatch.setenv("OPENAI_API_KEY", "stale-key")
    monkeypatch.setenv("TAU2_USER_MODEL", "stale-model")

    runner._configure_models(
        model="openai/agent-model",
        user_model="openai/user-model",
        api_base="https://inference.example/v1/",
    )

    assert runner.os.environ["OPENAI_API_KEY"] == "key-123"
    assert runner.os.environ["OPENAI_BASE_URL"] == "https://inference.example/v1"
    assert runner.os.environ["AUT_MODEL_NAME"] == "openai/agent-model"
    assert runner.os.environ["TAU2_USER_MODEL"] == "openai/user-model"
    assert runner.os.environ["TAU2_NL_ASSERTIONS_MODEL"] == "openai/user-model"


@pytest.mark.asyncio
async def test_upload_trials_sends_only_trace_with_correlation_metadata(tmp_path: Path) -> None:
    runner = _load_runner()
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "resourceSpans": [
                    {
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "traceId": "0123456789abcdef0123456789abcdef",
                                        "spanId": "0123456789abcdef",
                                        "name": "agent",
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trial = TrialResult(
        id="tau3-airline-0__0",
        task_id="tau3-airline-0",
        attempt=0,
        status="completed",
        trace=ResourceRef(uri=trace_path.as_uri()),
    )

    class FakeClient:
        def __init__(self) -> None:
            self.posts: list[dict[str, Any]] = []

        async def post(self, url: str, **kwargs: Any) -> None:
            self.posts.append({"url": url, **kwargs})

    fake_client = FakeClient()
    trace_ids = await runner._upload_trials(
        cast(AsyncNeMoPlatform, fake_client),
        [trial],
        workspace="tau3-airline",
        experiment_id="experiment-1",
        agent_name="agent-name",
        agent_version="1.2.3",
        model="model-name",
    )

    assert trace_ids == {"tau3-airline-0__0": "0123456789abcdef0123456789abcdef"}
    assert len(fake_client.posts) == 1
    assert fake_client.posts[0]["url"].endswith("/workspaces/tau3-airline/ingest/otlp/v1/traces")

    request = ExportTraceServiceRequest()
    request.ParseFromString(fake_client.posts[0]["content"])
    attrs = {
        attr.key: attr.value.string_value
        for resource_spans in request.resource_spans
        for attr in resource_spans.resource.attributes
    }
    assert attrs == {
        "nemo.experiment.id": "experiment-1",
        "nemo.test_case.id": "tau3-airline-0",
        "nemo.trial.id": "tau3-airline-0__0",
        "gen_ai.agent.name": "agent-name",
        "gen_ai.agent.version": "1.2.3",
        "gen_ai.request.model": "model-name",
    }
