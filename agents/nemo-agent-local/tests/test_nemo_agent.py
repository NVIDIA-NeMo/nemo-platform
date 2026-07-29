# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import yaml
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from nat.data_models.api_server import ChatRequest
from nemo_agent.register import (
    DEFAULT_RECURSION_LIMIT,
    SKILLS_DIR,
    _active_workspace,
    _delete_fileset,
    _direct_fileset_delete_name,
    _direct_list_resource,
    _disable_nat_method_retries,
    _get_client,
    _get_model,
    _list_resource_names,
    _parse_studio_callback_response,
    _resolve_resource,
    _serialize,
    _StreamSafeGraph,
    _studio_callback_url,
    check_status,
    create_nemo_agent,
    nemo_api,
)
from nemo_agent.wrapper import NemoAgentWrapperConfig, NemoAgentWrapperFunction, NemoAgentWrapperOutput
from pydantic import BaseModel

# The underlying functions wrapped by langchain's @tool decorator.
# ty doesn't resolve StructuredTool's .invoke() or .func attributes
# through the @tool decorator, so we call the functions directly.
_nemo_api = nemo_api.func  # ty: ignore[unresolved-attribute]
_check_status = check_status.func  # ty: ignore[unresolved-attribute]

AGENT_CONFIG = Path(__file__).parents[1] / "src" / "nemo_agent" / "nemo-agent.yml"
TRUSTED_SESSION_ID = "00000000-0000-4000-8000-000000000001"
TRUSTED_CONFIG = {"configurable": {"studio_session_id": TRUSTED_SESSION_ID}}


class TestAgentConfig:
    def test_uses_requested_model_without_telemetry(self):
        config = yaml.safe_load(AGENT_CONFIG.read_text(encoding="utf-8"))

        assert config["llms"]["agent"]["model_name"] == "nvidia-nemotron-3-super-120b-a12b"
        assert config["llms"]["agent"]["do_auto_retry"] is False
        assert config["llms"]["agent"]["num_retries"] == 1
        assert config["llms"]["agent"]["retry_on_status_codes"] == [599]
        assert config["llms"]["agent"]["retry_on_errors"] == ["__never_retry__"]
        assert config["llms"]["agent"]["max_retries"] == 0
        assert config["llms"]["agent"]["request_timeout"] == 120
        assert "general" not in config


class FakeWorkspace(BaseModel):
    id: str = "ws-001"
    name: str = "test-workspace"
    description: str = "A test workspace"


class FakeProvider(BaseModel):
    name: str = "nvidia-build"
    host_url: str = "https://integrate.api.nvidia.com"


class FakeJobStatus(BaseModel):
    name: str = "job-123"
    status: str = "running"


@pytest.fixture
def mock_client():
    """NeMoPlatform mock with realistic resource structure."""
    client = MagicMock()

    client.workspaces.create.return_value = FakeWorkspace()
    client.workspaces.list.return_value = [FakeWorkspace(), FakeWorkspace(name="other")]
    client.workspaces.retrieve.return_value = FakeWorkspace()
    client.workspaces.delete.return_value = None

    client.inference.providers.list.return_value = [FakeProvider()]
    client.inference.providers.create.return_value = FakeProvider()

    client.evaluation.metric_jobs.get_status.return_value = FakeJobStatus()
    client.evaluation.metric_jobs.get_logs.return_value = "log line 1\nlog line 2"

    return client


# ---------------------------------------------------------------------------
# _serialize
# ---------------------------------------------------------------------------


