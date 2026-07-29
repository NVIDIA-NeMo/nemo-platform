# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import logging
import os
import re
import types
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from deepagents import create_deep_agent  # ty: ignore[unresolved-import]
from deepagents.backends import (  # ty: ignore[unresolved-import]
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from nemo_platform import NeMoPlatform
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a NeMo Platform assistant executing benchmark tasks.

Complete every numbered requirement in the user instruction before returning.
Do not return a plan or instructions for a human to run. Execute the required
operations yourself with available tools, then report concise results.

Do not claim tools are insufficient until you have attempted reasonable
equivalent operations with `nemo_api`. Use `check_status` for platform jobs
and deployments. Do not attempt to invoke the NeMo CLI or other subprocesses.

Use the deployment's active workspace unless the user explicitly names another
one. If a required workspace, resource name, target, or consequential parameter
is missing or ambiguous, ask one focused clarification question and stop. Do
not repeat the same failing tool call or guess a destructive target.
"""
SKILLS_DIR = Path(__file__).parent / "skills"
DEFAULT_WORKSPACE = "default"
DEFAULT_RECURSION_LIMIT = 24
STUDIO_CALLBACK_PATH = "/studio/api/coding-agents/mcp/{session_id}"
STUDIO_CALLBACK_TIMEOUT_SECONDS = 3600.0
_READ_ONLY_SDK_ACTIONS = frozenset(
    {
        "get",
        "get_logs",
        "get_status",
        "list",
        "read",
        "retrieve",
        "search",
    }
)

_DIRECT_LIST_REQUEST = re.compile(r"^\s*(list|show|what|which)\b|\bavailable\b", re.IGNORECASE)
_DIRECT_FILESET_DELETE = re.compile(
    r"^\s*(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
    r"delete\s+(?:the\s+)?(?P<name>[a-z0-9][a-z0-9._-]*)\s+fileset\s*[?.!]?\s*$",
    re.IGNORECASE,
)
_FAST_PATH_MUTATION = re.compile(
    r"\b("
    r"add|cancel|create|delete|deploy|edit|evaluate|invoke|optimi[sz]e|"
    r"remove|run|set|submit|undeploy|update|upload|write"
    r")\b",
    re.IGNORECASE,
)
_FAST_PATH_ANALYSIS = re.compile(r"\b(analy[sz]e|audit|compare|explain|investigate|why)\b", re.IGNORECASE)
_DIRECT_LIST_RESOURCES = (
    (re.compile(r"\bworkspaces?\b", re.IGNORECASE), "workspaces"),
    (re.compile(r"\bmodels?\b", re.IGNORECASE), "models"),
    (re.compile(r"\bproviders?\b", re.IGNORECASE), "inference.providers"),
    (re.compile(r"\bfilesets?\b", re.IGNORECASE), "files.filesets"),
    (re.compile(r"\bdatasets?\b", re.IGNORECASE), "datasets"),
    (re.compile(r"\bbenchmarks?\b", re.IGNORECASE), "evaluation.benchmarks"),
    (re.compile(r"\bmetrics?\b", re.IGNORECASE), "evaluation.metrics"),
)

_client: NeMoPlatform | None = None


def _latest_user_text(messages: list[Any]) -> str:
    latest_user_text = ""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            latest_user_text = message.text
            break
    return latest_user_text


def _direct_list_resource(messages: list[Any]) -> str | None:
    """Resolve safe list-by-name requests to a known SDK resource."""
    latest_user_text = _latest_user_text(messages)
    if not latest_user_text or not _DIRECT_LIST_REQUEST.search(latest_user_text):
        return None
    if _FAST_PATH_MUTATION.search(latest_user_text) or _FAST_PATH_ANALYSIS.search(latest_user_text):
        return None
    for pattern, resource_path in _DIRECT_LIST_RESOURCES:
        if pattern.search(latest_user_text):
            return resource_path
    return None


def _direct_fileset_delete_name(messages: list[Any]) -> str | None:
    """Resolve an explicit single-fileset deletion request."""
    latest_user_text = _latest_user_text(messages)
    if not latest_user_text:
        return None
    match = _DIRECT_FILESET_DELETE.fullmatch(latest_user_text)
    if match is None:
        return None
    name = match.group("name")
    if name.lower() in {"a", "all", "an", "every", "my", "the"}:
        return None
    return name


def _active_workspace() -> str:
    """Return the workspace injected by the deployment runtime."""
    return os.environ.get("NMP_WORKSPACE") or DEFAULT_WORKSPACE


def _direct_list_error(resource_path: str, exc: Exception) -> str:
    """Turn a recognized fast-path failure into a terminal user response."""
    resource_name = resource_path.rsplit(".", maxsplit=1)[-1]
    if isinstance(exc, ValueError) and "workspace" in str(exc).lower():
        return f"Which workspace should I use to list {resource_name}?"
    return f"I couldn't list {resource_name} in workspace '{_active_workspace()}': {type(exc).__name__}: {exc}"


def _list_resource_names(resource_path: str) -> str:
    """List one SDK resource and return names or a terminal actionable error."""
    try:
        resource = _resolve_resource(_get_client(), resource_path)
        serialized = _serialize(_call_sdk_method(resource, "list"))
    except Exception as exc:
        logger.exception("nemo-agent: direct list fast path failed for resource=%s", resource_path)
        return _direct_list_error(resource_path, exc)

    if isinstance(serialized, dict):
        serialized = serialized.get("data")
    if not isinstance(serialized, list):
        return f"I couldn't list {resource_path}: the platform returned an unexpected response."
    names = [item.get("name") for item in serialized if isinstance(item, dict) and isinstance(item.get("name"), str)]
    if not names:
        return f"No {resource_path.rsplit('.', maxsplit=1)[-1]} found in workspace '{_active_workspace()}'."
    logger.info("nemo-agent: direct list fast path resource=%s count=%d", resource_path, len(names))
    return "\n".join(names)


def _delete_fileset(name: str) -> str:
    """Delete one explicitly named fileset and verify that it is absent."""
    workspace = _active_workspace()
    try:
        resource = _resolve_resource(_get_client(), "files.filesets")
        _call_sdk_method(resource, "delete", {"name": name})
        serialized = _serialize(_call_sdk_method(resource, "list"))
    except Exception as exc:
        logger.exception("nemo-agent: direct fileset delete failed for name=%s", name)
        if isinstance(exc, ValueError) and "workspace" in str(exc).lower():
            return f"Which workspace should I use to delete fileset '{name}'?"
        return f"I couldn't delete fileset '{name}' in workspace '{workspace}': {type(exc).__name__}: {exc}"

    if isinstance(serialized, dict):
        serialized = serialized.get("data")
    if not isinstance(serialized, list):
        return (
            f"The delete request for fileset '{name}' completed, but I couldn't verify "
            f"the result in workspace '{workspace}'."
        )
    remaining_names = {
        item.get("name") for item in serialized if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if name in remaining_names:
        return f"I couldn't verify deletion: fileset '{name}' still exists in workspace '{workspace}'."

    logger.info("nemo-agent: direct fileset delete name=%s workspace=%s", name, workspace)
    return f"Deleted fileset '{name}' from workspace '{workspace}'."


def _get_client() -> NeMoPlatform:
    global _client
    if _client is None:
        base_url = os.environ.get("NMP_BASE_URL") or os.environ.get("NEMO_BASE_URL")
        kwargs: dict[str, Any] = {}
        if base_url:
            kwargs["base_url"] = base_url
        kwargs["workspace"] = _active_workspace()
        _client = NeMoPlatform(**kwargs)
    return _client


def _serialize(obj: Any) -> Any:
    """Convert SDK response objects to JSON-serializable form."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    return str(obj)


def _resolve_resource(client: NeMoPlatform, resource_path: str) -> Any:
    """Navigate a dot-separated path on the SDK client.

    Example: "inference.providers" -> client.inference.providers
    """
    current = client
    for part in resource_path.split("."):
        current = getattr(current, part)
    return current


def _call_sdk_method(resource: Any, action: str, params: dict[str, Any] | None = None) -> Any:
    method = getattr(resource, action)
    if params:
        return method(**params)
    return method()


def _trusted_studio_session_id(config: RunnableConfig) -> str | None:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    value = configurable.get("studio_session_id")
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _request_mutation_approval(
    config: RunnableConfig,
    *,
    tool_name: str,
    tool_input: dict[str, Any],
) -> str | None:
    session_id = _trusted_studio_session_id(config)
    if session_id is None:
        return "Denied: mutating operations require a trusted Studio approval context"
    approval = _call_studio_tool(
        session_id,
        "approval_prompt",
        {
            "tool_name": tool_name,
            "input": tool_input,
        },
    )
    if approval.get("behavior") != "allow":
        return f"Denied by user: {approval.get('message') or 'operation was not approved'}"
    return None


@tool
def nemo_api(
    resource: str,
    action: str,
    config: RunnableConfig,
    params: str | None = None,
) -> str:
    """Call any NeMo Platform SDK method.

    Args:
        resource: Dot-separated SDK resource path. Examples:
            workspaces, inference.providers, inference.deployments,
            evaluation.metrics, evaluation.metric_jobs,
            evaluation.benchmarks, evaluation.benchmark_jobs,
            files, files.filesets, guardrail, secrets, customization, audit,
            data_designer, models, datasets, inference.virtual_models
        action: Method to call on the resource. Common actions:
            create, list, retrieve, get, delete, update,
            get_status, get_logs, cancel, evaluate, upload_content
        params: JSON string of keyword arguments to pass. Example:
            '{"name": "my-workspace", "description": "test"}'
            '{"name": "my-secret", "value": "secret-payload"}'
            '{"content": "hello", "remote_path": "verify.txt", "fileset": "my-fileset"}'
        Useful paths:
            - Fileset CRUD: resource="files.filesets"
            - In-memory upload: resource="files", action="upload_content"
            - Secret CRUD: resource="secrets"

    Returns:
        JSON string of the result.
    """
    client = _get_client()
    try:
        normalized_action = action.strip().lower()
        if normalized_action not in _READ_ONLY_SDK_ACTIONS:
            denial = _request_mutation_approval(
                config,
                tool_name="nemo_api",
                tool_input={
                    "resource": resource,
                    "action": action,
                    "params": params,
                },
            )
            if denial is not None:
                return denial

        resolved = _resolve_resource(client, resource)
        parsed_params = json.loads(params) if params else None
        result = _call_sdk_method(resolved, action, parsed_params)
        return json.dumps(_serialize(result), indent=2, default=str)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


def _studio_callback_url(
    session_id: str,
    *,
    workspace: str | None = None,
    studio_base_url: str | None = None,
) -> str:
    """Build the Studio callback URL using the deployment-reachable platform origin."""
    base_url = (os.environ.get("NMP_BASE_URL") or os.environ.get("NEMO_BASE_URL") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("NMP_BASE_URL is required for Studio UI callbacks")

    query = {
        key: value
        for key, value in {
            "workspace": workspace or _active_workspace(),
            "studio_base_url": studio_base_url,
        }.items()
        if value
    }
    url = f"{base_url}{STUDIO_CALLBACK_PATH.format(session_id=session_id)}"
    return f"{url}?{urlencode(query)}" if query else url


def _json_rpc_content(payload: dict[str, Any]) -> dict[str, Any]:
    error = payload.get("error")
    if isinstance(error, dict):
        raise RuntimeError(str(error.get("message") or "Studio callback failed"))

    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Studio callback response did not include a result")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return {}
    first = content[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        return {}
    decoded = json.loads(first["text"])
    if not isinstance(decoded, dict):
        raise RuntimeError("Studio callback tool returned a non-object result")
    return decoded


def _parse_studio_callback_response(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in reversed(response.text.splitlines()):
            if not line.startswith("data:"):
                continue
            payload = json.loads(line.removeprefix("data:").strip())
            if isinstance(payload, dict):
                return _json_rpc_content(payload)
        raise RuntimeError("Studio callback stream ended without a tool result")

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Studio callback returned a non-object response")
    return _json_rpc_content(payload)


def _call_studio_tool(
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    workspace: str | None = None,
    studio_base_url: str | None = None,
) -> dict[str, Any]:
    """Call one of Studio's blocking UI tools from a deployed agent."""
    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    with httpx.Client(timeout=STUDIO_CALLBACK_TIMEOUT_SECONDS) as client:
        response = client.post(
            _studio_callback_url(
                session_id,
                workspace=workspace,
                studio_base_url=studio_base_url,
            ),
            json=body,
        )
    return _parse_studio_callback_response(response)


@tool
def select_agent(
    studio_session_id: str,
    title: str = "Select agent",
    description: str = "",
    default_agent: str | None = None,
) -> str:
    """Render Studio's agent selector and return the user's selected agent."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "select_agent",
            {
                "title": title,
                "description": description,
                "default_agent": default_agent,
            },
        )
    )


@tool
def select_model(
    studio_session_id: str,
    title: str = "Select model",
    description: str = "",
    default_model: str | None = None,
    output_key: str = "model",
) -> str:
    """Render Studio's model selector and return the user's selected model."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "select_model",
            {
                "title": title,
                "description": description,
                "default_model": default_model,
                "output_key": output_key,
            },
        )
    )


@tool
def select_dataset_file(
    studio_session_id: str,
    title: str = "Select dataset",
    description: str = "",
    accepted_file_types: list[str] | None = None,
) -> str:
    """Render Studio's fileset/dataset picker and return the selected file."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "select_dataset_file",
            {
                "title": title,
                "description": description,
                "accepted_file_types": accepted_file_types or [],
            },
        )
    )


@tool
def select_eval_config(
    studio_session_id: str,
    title: str = "Select evaluation config",
    description: str = "",
    agent: str | None = None,
) -> str:
    """Render Studio's evaluation-config picker and return the selected config."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "select_eval_config",
            {
                "title": title,
                "description": description,
                "agent": agent,
            },
        )
    )


