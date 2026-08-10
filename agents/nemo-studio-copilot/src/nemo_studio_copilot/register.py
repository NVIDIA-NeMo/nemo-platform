# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Studio Copilot tool implementations exposed through MCP."""

import json
import os
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
from nemo_platform import NeMoPlatform
from pydantic import BaseModel

DEFAULT_WORKSPACE = "default"
STUDIO_CALLBACK_PATH = "/studio/api/copilot/mcp/{session_id}"
STUDIO_CALLBACK_TIMEOUT_SECONDS = 3600.0
_READ_ONLY_SDK_ACTIONS = frozenset({"get", "get_logs", "get_status", "list", "read", "retrieve", "search"})

_clients: dict[str, NeMoPlatform] = {}


def _active_workspace() -> str:
    return os.environ.get("NMP_WORKSPACE") or DEFAULT_WORKSPACE


def _get_client(workspace: str) -> NeMoPlatform:
    request_workspace = workspace.strip()
    if not request_workspace:
        raise ValueError("workspace is required")
    if request_workspace not in _clients:
        base_url = os.environ.get("NEMO_BASE_URL") or os.environ.get("NMP_BASE_URL")
        kwargs: dict[str, Any] = {"workspace": request_workspace}
        if base_url:
            kwargs["base_url"] = base_url
        _clients[request_workspace] = NeMoPlatform(**kwargs)
    return _clients[request_workspace]


def _serialize(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    return str(obj)


def _resolve_resource(client: NeMoPlatform, resource_path: str) -> Any:
    current = client
    for part in resource_path.split("."):
        if not part or part.startswith("_"):
            raise ValueError(f"Invalid SDK resource path: {resource_path}")
        current = getattr(current, part)
    return current


def _call_sdk_method(resource: Any, action: str, params: dict[str, Any] | None = None) -> Any:
    if not action or action.startswith("_"):
        raise ValueError(f"Invalid SDK action: {action}")
    method = getattr(resource, action)
    return method(**params) if params else method()


def _validated_session_id(session_id: str) -> str:
    try:
        return str(uuid.UUID(session_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("A valid Studio session id is required") from exc


def _studio_callback_url(
    session_id: str,
    *,
    workspace: str | None = None,
    studio_base_url: str | None = None,
) -> str:
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
    url = f"{base_url}{STUDIO_CALLBACK_PATH.format(session_id=_validated_session_id(session_id))}"
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
            if line.startswith("data:"):
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
    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    with httpx.Client(timeout=STUDIO_CALLBACK_TIMEOUT_SECONDS) as client:
        response = client.post(
            _studio_callback_url(session_id, workspace=workspace, studio_base_url=studio_base_url), json=body
        )
    return _parse_studio_callback_response(response)


def _request_mutation_approval(
    studio_session_id: str | None,
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    workspace: str,
) -> dict[str, Any] | str:
    if studio_session_id is None:
        return "Denied: mutating operations require a Studio session id and explicit approval"
    try:
        session_id = _validated_session_id(studio_session_id)
    except ValueError:
        return "Denied: mutating operations require a valid Studio session id and explicit approval"
    approval = _call_studio_tool(
        session_id,
        "approval_prompt",
        {"tool_name": tool_name, "input": tool_input},
        workspace=workspace,
    )
    if approval.get("behavior") != "allow":
        return f"Denied by user: {approval.get('message') or 'operation was not approved'}"
    updated_input = approval.get("updatedInput")
    return updated_input if isinstance(updated_input, dict) else tool_input


def nemo_api(
    resource: str,
    action: str,
    params: str | None = None,
    studio_session_id: str | None = None,
    workspace: str | None = None,
) -> str:
    """Call a NeMo Platform SDK method; writes require explicit Studio approval.

    ``resource`` is a dot-separated SDK path such as ``workspaces``,
    ``inference.providers``, ``files.filesets``, ``evaluation.metric_jobs``,
    ``guardrail``, ``secrets``, ``models`` or ``datasets``. ``action`` is the
    SDK method name. ``params`` is an optional JSON object string containing
    keyword arguments. Pass the active request workspace for every operation.
    Pass the Studio session id from the user context for create, update, delete,
    submit, upload, cancel, or other mutating actions.
    """
    try:
        if workspace is None or not workspace.strip():
            return "Clarification required: which workspace should this operation use?"
        parsed_params = json.loads(params) if params else None
        if parsed_params is not None and not isinstance(parsed_params, dict):
            raise ValueError("params must decode to a JSON object")
        normalized_action = action.strip().lower()
        if normalized_action not in _READ_ONLY_SDK_ACTIONS:
            approved_input = _request_mutation_approval(
                studio_session_id,
                tool_name="nemo_api",
                tool_input={"resource": resource, "action": action, "params": params, "workspace": workspace},
                workspace=workspace,
            )
            if isinstance(approved_input, str):
                return approved_input
            if approved_input.get("workspace", workspace) != workspace:
                return "Denied: mutation approval cannot change the request workspace"
            resource = approved_input.get("resource", resource)
            action = approved_input.get("action", action)
            approved_params = approved_input.get("params", params)
            if approved_params != params:
                params = approved_params
                parsed_params = json.loads(params) if params else None
                if parsed_params is not None and not isinstance(parsed_params, dict):
                    raise ValueError("params must decode to a JSON object")
            normalized_action = action.strip().lower()
        result = _call_sdk_method(_resolve_resource(_get_client(workspace), resource), normalized_action, parsed_params)
        return json.dumps(_serialize(result), indent=2, default=str)
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


def select_agent(
    studio_session_id: str, title: str = "Select agent", description: str = "", default_agent: str | None = None
) -> str:
    """Render Studio's agent selector and return the selected agent."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "select_agent",
            {"title": title, "description": description, "default_agent": default_agent},
        )
    )


def select_model(
    studio_session_id: str,
    title: str = "Select model",
    description: str = "",
    default_model: str | None = None,
    output_key: str = "model",
    display_label: str | None = None,
    field_label: str | None = None,
    placeholder: str | None = None,
    required_message: str | None = None,
    submit_label: str | None = None,
) -> str:
    """Render Studio's model selector and return the selected model."""
    return json.dumps(
        _call_studio_tool(
            studio_session_id,
            "select_model",
            {
                "title": title,
                "description": description,
                "default_model": default_model,
                "output_key": output_key,
                "display_label": display_label,
                "field_label": field_label,
                "placeholder": placeholder,
                "required_message": required_message,
                "submit_label": submit_label,
            },
        )
    )


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
            {"title": title, "description": description, "accepted_file_types": accepted_file_types or []},
        )
    )


def select_eval_config(
    studio_session_id: str,
    title: str = "Select evaluation config",
    description: str = "",
    agent: str | None = None,
    default_agent: str | None = None,
    accepted_file_types: list[str] | None = None,
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
                "default_agent": default_agent,
                "accepted_file_types": accepted_file_types or [],
            },
        )
    )