class TestSerialize:
    def test_pydantic_model(self):
        result = _serialize(FakeWorkspace())
        assert isinstance(result, dict)
        assert result["name"] == "test-workspace"
        assert result["id"] == "ws-001"

    def test_list_of_models(self):
        result = _serialize([FakeWorkspace(), FakeProvider()])
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "test-workspace"
        assert result[1]["name"] == "nvidia-build"

    def test_plain_dict_passthrough(self):
        d = {"key": "value", "nested": {"a": 1}}
        assert _serialize(d) == d

    @pytest.mark.parametrize("value", ["hello", 42, 3.14, True, None])
    def test_primitives_passthrough(self, value):
        assert _serialize(value) is value or _serialize(value) == value

    def test_unknown_object_str_fallback(self):
        class Opaque:
            def __str__(self):
                return "opaque-repr"

        assert _serialize(Opaque()) == "opaque-repr"


# ---------------------------------------------------------------------------
# _resolve_resource
# ---------------------------------------------------------------------------


class TestResolveResource:
    @pytest.mark.parametrize(
        "path,expected_attr",
        [
            ("workspaces", "workspaces"),
            ("inference.providers", "inference.providers"),
            ("evaluation.metric_jobs", "evaluation.metric_jobs"),
        ],
    )
    def test_resolve_paths(self, mock_client, path, expected_attr):
        result = _resolve_resource(mock_client, path)
        expected = mock_client
        for part in expected_attr.split("."):
            expected = getattr(expected, part)
        assert result is expected

    def test_invalid_path_raises(self):
        client = MagicMock(spec=["workspaces", "inference", "evaluation"])
        with pytest.raises(AttributeError):
            _resolve_resource(client, "nonexistent")


# ---------------------------------------------------------------------------
# nemo_api tool
# ---------------------------------------------------------------------------