@tool
def job_progress(
    studio_session_id: str,
    job_name: str,
    job_type: str | None = None,
    source: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> str:
    """Render a Studio progress card for a platform job that was just launched."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "job_progress",
            {
                "job_name": job_name,
                "job_type": job_type,
                "source": source,
                "title": title,
                "description": description,
            },
        )
    )


@tool
def studio_link(
    studio_session_id: str,
    destination: str,
    name: str | None = None,
    label: str | None = None,
    studio_base_url: str | None = None,
) -> str:
    """Build a feature-flag-aware link to a NeMo Studio page."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "studio_link",
            {
                "destination": destination,
                "name": name,
                "label": label,
            },
            studio_base_url=studio_base_url,
        )
    )


@tool
def check_status(service: str, job_name: str) -> str:
    """Check the status of a platform job or deployment.

    Args:
        service: The service that owns the job. One of:
            evaluation, customization, audit, data_designer
        job_name: The name or ID of the job to check.

    Returns:
        JSON string with the job status.
    """
    client = _get_client()
    try:
        svc = getattr(client, service)
        status_methods = [
            ("metric_jobs", "get_status"),
            ("benchmark_jobs", "get_status"),
            ("jobs", "get_status"),
        ]
        last_error: Exception | None = None
        for sub_resource, method_name in status_methods:
            if hasattr(svc, sub_resource):
                resource = getattr(svc, sub_resource)
                if hasattr(resource, method_name):
                    try:
                        result = getattr(resource, method_name)(name=job_name)
                        return json.dumps(_serialize(result), indent=2, default=str)
                    except Exception as exc:
                        last_error = exc
        if last_error:
            return f"Error: {type(last_error).__name__}: {last_error}"
        return f"Error: no status method found for service '{service}'"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