def job_progress(
    studio_session_id: str,
    job_name: str,
    job_type: str | None = None,
    source: str | None = None,
    title: str | None = None,
    description: str | None = None,
    workspace: str | None = None,
) -> str:
    """Render a Studio progress card for a platform job."""
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
                "workspace": workspace,
            },
        )
    )


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
            {"destination": destination, "name": name, "label": label},
            studio_base_url=studio_base_url,
        )
    )


def ask_user_question(studio_session_id: str, questions: str) -> str:
    """Render one or more Studio multiple-choice questions."""
    try:
        parsed = json.loads(questions)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"Error: `questions` must be a JSON array string: {exc}"
    if not isinstance(parsed, list) or not parsed or not all(isinstance(question, dict) for question in parsed):
        return "Error: `questions` must be a non-empty JSON array of question objects."
    approval = _call_studio_tool(
        studio_session_id, "approval_prompt", {"tool_name": "AskUserQuestion", "input": {"questions": parsed}}
    )
    if approval.get("behavior") != "allow":
        return f"User declined to answer: {approval.get('message') or 'no selection made'}"
    return json.dumps(approval.get("updatedInput") or {})


def check_status(service: str, job_name: str, workspace: str | None = None) -> str:
    """Check an evaluation, customization, audit, or Data Designer job."""
    try:
        if workspace is None or not workspace.strip():
            return "Clarification required: which workspace should this status check use?"
        svc = getattr(_get_client(workspace), service)
        last_error: Exception | None = None
        for sub_resource in ("metric_jobs", "benchmark_jobs", "jobs"):
            resource = getattr(svc, sub_resource, None)
            if resource is None or not hasattr(resource, "get_status"):
                continue
            try:
                return json.dumps(_serialize(resource.get_status(name=job_name)), indent=2, default=str)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            return f"Error: {type(last_error).__name__}: {last_error}"
        return f"Error: no status method found for service '{service}'"
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"