class TestNemoApiTool:
    def test_sdk_uses_deployment_platform_base_url(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://host.docker.internal:8080")
        monkeypatch.setenv("NMP_WORKSPACE", "developer-workspace")
        monkeypatch.delenv("NMP_AGENT_NAME", raising=False)
        monkeypatch.delenv("NEMO_BASE_URL", raising=False)

        with (
            patch("nemo_agent.register._client", None),
            patch("nemo_agent.register.NeMoPlatform") as platform_client,
        ):
            _get_client()

        platform_client.assert_called_once_with(
            base_url="http://host.docker.internal:8080",
            workspace="developer-workspace",
        )

    def test_sdk_defaults_to_default_workspace(self, monkeypatch):
        monkeypatch.delenv("NMP_WORKSPACE", raising=False)

        with (
            patch("nemo_agent.register._client", None),
            patch("nemo_agent.register.NeMoPlatform") as platform_client,
        ):
            _get_client()

        assert _active_workspace() == "default"
        assert platform_client.call_args.kwargs["workspace"] == "default"

    def test_workspace_create(self, mock_client):
        with (
            patch("nemo_agent.register._get_client", return_value=mock_client),
            patch(
                "nemo_agent.register._call_studio_tool",
                return_value={"behavior": "allow"},
            ),
        ):
            result = _nemo_api(
                resource="workspaces",
                action="create",
                config=TRUSTED_CONFIG,
                params='{"name": "new-ws"}',
            )
        mock_client.workspaces.create.assert_called_once_with(name="new-ws")
        assert "test-workspace" in str(result)

    def test_workspace_list(self, mock_client):
        with patch("nemo_agent.register._get_client", return_value=mock_client):
            result = _nemo_api(
                resource="workspaces",
                action="list",
                config={},
            )
        mock_client.workspaces.list.assert_called_once()
        assert isinstance(result, str)

    def test_nested_resource(self, mock_client):
        with patch("nemo_agent.register._get_client", return_value=mock_client):
            _nemo_api(
                resource="inference.providers",
                action="list",
                config={},
            )
        mock_client.inference.providers.list.assert_called_once()

    def test_studio_mutation_requires_approval(self, mock_client):
        with (
            patch("nemo_agent.register._get_client", return_value=mock_client),
            patch(
                "nemo_agent.register._call_studio_tool",
                return_value={"behavior": "deny", "message": "not now"},
            ) as studio_tool,
        ):
            result = _nemo_api(
                resource="workspaces",
                action="create",
                config=TRUSTED_CONFIG,
                params='{"name": "blocked"}',
            )

        assert result == "Denied by user: not now"
        mock_client.workspaces.create.assert_not_called()
        studio_tool.assert_called_once_with(
            TRUSTED_SESSION_ID,
            "approval_prompt",
            {
                "tool_name": "nemo_api",
                "input": {
                    "resource": "workspaces",
                    "action": "create",
                    "params": '{"name": "blocked"}',
                },
            },
        )

    def test_mutation_without_trusted_session_is_denied(self, mock_client):
        with patch("nemo_agent.register._get_client", return_value=mock_client):
            result = _nemo_api(
                resource="workspaces",
                action="create",
                config={},
                params='{"name": "blocked"}',
            )

        assert result == "Denied: mutating operations require a trusted Studio approval context"
        mock_client.workspaces.create.assert_not_called()

    def test_model_tool_schema_does_not_expose_approval_context(self):
        assert "studio_session_id" not in nemo_api.args_schema.model_fields
        assert "config" not in nemo_api.args_schema.model_fields

    def test_studio_callback_uses_deployment_reachable_base_url(self, monkeypatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://host.docker.internal:8080/")
        monkeypatch.setenv("NMP_WORKSPACE", "developer-workspace")

        assert _studio_callback_url(
            "session-id",
            studio_base_url="https://studio.example/studio",
        ) == (
            "http://host.docker.internal:8080/studio/api/coding-agents/mcp/session-id"
            "?workspace=developer-workspace&studio_base_url=https%3A%2F%2Fstudio.example%2Fstudio"
        )

    def test_studio_callback_parses_blocking_sse_result(self):
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=(
                ": keepalive\n\n"
                'event: message\ndata: {"jsonrpc":"2.0","id":"1","result":{"content":'
                '[{"type":"text","text":"{\\"status\\": \\"submitted\\", \\"agent\\": \\"demo\\"}"}]}}\n\n'
            ),
            request=httpx.Request("POST", "http://studio.test/callback"),
        )

        assert _parse_studio_callback_response(response) == {
            "status": "submitted",
            "agent": "demo",
        }


# ---------------------------------------------------------------------------
# check_status tool
# ---------------------------------------------------------------------------


class TestCheckStatusTool:
    def test_evaluation_job_status(self, mock_client):
        with patch("nemo_agent.register._get_client", return_value=mock_client):
            result = _check_status(
                service="evaluation",
                job_name="job-123",
            )
        assert "running" in result.lower() or "job-123" in result

    def test_falls_through_to_next_method(self, mock_client):
        """If the first status method raises, the next one should be tried."""
        mock_client.evaluation.metric_jobs.get_status.side_effect = Exception("not found")
        mock_client.evaluation.benchmark_jobs.get_status.return_value = FakeJobStatus(
            name="job-456", status="completed"
        )
        with patch("nemo_agent.register._get_client", return_value=mock_client):
            result = _check_status(service="evaluation", job_name="job-456")
        assert "completed" in result.lower()


# ---------------------------------------------------------------------------
# Agent graph creation and model selection
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm():
    """Provide a mock LLM via NAT's SyncBuilder context."""
    llm = MagicMock()
    builder = MagicMock()
    builder.get_llm.return_value = llm
    with patch("nat.builder.sync_builder.SyncBuilder") as mock_sync:
        mock_sync.current.return_value = builder
        yield llm


class TestGetModel:
    def test_returns_llm_from_builder(self, mock_llm):
        model = _get_model()
        assert model is mock_llm

    def test_raises_without_builder_context(self):
        with patch("nat.builder.sync_builder.SyncBuilder") as mock_sync:
            mock_sync.current.side_effect = ValueError("no builder context")
            with pytest.raises(ValueError, match="no builder context"):
                _get_model()

    @pytest.mark.asyncio
    async def test_disables_nat_automatic_retry_wrapper(self):
        from nat.utils.exception_handlers.automatic_retries import patch_with_retry

        class FailingModel:
            def __init__(self):
                self.calls = 0

            async def ainvoke(self, messages):
                return await self.agenerate(messages)

            async def agenerate(self, messages):
                self.calls += 1
                raise RuntimeError("429 Too Many Requests")

        model = patch_with_retry(
            FailingModel(),
            retries=5,
            retry_codes=[429],
        )

        _disable_nat_method_retries(model)
        with pytest.raises(RuntimeError, match="429"):
            await model.ainvoke([])

        assert model.calls == 1


class TestAgentGraph:
    @pytest.fixture
    def mock_graph(self, mock_llm):
        """Mock create_deep_agent to return a fake CompiledStateGraph."""
        fake_graph = MagicMock()
        fake_graph.nodes = {"tools": MagicMock(bound=MagicMock(tools_by_name={"nemo_api": 1, "check_status": 1}))}
        with patch("nemo_agent.register.create_deep_agent", return_value=fake_graph):
            yield fake_graph

    def test_create_agent_returns_stream_safe_graph(self, mock_graph):
        from nemo_agent.register import _StreamSafeGraph

        graph = create_nemo_agent()
        assert isinstance(graph, _StreamSafeGraph)

    def test_stream_safe_graph_delegates_attribute_access(self, mock_graph):
        graph = create_nemo_agent()
        _ = graph.nodes
        assert mock_graph.nodes is not None

    @pytest.mark.asyncio
    async def test_stream_safe_graph_forwards_incremental_chunks(self):
        from nemo_agent.register import _StreamSafeGraph

        class StreamingGraph:
            def __init__(self):
                self.calls = []

            async def astream(self, input_data, config=None, **kwargs):
                self.calls.append((input_data, config, kwargs))
                yield {"skills_metadata": []}
                yield {"agent": {"messages": [AIMessage(content="done")]}}

        inner = StreamingGraph()
        graph = _StreamSafeGraph(inner)

        chunks = [
            chunk
            async for chunk in graph.astream(
                {"messages": [HumanMessage(content="perform a complex benchmark task")]},
                config={"recursion_limit": 4},
                stream_mode="updates",
            )
        ]

        assert chunks == [
            {"skills_metadata": []},
            {"agent": {"messages": [AIMessage(content="done")]}},
        ]
        assert inner.calls[0][1] == {"recursion_limit": 4}
        assert inner.calls[0][2] == {"stream_mode": "updates"}

    @pytest.mark.asyncio
    async def test_stream_safe_graph_defaults_to_assistant_message_chunks(self):
        from nemo_agent.register import _StreamSafeGraph

        class MessageStreamingGraph:
            def __init__(self):
                self.calls = []

            async def astream(self, input_data, config=None, **kwargs):
                self.calls.append((input_data, config, kwargs))
                yield AIMessageChunk(content="danielle"), {"langgraph_node": "model"}
                yield (
                    ToolMessage(content='{"data": "private tool result"}', tool_call_id="call-1"),
                    {"langgraph_node": "tools"},
                )
                yield AIMessageChunk(content="ali"), {"langgraph_node": "model"}

        inner = MessageStreamingGraph()
        graph = _StreamSafeGraph(inner)

        chunks = [
            chunk
            async for chunk in graph.astream({"messages": [HumanMessage(content="perform a complex benchmark task")]})
        ]

        assert chunks == [
            {"messages": [AIMessageChunk(content="danielle")]},
            {"messages": [AIMessageChunk(content="ali")]},
        ]
        assert inner.calls[0][1] == {"recursion_limit": DEFAULT_RECURSION_LIMIT}
        assert inner.calls[0][2] == {"stream_mode": "messages"}

    @pytest.mark.asyncio
    async def test_stream_safe_graph_bounds_non_streaming_invocations(self):
        class InvokeGraph:
            def __init__(self):
                self.calls = []

            async def ainvoke(self, input_data, config=None, **kwargs):
                self.calls.append((input_data, config, kwargs))
                return {"messages": [AIMessage(content="done")]}

        inner = InvokeGraph()
        graph = _StreamSafeGraph(inner)

        result = await graph.ainvoke({"messages": [HumanMessage(content="perform a complex task")]})

        assert result == {"messages": [AIMessage(content="done")]}
        assert inner.calls[0][1] == {"recursion_limit": DEFAULT_RECURSION_LIMIT}

    def test_agent_has_expected_tools(self, mock_graph):
        create_nemo_agent()

        from nemo_agent.register import create_deep_agent

        tools = create_deep_agent.call_args.kwargs["tools"]
        tool_names = {agent_tool.name for agent_tool in tools}
        assert tool_names == {
            "nemo_api",
            "check_status",
            "select_agent",
            "select_model",
            "select_dataset_file",
            "select_eval_config",
            "job_progress",
            "studio_link",
        }

    def test_skills_dir_exists(self):
        assert SKILLS_DIR.name == "skills"

    def test_create_agent_passes_backend_visible_skills(self, mock_graph):
        from deepagents.middleware.skills import _list_skills_with_errors  # ty: ignore[unresolved-import]

        graph = create_nemo_agent()
        assert graph is not None

        from nemo_agent.register import create_deep_agent

        kwargs = create_deep_agent.call_args.kwargs
        assert kwargs["skills"] == [str(SKILLS_DIR)]

        skills, error = _list_skills_with_errors(kwargs["backend"], str(SKILLS_DIR))
        assert error is None
        assert len(skills) > 0


class TestDirectListFastPath:
    @pytest.mark.parametrize(
        ("prompt", "resource_path"),
        [
            ("List the available workspaces. Return only their names.", "workspaces"),
            ("What models are available?", "models"),
            ("Show filesets", "files.filesets"),
        ],
    )
    def test_safe_list_requests_resolve_to_sdk_resources(self, prompt, resource_path):
        assert _direct_list_resource([HumanMessage(content=prompt)]) == resource_path

    @pytest.mark.parametrize(
        "prompt",
        [
            "Create a workspace",
            "List agents and deploy one",
            "Explain why this deployment is slow",
            "Audit the available skills",
            "Check the deployment status",
            "Hello",
        ],
    )
    def test_unsupported_or_complex_requests_fall_back_to_agent(self, prompt):
        assert _direct_list_resource([HumanMessage(content=prompt)]) is None

    def test_list_resource_names_returns_only_names(self):
        resource = MagicMock()
        resource.list.return_value = [FakeWorkspace(name="danielleali"), FakeWorkspace(name="default")]

        with patch("nemo_agent.register._resolve_resource", return_value=resource):
            result = _list_resource_names("workspaces")

        assert result == "danielleali\ndefault"

    def test_list_resource_names_asks_for_workspace_instead_of_falling_back(self):
        resource = MagicMock()
        resource.list.side_effect = ValueError("Missing workspace argument")

        with patch("nemo_agent.register._resolve_resource", return_value=resource):
            result = _list_resource_names("files.filesets")

        assert result == "Which workspace should I use to list filesets?"

    @pytest.mark.asyncio
    async def test_stream_graph_bypasses_model_for_direct_list(self):
        inner = MagicMock()
        graph = _StreamSafeGraph(inner)

        with patch("nemo_agent.register._list_resource_names", return_value="danielleali\nsystem\ndefault"):
            chunks = [
                chunk
                async for chunk in graph.astream(
                    {"messages": [HumanMessage(content="List available workspaces. Return only their names.")]}
                )
            ]

        assert chunks == [{"messages": [AIMessageChunk(content="danielleali\nsystem\ndefault")]}]
        inner.astream.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_graph_does_not_fall_back_after_direct_list_failure(self):
        inner = MagicMock()
        graph = _StreamSafeGraph(inner)

        with patch(
            "nemo_agent.register._list_resource_names",
            return_value="Which workspace should I use to list filesets?",
        ):
            chunks = [
                chunk
                async for chunk in graph.astream({"messages": [HumanMessage(content="List all my current filesets")]})
            ]

        assert chunks == [{"messages": [AIMessageChunk(content="Which workspace should I use to list filesets?")]}]
        inner.astream.assert_not_called()


class TestDirectFilesetDeleteFastPath:
    @pytest.mark.parametrize(
        ("prompt", "expected_name"),
        [
            ("Delete phishing_dataset fileset", "phishing_dataset"),
            ("Can you delete the phishing_dataset fileset?", "phishing_dataset"),
            ("Please delete my-files.v2 fileset.", "my-files.v2"),
        ],
    )
    def test_explicit_single_fileset_deletes_are_recognized(self, prompt, expected_name):
        assert _direct_fileset_delete_name([HumanMessage(content=prompt)]) == expected_name

    @pytest.mark.parametrize(
        "prompt",
        [
            "Delete the fileset",
            "Delete phishing_dataset",
            "Delete every fileset",
            "Can you delete phishing_dataset and another fileset?",
        ],
    )
    def test_ambiguous_or_broad_deletes_are_not_recognized(self, prompt):
        assert _direct_fileset_delete_name([HumanMessage(content=prompt)]) is None

    def test_delete_fileset_executes_once_and_verifies_absence(self):
        resource = MagicMock()
        resource.list.return_value = [FakeWorkspace(name="other-fileset")]

        with patch("nemo_agent.register._resolve_resource", return_value=resource):
            result = _delete_fileset("phishing_dataset")

        resource.delete.assert_called_once_with(name="phishing_dataset")
        resource.list.assert_called_once_with()
        assert result == "Deleted fileset 'phishing_dataset' from workspace 'default'."

    def test_delete_fileset_reports_failure_without_model_fallback(self):
        resource = MagicMock()
        resource.delete.side_effect = RuntimeError("service unavailable")

        with patch("nemo_agent.register._resolve_resource", return_value=resource):
            result = _delete_fileset("phishing_dataset")

        assert "I couldn't delete fileset 'phishing_dataset'" in result
        assert "service unavailable" in result

    def test_delete_fileset_without_studio_session_retains_direct_behavior(self):
        resource = MagicMock()
        resource.list.return_value = []

        with patch("nemo_agent.register._resolve_resource", return_value=resource):
            result = _delete_fileset("phishing_dataset")

        assert result == "Deleted fileset 'phishing_dataset' from workspace 'default'."
        resource.delete.assert_called_once_with(name="phishing_dataset")

    @pytest.mark.asyncio
    async def test_stream_graph_requires_studio_approval_before_direct_fileset_delete(self):
        inner = MagicMock()
        graph = _StreamSafeGraph(inner)

        with (
            patch(
                "nemo_agent.register._delete_fileset",
                return_value="Deleted fileset 'phishing_dataset' from workspace 'default'.",
            ) as delete_fileset,
            patch(
                "nemo_agent.register._call_studio_tool",
                return_value={"behavior": "allow"},
            ) as studio_tool,
        ):
            chunks = [
                chunk
                async for chunk in graph.astream(
                    {"messages": [HumanMessage(content="Can you delete the phishing_dataset fileset?")]},
                    config=TRUSTED_CONFIG,
                )
            ]

        assert chunks == [
            {"messages": [AIMessageChunk(content="Deleted fileset 'phishing_dataset' from workspace 'default'.")]}
        ]
        studio_tool.assert_called_once_with(
            TRUSTED_SESSION_ID,
            "approval_prompt",
            {
                "tool_name": "nemo_api",
                "input": {
                    "resource": "files.filesets",
                    "action": "delete",
                    "params": '{"name": "phishing_dataset"}',
                },
            },
        )
        delete_fileset.assert_called_once_with("phishing_dataset")
        inner.astream.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_graph_stops_when_studio_denies_direct_fileset_delete(self):
        inner = MagicMock()
        graph = _StreamSafeGraph(inner)

        with (
            patch("nemo_agent.register._delete_fileset") as delete_fileset,
            patch(
                "nemo_agent.register._call_studio_tool",
                return_value={"behavior": "deny", "message": "not now"},
            ),
        ):
            chunks = [
                chunk
                async for chunk in graph.astream(
                    {"messages": [HumanMessage(content="Delete phishing_dataset fileset")]},
                    config=TRUSTED_CONFIG,
                )
            ]

        assert chunks == [{"messages": [AIMessageChunk(content="Denied by user: not now")]}]
        delete_fileset.assert_not_called()
        inner.astream.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_graph_without_studio_session_rejects_direct_fileset_delete(self):
        inner = MagicMock()
        graph = _StreamSafeGraph(inner)

        with (
            patch(
                "nemo_agent.register._delete_fileset",
                return_value="Deleted fileset 'phishing_dataset' from workspace 'default'.",
            ) as delete_fileset,
            patch("nemo_agent.register._call_studio_tool") as studio_tool,
        ):
            chunks = [
                chunk
                async for chunk in graph.astream(
                    {"messages": [HumanMessage(content="Delete phishing_dataset fileset")]},
                )
            ]

        assert chunks == [
            {
                "messages": [
                    AIMessageChunk(content="Denied: mutating operations require a trusted Studio approval context")
                ]
            }
        ]
        studio_tool.assert_not_called()
        delete_fileset.assert_not_called()
        inner.astream.assert_not_called()


class FakeWrapperGraph:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.inputs = []
        self.configs = []

    async def ainvoke(self, state, config=None):
        self.inputs.append(state)
        self.configs.append(config)
        return self.outputs.pop(0)


class FailingStreamingGraph:
    def __init__(self, error):
        self.error = error

    async def astream(self, state, config=None):
        if False:
            yield state
        raise self.error


class TestNemoAgentWrapper:
    @pytest.mark.parametrize(
        ("messages", "expected"),
        [
            ([], ""),
            ([AIMessage(content="base message")], "base message"),
            ([{"role": "assistant", "content": "dict message"}], "dict message"),
        ],
    )
    def test_convert_to_str_normalizes_message_representations(self, messages, expected):
        output = NemoAgentWrapperOutput.model_construct(messages=messages)

        assert NemoAgentWrapperFunction.convert_to_str(output) == expected

    def test_chat_request_converts_trusted_session_to_invocation_config(self):
        request = ChatRequest.model_validate(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "studio_session_id": TRUSTED_SESSION_ID,
            }
        )

        value = NemoAgentWrapperFunction.convert_chat_request(request)

        assert NemoAgentWrapperFunction._invocation_config(value) == TRUSTED_CONFIG

    @pytest.mark.asyncio
    async def test_wrapper_passes_trusted_session_config_to_graph(self):
        graph = FakeWrapperGraph([{"messages": [AIMessage(content="done")]}])
        wrapper = NemoAgentWrapperFunction(config=NemoAgentWrapperConfig(), graph=graph)
        value = wrapper.convert_chat_request(
            ChatRequest.model_validate(
                {
                    "messages": [{"role": "user", "content": "hello"}],
                    "studio_session_id": TRUSTED_SESSION_ID,
                }
            )
        )

        result = await wrapper._ainvoke(value)

        assert result.value == "done"
        assert graph.configs == [TRUSTED_CONFIG]

    @pytest.mark.parametrize(
        "message",
        [
            ToolMessage(content='{"secret": "tool result"}', tool_call_id="call-1"),
            {"role": "tool", "content": '{"secret": "tool result"}'},
            {"type": "tool", "content": '{"secret": "tool result"}'},
        ],
    )
    def test_stream_value_hides_tool_messages(self, message):
        output = NemoAgentWrapperFunction._parse({"messages": [message]})

        assert output.value == ""
        assert NemoAgentWrapperFunction.convert_to_chat_response_chunk(output).choices[0].delta.content == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error,expected",
        [
            (RuntimeError("upstream returned 429 Too Many Requests"), "temporarily rate-limited"),
            (TimeoutError("request timed out"), "timed out"),
            (RuntimeError("connection reset"), "returned an error"),
        ],
    )
    async def test_stream_failure_emits_visible_terminal_message(self, error, expected):
        wrapper = NemoAgentWrapperFunction(
            config=NemoAgentWrapperConfig(),
            graph=FailingStreamingGraph(error),
        )

        outputs = [output async for output in wrapper._astream(wrapper.convert_str("test"))]

        assert len(outputs) == 1
        assert expected in outputs[0].value

    @pytest.mark.asyncio
    async def test_empty_final_response_prompts_continuation(self):
        graph = FakeWrapperGraph(
            [
                {"messages": [HumanMessage(content="do task"), AIMessage(content="")]},
                {"messages": [AIMessage(content="completed")]},
            ]
        )
        wrapper = NemoAgentWrapperFunction(config=NemoAgentWrapperConfig(), graph=graph)

        result = await wrapper._ainvoke_with_empty_response_retry({"messages": [HumanMessage(content="do task")]})

        assert result.value == "completed"
        assert len(graph.inputs) == 2
        retry_messages = graph.inputs[1]["messages"]
        assert retry_messages[:-1] == [HumanMessage(content="do task")]
        assert isinstance(retry_messages[-1], HumanMessage)
        assert "previous assistant response was empty" in retry_messages[-1].content
        assert all(not (isinstance(message, AIMessage) and not message.content) for message in retry_messages)

    @pytest.mark.asyncio
    async def test_empty_final_response_retry_falls_back_to_original_state(self):
        graph = FakeWrapperGraph(
            [
                {"messages": [AIMessage(content="")]},
                {"messages": [AIMessage(content="completed")]},
            ]
        )
        wrapper = NemoAgentWrapperFunction(config=NemoAgentWrapperConfig(), graph=graph)

        result = await wrapper._ainvoke_with_empty_response_retry({"messages": [HumanMessage(content="do task")]})

        assert result.value == "completed"
        retry_messages = graph.inputs[1]["messages"]
        assert retry_messages[:-1] == [HumanMessage(content="do task")]
        assert all(not (isinstance(message, AIMessage) and not message.content) for message in retry_messages)

    @pytest.mark.asyncio
    async def test_empty_final_response_retry_preserves_tool_call_messages(self):
        tool_call_message = AIMessage(
            content="",
            tool_calls=[{"name": "nemo_api", "args": {"resource": "workspaces"}, "id": "call-1"}],
        )
        graph = FakeWrapperGraph(
            [
                {"messages": [HumanMessage(content="do task"), tool_call_message, AIMessage(content="")]},
                {"messages": [AIMessage(content="completed")]},
            ]
        )
        wrapper = NemoAgentWrapperFunction(config=NemoAgentWrapperConfig(), graph=graph)

        result = await wrapper._ainvoke_with_empty_response_retry({"messages": [HumanMessage(content="do task")]})

        assert result.value == "completed"
        retry_messages = graph.inputs[1]["messages"]
        assert retry_messages[1] is tool_call_message
        assert retry_messages[-2] is tool_call_message
        assert isinstance(retry_messages[-1], HumanMessage)

    @pytest.mark.asyncio
    async def test_non_empty_final_response_does_not_retry(self):
        graph = FakeWrapperGraph([{"messages": [AIMessage(content="completed")]}])
        wrapper = NemoAgentWrapperFunction(config=NemoAgentWrapperConfig(), graph=graph)

        result = await wrapper._ainvoke_with_empty_response_retry({"messages": [HumanMessage(content="do task")]})

        assert result.value == "completed"
        assert len(graph.inputs) == 1