_nemo_tools = [
    nemo_api,
    check_status,
    select_agent,
    select_model,
    select_dataset_file,
    select_eval_config,
    job_progress,
    studio_link,
]


class _StreamSafeGraph:
    """Wraps a CompiledStateGraph with NAT-compatible incremental streaming.

    The custom ``nemo_agent_wrapper`` accepts Deep Agent state deltas that do
    not contain ``messages``. Delegate to the graph's real ``astream`` so NAT
    can forward chunks as each graph step completes instead of buffering the
    entire run behind ``ainvoke``.
    """

    def __init__(self, graph):
        self._graph = graph

    def __getattr__(self, name):
        return getattr(self._graph, name)

    @staticmethod
    def _bounded_config(config: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "recursion_limit": DEFAULT_RECURSION_LIMIT,
            **(config or {}),
        }

    @staticmethod
    async def _direct_response(input_data: Any, config: RunnableConfig) -> str | None:
        if not isinstance(input_data, dict):
            return None
        messages = input_data.get("messages")
        if not isinstance(messages, list):
            return None
        fileset_name = _direct_fileset_delete_name(messages)
        if fileset_name is not None:
            if _trusted_studio_session_id(config) is not None:
                denial = await asyncio.to_thread(
                    _request_mutation_approval,
                    config,
                    tool_name="nemo_api",
                    tool_input={
                        "resource": "files.filesets",
                        "action": "delete",
                        "params": json.dumps({"name": fileset_name}),
                    },
                )
                if denial is not None:
                    return denial
            return await asyncio.to_thread(_delete_fileset, fileset_name)
        resource_path = _direct_list_resource(messages)
        if resource_path is None:
            return None
        return await asyncio.to_thread(_list_resource_names, resource_path)

    async def ainvoke(self, input_data, config=None, **kwargs):
        bounded_config = self._bounded_config(config)
        direct_response = await self._direct_response(input_data, bounded_config)
        if direct_response is not None:
            return {"messages": [AIMessage(content=direct_response)]}
        return await self._graph.ainvoke(input_data, config=bounded_config, **kwargs)

    async def astream(self, input_data, config=None, **kwargs):
        bounded_config = self._bounded_config(config)
        direct_response = await self._direct_response(input_data, bounded_config)
        if direct_response is not None:
            yield {"messages": [AIMessageChunk(content=direct_response)]}
            return

        if "stream_mode" not in kwargs:
            async for message, _metadata in self._graph.astream(
                input_data,
                config=bounded_config,
                stream_mode="messages",
                **kwargs,
            ):
                if isinstance(message, AIMessage):
                    yield {"messages": [message]}
            return

        async for chunk in self._graph.astream(input_data, config=bounded_config, **kwargs):
            yield chunk

    async def astream_events(self, *args, **kwargs):
        async for event in self._graph.astream_events(*args, **kwargs):
            yield event


def _get_model():
    """Get the LLM from NAT's builder context (YAML llms: section)."""
    from nat.builder.framework_enum import LLMFrameworkEnum
    from nat.builder.sync_builder import SyncBuilder

    model = SyncBuilder.current().get_llm("agent", wrapper_type=LLMFrameworkEnum.LANGCHAIN)
    return _disable_nat_method_retries(model)


def _disable_nat_method_retries(model: Any) -> Any:
    """Remove NAT's instance-level retry decorators from the model.

    NAT 1.8's FastAPI worker round-trips its validated config through
    ``model_dump`` before starting the serving process. RetryMixin fields are
    lost in that round trip, so the worker silently restores its five-attempt
    defaults even when the source YAML disables retries. ``patch_with_retry``
    uses ``functools.wraps``, which leaves the original method available as
    ``__wrapped__``. Restore only wrappers whose code comes from NAT's
    ``automatic_retries.py``; leave every other LangChain decorator intact.
    """
    disabled: list[str] = []
    for name in dir(model):
        if name.startswith("_"):
            continue
        try:
            bound_method = getattr(model, name)
        except Exception:
            continue
        function = getattr(bound_method, "__func__", bound_method)
        wrapped = getattr(function, "__wrapped__", None)
        code = getattr(function, "__code__", None)
        if wrapped is None or code is None or Path(code.co_filename).name != "automatic_retries.py":
            continue
        object.__setattr__(model, name, types.MethodType(wrapped, model))
        disabled.append(name)
    if disabled:
        logger.info("nemo-agent: disabled NAT automatic retry wrappers for model methods: %s", ", ".join(disabled))
    return model


def _discover_skills(skills_dir: Path) -> list[str]:
    """Return the list of well-formed skills under ``skills_dir``.

    deepagents' ``SkillsMiddleware`` follows the Agent Skills specification
    (https://agentskills.io/specification): each skill must be a subdirectory
    containing a ``SKILL.md`` file whose first line is ``---`` (start of YAML
    frontmatter). We mirror that shape here so we can log a clear count and
    warn loudly when the layout drifts — silently empty skill loads have
    already cost us one Stage 4 baseline run.
    """
    if not skills_dir.is_dir():
        return []
    discovered: list[str] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            with skill_md.open("r", encoding="utf-8") as fp:
                first_line = fp.readline().strip()
        except OSError:
            continue
        if first_line == "---":
            discovered.append(child.name)
    return discovered


def _build_backend() -> CompositeBackend:
    """Build the agent filesystem backend.

    DeepAgents resolves both skill files and file-tool reads through this
    backend. Route packaged skills and `/tmp` to the real filesystem; keep all
    other scratchpad paths in graph state.

    Use virtual mode for routed filesystem roots because CompositeBackend strips
    the route prefix before delegation: `/tmp/foo` reaches the `/tmp/` backend
    as `/foo`, which should resolve under `/tmp`, not the container root.
    """
    routes = {
        f"{str(SKILLS_DIR).rstrip('/')}/": FilesystemBackend(root_dir=str(SKILLS_DIR), virtual_mode=True),
        "/tmp/": FilesystemBackend(root_dir="/tmp", virtual_mode=True),
    }
    return CompositeBackend(default=StateBackend(), routes=routes)


def create_nemo_agent(config=None):
    """Create the NeMo Platform Deep Agent.

    Args:
        config: Optional configuration for NAT langgraph_wrapper compatibility.
    """
    model = _get_model()
    # Only pass ``skills`` when at least one spec-compliant skill is actually
    # discovered. Driving ``skills`` purely off directory existence makes
    # ``create_deep_agent`` behavior depend on whatever its (downstream)
    # parser does with an empty layout, which is something we'd rather not
    # rely on when the layout drifts.
    discovered = _discover_skills(SKILLS_DIR)
    skills = [str(SKILLS_DIR)] if discovered else None
    if SKILLS_DIR.is_dir() and not discovered:
        logger.warning(
            "nemo-agent: SKILLS_DIR=%s is configured but no spec-compliant "
            "skills were discovered (each skill must be a subdirectory with "
            "a SKILL.md starting with '---' YAML frontmatter). Agent will "
            "run without playbook scaffolding.",
            SKILLS_DIR,
        )
    elif discovered:
        logger.info("nemo-agent: loaded %d skills: %s", len(discovered), ", ".join(discovered))
    backend = _build_backend()
    graph = create_deep_agent(
        model=model,
        tools=_nemo_tools,
        system_prompt=SYSTEM_PROMPT,
        skills=skills,
        backend=backend,
    )
    return _StreamSafeGraph(graph)


# Module-level graph factory. The active workflow type is `nemo_agent_wrapper`
# (see ./wrapper.py), which calls ``create_nemo_agent`` directly. This alias is
# kept so the graph can also be loaded via ``_type: langgraph_wrapper`` with
# ``graph: .../register.py:agent`` for ad-hoc debugging — note that path will
# hit the NAT 1.6.0 input/output schema bugs that ``nemo_agent_wrapper``
# exists to work around.
agent = create_nemo_agent
