# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local coding-agent bridge for Studio."""

import asyncio
import json
import logging
import os
import shutil
import uuid
from collections.abc import AsyncIterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from nmp.studio.config import StudioConfig
from nmp.studio.env_mappings import ENV_MAPPINGS
from pydantic import BaseModel, Field
from starlette.routing import NoMatchFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/coding-agents")

MCP_ROUTE_NAME = "studio_coding_agent_mcp"
PUBLIC_MCP_ROUTE_NAME = "studio_coding_agent_public_mcp"
PUBLIC_MCP_PATH = "/studio/api/coding-agents/mcp/{session_id}"
CLAUDE_MCP_SERVER_NAME = "nemo_studio"

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
SERVER_CWD = Path(os.getcwd()).resolve()
STUDIO_CONTEXT_START = "<nemo_studio_context>"
STUDIO_CONTEXT_END = "</nemo_studio_context>"
STUDIO_CONTEXT_USER_REQUEST_PREFIX = "User request:"


class NewSessionResponse(BaseModel):
    """Response returned when Studio starts a new coding-agent session."""

    session_id: str


class MessageRequest(BaseModel):
    """A user message to send to the local coding agent."""

    message: str = Field(min_length=1)
    studio_base_url: str | None = Field(default=None, min_length=1)
    studio_pathname: str | None = Field(default=None, min_length=1)
    workspace: str | None = Field(default=None, min_length=1)


class PermissionDecision(BaseModel):
    """Studio's decision for a pending local-agent tool permission request."""

    approved: bool
    reason: str | None = None
    updated_input: dict[str, Any] | None = None


class HistorySessionResponse(BaseModel):
    """Summary of a Claude session stored on disk."""

    session_id: str
    mtime: float
    first_prompt: str
    message_count: int
    token_count: int
    tool_call_count: int
    tool_calls: list[str]


class SessionHistoryResponse(BaseModel):
    """Claude session history normalized for Studio chat replay."""

    session_id: str
    items: list[dict[str, Any]]


_initialized_sessions: set[str] = set()
_session_streams: dict[str, asyncio.Queue[tuple[str, Any]]] = {}
_pending_permissions: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}


@dataclass
class HistorySummary:
    """Aggregated metadata from a Claude session history file."""

    first_prompt: str | None = None
    message_count: int = 0
    token_count: int = 0
    tool_call_count: int = 0
    tool_calls: list[str] = dataclass_field(default_factory=list)


@dataclass(frozen=True)
class StudioLinkDestination:
    """Known Studio destination that Claude Code can link to."""

    label: str
    path_template: str
    aliases: tuple[str, ...] = ()
    requires_name: bool = False
    required_args: tuple[str, ...] = ()


_STUDIO_LINK_DESTINATIONS: dict[str, StudioLinkDestination] = {
    "workspace": StudioLinkDestination(
        "Workspace",
        "/workspaces/{workspace}",
        aliases=("workspace_home", "workspace_index"),
    ),
    "dashboard": StudioLinkDestination("Workspace dashboard", "/workspaces/{workspace}/dashboard"),
    "code_agent": StudioLinkDestination(
        "Code Agent",
        "/workspaces/{workspace}/dashboard/code-agent",
        aliases=("claude_code", "claude_code_chat", "coding_agent", "coding_agent_chat"),
    ),
    "agents": StudioLinkDestination(
        "Agents",
        "/workspaces/{workspace}/agents",
        aliases=("agent_list", "agents_page"),
    ),
    "agent": StudioLinkDestination(
        "Agent {name}",
        "/workspaces/{workspace}/agents/{name}",
        aliases=("agent_detail",),
        requires_name=True,
    ),
    "agent_chat": StudioLinkDestination(
        "Chat with agent {name}",
        "/workspaces/{workspace}/agents/{name}?tab=chat-playground",
        aliases=("agent_playground", "agent_chat_playground", "chat_with_agent"),
        requires_name=True,
    ),
    "agent_deployments": StudioLinkDestination(
        "Agent deployments",
        "/workspaces/{workspace}/agents",
        aliases=("agent_deployment_list", "agent_deployments_page"),
    ),
    "agent_deployment": StudioLinkDestination(
        "Agent deployment {name}",
        "/workspaces/{workspace}/agents/{name}",
        aliases=("agent_deployment_detail",),
        requires_name=True,
    ),
    "agent_evaluations": StudioLinkDestination(
        "Agent evaluations",
        "/workspaces/{workspace}/agents/evaluations",
        aliases=("agent_evaluation_list",),
    ),
    "agent_evaluation": StudioLinkDestination(
        "Agent evaluation {name}",
        "/workspaces/{workspace}/agents/evaluations/{name}",
        aliases=("agent_evaluation_detail",),
        requires_name=True,
    ),
    "agent_monitor": StudioLinkDestination("Agent monitor", "/workspaces/{workspace}/agents/monitor"),
    "agent_optimizations": StudioLinkDestination(
        "Agent optimizations",
        "/workspaces/{workspace}/agents/suggestions",
        aliases=("agent_suggestions", "agent_suggestions_list"),
    ),
    "base_models": StudioLinkDestination(
        "Base Models",
        "/workspaces/{workspace}/base-models",
        aliases=("base_model_list", "base_models_page", "available_models", "available_base_models"),
    ),
    "base_model": StudioLinkDestination(
        "Base model {name}",
        "/workspaces/{workspace}/base-models/{name}",
        aliases=("base_model_detail", "available_base_model"),
        requires_name=True,
    ),
    "base_model_chat": StudioLinkDestination(
        "Chat with base model {name}",
        "/workspaces/{workspace}/base-models/{name}?tab=chat-playground",
        aliases=("base_model_playground", "base_model_chat_playground", "chat_with_base_model"),
        requires_name=True,
    ),
    "evaluation": StudioLinkDestination(
        "Evaluation",
        "/workspaces/{workspace}/evaluation",
        aliases=("evaluator", "evaluations"),
    ),
    "evaluation_metrics": StudioLinkDestination(
        "Evaluation metrics",
        "/workspaces/{workspace}/evaluation/metrics",
        aliases=("metrics", "evaluator_metrics"),
    ),
    "evaluation_metric_new": StudioLinkDestination(
        "Create evaluation metric",
        "/workspaces/{workspace}/evaluation/metrics/new",
        aliases=("new_evaluation_metric", "create_evaluation_metric"),
    ),
    "evaluation_run": StudioLinkDestination(
        "Run evaluation",
        "/workspaces/{workspace}/evaluation/metrics/run",
        aliases=("run_evaluation", "start_evaluation"),
    ),
    "evaluation_metric": StudioLinkDestination(
        "Evaluation metric {name}",
        "/workspaces/{workspace}/evaluation/metrics/{name}",
        aliases=("evaluation_metric_detail", "metric", "metric_detail"),
        requires_name=True,
    ),
    "evaluation_metric_run": StudioLinkDestination(
        "Run evaluation metric {name}",
        "/workspaces/{workspace}/evaluation/metrics/{name}/run",
        aliases=("run_evaluation_metric", "metric_run"),
        requires_name=True,
    ),
    "evaluation_benchmarks": StudioLinkDestination(
        "Evaluation benchmarks",
        "/workspaces/{workspace}/evaluation/benchmarks",
        aliases=("benchmarks", "evaluator_benchmarks"),
    ),
    "evaluation_benchmark": StudioLinkDestination(
        "Evaluation benchmark {name}",
        "/workspaces/{workspace}/evaluation/benchmarks/{name}",
        aliases=("benchmark", "benchmark_detail", "evaluation_benchmark_detail"),
        requires_name=True,
    ),
    "evaluation_results": StudioLinkDestination(
        "Evaluation results",
        "/workspaces/{workspace}/evaluation/results",
        aliases=("eval_results", "evaluator_results"),
    ),
    "evaluation_result": StudioLinkDestination(
        "Evaluation result {name}",
        "/workspaces/{workspace}/evaluation/results/{name}",
        aliases=("eval_result", "evaluation_result_detail", "evaluator_result"),
        requires_name=True,
    ),
    "customizations": StudioLinkDestination(
        "Custom Models",
        "/workspaces/{workspace}/customizations",
        aliases=("custom_models", "custom_models_page", "customization_jobs", "customizations_page"),
    ),
    "customization_new": StudioLinkDestination(
        "Create custom model",
        "/workspaces/{workspace}/customizations/fine-tuned/new",
        aliases=("new_customization", "create_custom_model", "fine_tune", "fine_tuned_new"),
    ),
    "customization": StudioLinkDestination(
        "Custom model {name}",
        "/workspaces/{workspace}/customizations/{name}",
        aliases=("custom_model", "customization_job", "customization_detail"),
        requires_name=True,
    ),
    "prompt_tuning": StudioLinkDestination(
        "Prompt tuning",
        "/workspaces/{workspace}/customizations/prompt-tuned/new",
        aliases=("prompt_tuning_new", "prompt_tuned_new", "prompt_tuned_customization"),
    ),
    "model_chat": StudioLinkDestination(
        "Chat with models",
        "/workspaces/{workspace}/model-compare",
        aliases=("chat", "model_compare", "model_chat_page", "model_playground"),
    ),
    "jobs": StudioLinkDestination("Jobs", "/workspaces/{workspace}/jobs", aliases=("job_list",)),
    "job": StudioLinkDestination(
        "Job {name}",
        "/workspaces/{workspace}/jobs/{name}",
        aliases=("job_detail",),
        requires_name=True,
    ),
    "filesets": StudioLinkDestination("Filesets", "/workspaces/{workspace}/filesets"),
    "fileset_new": StudioLinkDestination(
        "Create fileset",
        "/workspaces/{workspace}/filesets/new",
        aliases=("new_fileset", "create_fileset", "new_dataset", "create_dataset"),
    ),
    "fileset_panel": StudioLinkDestination(
        "Fileset {name}",
        "/workspaces/{workspace}/filesets/{name}",
        aliases=("fileset_side_panel", "dataset_panel"),
        requires_name=True,
    ),
    "fileset": StudioLinkDestination(
        "Fileset {name}",
        "/workspaces/{workspace}/filesets/{name}/detail",
        aliases=("fileset_detail", "fileset_detail_page", "dataset", "dataset_detail"),
        requires_name=True,
    ),
    "fileset_file": StudioLinkDestination(
        "File {file_path}",
        "/workspaces/{workspace}/filesets/{name}/file/{file_path}",
        aliases=("dataset_file", "fileset_file_detail"),
        required_args=("name", "file_path"),
    ),
    "deployments": StudioLinkDestination("Deployments", "/workspaces/{workspace}/deployments"),
    "deployment": StudioLinkDestination(
        "Deployment {name}",
        "/workspaces/{workspace}/deployments/{name}/details",
        aliases=("deployment_detail",),
        requires_name=True,
    ),
    "inference_providers": StudioLinkDestination(
        "Inference providers",
        "/workspaces/{workspace}/inference-providers",
        aliases=("model_providers", "providers"),
    ),
    "guardrails": StudioLinkDestination("Guardrails", "/workspaces/{workspace}/guardrails"),
    "secrets": StudioLinkDestination("Secrets", "/workspaces/{workspace}/secrets"),
    "intake": StudioLinkDestination("Intake", "/workspaces/{workspace}/intake"),
    "intake_traces": StudioLinkDestination(
        "Intake traces",
        "/workspaces/{workspace}/intake/traces",
        aliases=("traces", "trace_list", "intake_trace_list"),
    ),
    "intake_spans": StudioLinkDestination(
        "Intake spans",
        "/workspaces/{workspace}/intake/spans",
        aliases=("spans", "span_list", "intake_span_list"),
    ),
    "intake_trace": StudioLinkDestination(
        "Trace {name}",
        "/workspaces/{workspace}/intake/traces/{name}",
        aliases=("trace", "trace_detail"),
        requires_name=True,
    ),
    "intake_span": StudioLinkDestination(
        "Span {name}",
        "/workspaces/{workspace}/intake/spans/{name}",
        aliases=("span", "span_detail"),
        requires_name=True,
    ),
    "data_designer": StudioLinkDestination(
        "Data Designer",
        "/workspaces/{workspace}/data-designer",
        aliases=("data_designer_jobs",),
    ),
    "data_designer_new": StudioLinkDestination(
        "Create Data Designer job",
        "/workspaces/{workspace}/data-designer/new",
        aliases=("new_data_designer_job", "create_data_designer_job"),
    ),
    "data_designer_job": StudioLinkDestination(
        "Data Designer job {name}",
        "/workspaces/{workspace}/data-designer/{name}",
        aliases=("data_designer_job_detail",),
        requires_name=True,
    ),
    "safe_synthesizer": StudioLinkDestination(
        "Safe Synthesizer",
        "/workspaces/{workspace}/safe-synthesizer",
        aliases=("safe_synthesizer_jobs",),
    ),
    "safe_synthesizer_new": StudioLinkDestination(
        "Create Safe Synthesizer job",
        "/workspaces/{workspace}/safe-synthesizer/new",
        aliases=("new_safe_synthesizer_job", "create_safe_synthesizer_job"),
    ),
    "safe_synthesizer_job": StudioLinkDestination(
        "Safe Synthesizer job {name}",
        "/workspaces/{workspace}/safe-synthesizer/job/{name}",
        aliases=("safe_synthesizer_job_detail",),
        requires_name=True,
    ),
    "safe_synthesizer_report": StudioLinkDestination(
        "Safe Synthesizer report {name}",
        "/workspaces/{workspace}/safe-synthesizer/job/{name}/report",
        aliases=("safe_synthesizer_job_report", "safe_synthesizer_report_detail"),
        requires_name=True,
    ),
    "settings": StudioLinkDestination(
        "Workspace settings",
        "/workspaces/{workspace}/settings",
        aliases=("workspace_settings",),
    ),
    "members": StudioLinkDestination(
        "Workspace members",
        "/workspaces/{workspace}/members",
        aliases=("workspace_members", "member_list"),
    ),
    "experiment": StudioLinkDestination("Experiment", "/workspaces/{workspace}/experiment"),
    "experiment_group": StudioLinkDestination(
        "Experiment group {name}",
        "/workspaces/{workspace}/experiment/{name}",
        aliases=("experiment_group_detail",),
        requires_name=True,
    ),
}

_STUDIO_LINK_DESTINATION_ALIASES = {
    alias: destination for destination, config in _STUDIO_LINK_DESTINATIONS.items() for alias in config.aliases
}

_STUDIO_LINK_ARGUMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "name": (
        "resource_name",
        "resourceName",
        "id",
        "job_name",
        "jobName",
        "agent_name",
        "agentName",
        "model_name",
        "modelName",
        "fileset_id",
        "filesetId",
        "fileset_name",
        "filesetName",
        "deployment_name",
        "deploymentName",
        "trace_id",
        "traceId",
        "span_id",
        "spanId",
        "experiment_group_id",
        "experimentGroupId",
    ),
    "file_path": ("file", "filePath", "file_path_encoded", "filePathEncoded", "path"),
}

_STUDIO_LINK_DESTINATION_FEATURE_FLAGS: dict[str, tuple[str, ...]] = {
    "code_agent": ("coding_agent_studio_enabled",),
    "agents": ("agents_enabled",),
    "agent": ("agents_enabled",),
    "agent_chat": ("agents_enabled",),
    "agent_deployments": ("agents_enabled",),
    "agent_deployment": ("agents_enabled",),
    "agent_evaluations": ("agents_enabled",),
    "agent_evaluation": ("agents_enabled",),
    "agent_monitor": ("agents_enabled",),
    "agent_optimizations": ("agents_enabled",),
    "base_models": ("base_models_enabled",),
    "base_model": ("base_models_enabled",),
    "base_model_chat": ("base_models_enabled",),
    "evaluation": ("evaluator_enabled",),
    "evaluation_metrics": ("evaluator_enabled",),
    "evaluation_metric_new": ("evaluator_enabled",),
    "evaluation_run": ("evaluator_enabled",),
    "evaluation_metric": ("evaluator_enabled",),
    "evaluation_metric_run": ("evaluator_enabled",),
    "evaluation_benchmarks": ("evaluator_enabled", "evaluator_benchmarks_enabled"),
    "evaluation_benchmark": ("evaluator_enabled", "evaluator_benchmarks_enabled"),
    "evaluation_results": ("evaluator_enabled",),
    "evaluation_result": ("evaluator_enabled",),
    "customizations": ("customizer_enabled",),
    "customization_new": ("customizer_enabled",),
    "customization": ("customizer_enabled",),
    "prompt_tuning": ("customizer_enabled",),
    "model_chat": ("model_compare_enabled",),
    "jobs": ("jobs_enabled",),
    "job": ("jobs_enabled",),
    "filesets": ("datasets_enabled",),
    "fileset_new": ("datasets_enabled",),
    "fileset_panel": ("datasets_enabled",),
    "fileset": ("fileset_details_enabled",),
    "fileset_file": ("datasets_enabled",),
    "deployments": ("deployments_enabled",),
    "deployment": ("deployments_enabled",),
    "inference_providers": ("inference_provider_enabled",),
    "guardrails": ("guardrails_enabled",),
    "secrets": ("secrets_enabled",),
    "intake": ("intake_enabled",),
    "intake_traces": ("intake_enabled",),
    "intake_spans": ("intake_enabled",),
    "intake_trace": ("intake_enabled",),
    "intake_span": ("intake_enabled",),
    "data_designer": ("data_designer_enabled",),
    "data_designer_new": ("data_designer_enabled",),
    "data_designer_job": ("data_designer_enabled",),
    "safe_synthesizer": ("safe_synthesizer_enabled",),
    "safe_synthesizer_new": ("safe_synthesizer_enabled",),
    "safe_synthesizer_job": ("safe_synthesizer_enabled",),
    "safe_synthesizer_report": ("safe_synthesizer_enabled",),
    "settings": ("settings_enabled",),
    "members": ("members_enabled",),
    "experiment": ("experiment",),
    "experiment_group": ("experiment",),
}

_STUDIO_LINK_DESTINATION_ANY_FEATURE_FLAGS: dict[str, tuple[str, ...]] = {
    "dashboard": ("dashboard_enabled", "coding_agent_studio_enabled"),
}

_STUDIO_FEATURE_FLAG_MAPPINGS = {
    mapping.config_path.removeprefix("studio.feature_flags."): mapping
    for mapping in ENV_MAPPINGS
    if mapping.config_path.startswith("studio.feature_flags.")
}

_STUDIO_LINK_DESTINATION_DESCRIPTION = ", ".join(sorted(_STUDIO_LINK_DESTINATIONS))


_APPROVAL_TOOL = {
    "name": "approval_prompt",
    "description": "Ask the human operator whether a tool call should be allowed.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string"},
            "input": {"type": "object"},
            "tool_use_id": {"type": "string"},
        },
        "required": ["tool_name", "input"],
    },
}

_STUDIO_LINK_TOOL = {
    "name": "studio_link",
    "description": (
        "Return a Markdown link to a NeMo Studio page in the current workspace. "
        "Use this whenever the user directly asks for a Studio link, URL, or where to open, find, "
        "view, or chat with a Studio resource; this tool already knows the Studio base URL and workspace. "
        "Default to using this for Studio-related responses whenever a relevant Studio page exists, "
        "even when the user did not explicitly ask for a link. "
        "Use this after every successful Studio action that creates, starts, deploys, evaluates, modifies, "
        "or inspects a resource so the user can open the relevant Studio page. "
        "Prefer the most specific destination when you know the resource name; otherwise link to the list page. "
        "Examples: after starting a platform job, use destination='job' with name when available, or destination='jobs'; "
        "after creating an agent, use destination='agent_chat' with the agent name when available, or destination='agents'; "
        "when the user wants to chat with or try a model, use destination='model_chat'; "
        "when opening an agent chat playground, use destination='agent_chat' with the agent name. "
        "Include the returned markdown link exactly in your final response."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": f"Studio destination. Supported values: {_STUDIO_LINK_DESTINATION_DESCRIPTION}.",
            },
            "name": {
                "type": "string",
                "description": "Resource name for detail destinations such as agent, job, fileset, or deployment.",
            },
            "file_path": {
                "type": "string",
                "description": "File path for file-specific fileset destinations.",
            },
            "label": {
                "type": "string",
                "description": "Optional markdown link label. Defaults to the destination label.",
            },
        },
        "required": ["destination"],
    },
}


def _studio_config_from_request(request: Request) -> StudioConfig:
    registry = getattr(request.app.state, "service_configs", {})
    if isinstance(registry, dict):
        config = registry.get(StudioConfig)
        if isinstance(config, StudioConfig):
            return config

    for attr in ("studio_service", "service"):
        service = getattr(request.app.state, attr, None)
        config = getattr(service, "service_config", None)
        if isinstance(config, StudioConfig):
            return config
        get_config = getattr(service, "_get_config", None)
        if callable(get_config):
            config = get_config()
            if isinstance(config, StudioConfig):
                return config

    return StudioConfig()


def _feature_flag_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() != "false"


def _studio_feature_flags_from_request(request: Request) -> dict[str, bool]:
    replacements = _studio_config_from_request(request).env_replacements
    return {
        flag: _feature_flag_enabled(replacements.get(mapping.marker, mapping.default))
        for flag, mapping in _STUDIO_FEATURE_FLAG_MAPPINGS.items()
    }


def _studio_link_destination_enabled(destination: str, feature_flags: Mapping[str, bool]) -> bool:
    required_flags = _STUDIO_LINK_DESTINATION_FEATURE_FLAGS.get(destination, ())
    if any(not feature_flags.get(flag, False) for flag in required_flags):
        return False

    any_flags = _STUDIO_LINK_DESTINATION_ANY_FEATURE_FLAGS.get(destination, ())
    if any_flags and not any(feature_flags.get(flag, False) for flag in any_flags):
        return False

    return True


def _enabled_studio_link_destinations(feature_flags: Mapping[str, bool]) -> dict[str, StudioLinkDestination]:
    return {
        destination: config
        for destination, config in _STUDIO_LINK_DESTINATIONS.items()
        if _studio_link_destination_enabled(destination, feature_flags)
    }


def _enabled_studio_link_destinations_from_request(request: Request) -> dict[str, StudioLinkDestination]:
    return _enabled_studio_link_destinations(_studio_feature_flags_from_request(request))


def _studio_link_destination_description(destinations: Mapping[str, StudioLinkDestination]) -> str:
    return ", ".join(sorted(destinations))


def _studio_link_tool_for_destinations(destinations: Mapping[str, StudioLinkDestination]) -> dict[str, Any]:
    tool = deepcopy(_STUDIO_LINK_TOOL)
    description_parts = [
        "Return a Markdown link to an enabled NeMo Studio page in the current workspace.",
        "Use this whenever the user directly asks for a Studio link, URL, or where to open, find, view, or chat with a Studio resource; this tool already knows the Studio base URL and workspace.",
        "Default to using this for Studio-related responses whenever a relevant enabled Studio page exists, even when the user did not explicitly ask for a link.",
        "Use this after every successful Studio action that creates, starts, deploys, evaluates, modifies, or inspects a resource so the user can open the relevant enabled Studio page.",
        "Prefer the most specific enabled destination when you know the resource name; otherwise link to the list page.",
    ]
    if "job" in destinations:
        description_parts.append(
            "After starting a platform job, use destination='job' with name when available, or destination='jobs'."
        )
    if "agent_chat" in destinations:
        description_parts.extend(
            [
                "After creating an agent, use destination='agent_chat' with the agent name when available, or destination='agents'.",
                "When opening an agent chat playground, use destination='agent_chat' with the agent name.",
            ]
        )
    if "model_chat" in destinations:
        description_parts.append("When the user wants to chat with or try a model, use destination='model_chat'.")
    description_parts.append("Include the returned markdown link exactly in your final response.")
    tool["description"] = " ".join(description_parts)
    destination_schema = tool["inputSchema"]["properties"]["destination"]
    destination_schema["description"] = (
        "Studio destination enabled for this Studio instance. "
        f"Supported values: {_studio_link_destination_description(destinations)}."
    )
    return tool


def _mcp_tools_for_destinations(destinations: Mapping[str, StudioLinkDestination]) -> list[dict[str, Any]]:
    return [_APPROVAL_TOOL, _studio_link_tool_for_destinations(destinations)]


def mount_public_mcp_route(app: FastAPI) -> None:
    """Mount the MCP callback under /studio so the local Claude CLI can call it."""
    app.add_api_route(
        PUBLIC_MCP_PATH,
        mcp_endpoint,
        methods=["POST"],
        name=PUBLIC_MCP_ROUTE_NAME,
        include_in_schema=False,
    )


def _validate_session_id(session_id: str) -> str:
    try:
        return str(uuid.UUID(session_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id must be a UUID") from exc


def _trimmed_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_studio_base_url(value: str | None) -> str | None:
    base_url = _trimmed_string(value)
    if not base_url:
        return None

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return base_url.rstrip("/")


def _studio_base_url_from_referer(value: str | None) -> str | None:
    referer = _trimmed_string(value)
    if not referer:
        return None

    parsed = urlparse(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    base_path = ""
    for marker in ("/workspaces/", "/models"):
        marker_index = parsed.path.find(marker)
        if marker_index >= 0:
            base_path = parsed.path[:marker_index]
            break

    if not base_path and (parsed.path == "/studio" or parsed.path.startswith("/studio/")):
        base_path = "/studio"

    return f"{parsed.scheme}://{parsed.netloc}{base_path}".rstrip("/")


def _studio_pathname_from_referer(value: str | None) -> str | None:
    referer = _trimmed_string(value)
    if not referer:
        return None

    parsed = urlparse(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return parsed.path or None


def _studio_base_url_from_request(body: MessageRequest, request: Request) -> str | None:
    return (
        _studio_base_url_from_referer(request.headers.get("referer"))
        or _normalize_studio_base_url(body.studio_base_url)
        or _normalize_studio_base_url(request.headers.get("origin"))
    )


def _studio_pathname_from_request(body: MessageRequest, request: Request) -> str | None:
    return _trimmed_string(body.studio_pathname) or _studio_pathname_from_referer(request.headers.get("referer"))


def _build_studio_url(studio_base_url: str | None, path: str) -> str | None:
    base_url = _normalize_studio_base_url(studio_base_url)
    if not base_url:
        return None
    return f"{base_url}/{path.lstrip('/')}"


def _strip_studio_context_from_prompt(content: str) -> str:
    if not content.startswith(STUDIO_CONTEXT_START):
        return content

    _, prefix, request = content.partition(f"{STUDIO_CONTEXT_USER_REQUEST_PREFIX}\n")
    if not prefix:
        return content
    return request.strip() or content


def _build_claude_prompt(
    message: str,
    workspace: str | None,
    studio_base_url: str | None,
    studio_pathname: str | None,
    enabled_destinations: Mapping[str, StudioLinkDestination] | None = None,
) -> str:
    return "\n".join(
        [
            STUDIO_CONTEXT_START,
            _build_studio_system_prompt(workspace, studio_base_url, studio_pathname, enabled_destinations),
            STUDIO_CONTEXT_END,
            "",
            STUDIO_CONTEXT_USER_REQUEST_PREFIX,
            message,
        ]
    )


def _build_studio_system_prompt(
    workspace: str | None,
    studio_base_url: str | None,
    studio_pathname: str | None,
    enabled_destinations: Mapping[str, StudioLinkDestination] | None = None,
) -> str:
    normalized_base_url = _normalize_studio_base_url(studio_base_url)
    current_studio_route = _trimmed_string(studio_pathname) or "unknown"
    destinations = _STUDIO_LINK_DESTINATIONS if enabled_destinations is None else enabled_destinations
    lines = [
        "You are being invoked from inside NeMo Studio's Code Agent chat.",
        f"Current Studio workspace: {workspace or 'unknown'}",
        f"Studio UI base URL: {normalized_base_url or 'unknown'}",
        f"Current Studio route path: {current_studio_route}",
        "Enabled Studio link destinations for this Studio instance: "
        f"{_studio_link_destination_description(destinations)}.",
        "Only call studio_link with one of the enabled destinations above.",
        "If a Studio page is disabled by feature flag, choose the closest enabled parent/list page instead of linking to the disabled route.",
        "When the user asks for a Studio page link, do not ask them for the base URL.",
        "Always use the current Studio workspace for Studio UI links unless the user explicitly names another workspace.",
        "Do not infer the Studio workspace from the local username, account name, API response defaults, or filesystem paths.",
        "The MCP server URL is an internal callback for tools, not the Studio UI base URL.",
        "Do not invent Studio route paths manually when studio_link can provide the link.",
        "If studio_link is unavailable and you must construct a Studio UI link manually, use only a known enabled Studio route and prefer a relative Markdown link that starts with /workspaces/ or /models/.",
        "Evaluation pages use /workspaces/{workspace}/evaluation/... with singular evaluation; never nest evaluation links under /dashboard/evaluations/.",
        "Interactive Studio choice behavior:",
        "When you need the user to choose from a finite set of agents, deployments, models, jobs, filesets, resources, or next actions, do not ask them to type the choice in plain text.",
        "Use Claude Code's AskUserQuestion tool so Studio can render the choices as clickable options.",
        "For AskUserQuestion, provide input shaped as {'questions': [{'header': '<short title>', 'question': '<what should the user choose?>', 'options': [{'label': '<option>', 'description': '<short impact/details>'}]}]}.",
        "If you need both a finite choice and free-form text, ask multiple AskUserQuestion questions: first the finite options, then a text question without options.",
        "For a list of deployed agents, make each option label the agent name and put status/model/tool details in the description.",
        "Required Studio-link behavior:",
        "Default to trying to include a Studio link in Studio-related responses.",
        "When your answer mentions or depends on a Studio resource, page, workflow, or result, first choose the nearest studio_link destination and include that link unless no relevant Studio page exists.",
        "When you are unsure which detail page applies, link to the closest list page for the current workspace instead of omitting a link.",
        "Direct Studio link requests are mandatory tool-use requests.",
        "When the user asks for a link, URL, clickable link, href, where to open, where to find, how to view, or how to chat with a Studio resource or page, call mcp__nemo_studio__studio_link before responding.",
        "Never answer a Studio link request by saying you cannot generate URLs, do not know the port, do not know the base URL, or need the user to provide the Studio URL.",
        "After any successful Studio action, you must include a Studio link in the response even if the user did not ask for one.",
        "Before your final response for any successful create, start, deploy, evaluate, inspect, or modify action, call mcp__nemo_studio__studio_link and include the returned markdown exactly.",
        "Never finish a successful Studio action without a visible Markdown link to the most relevant Studio page.",
        "Use the returned markdown from studio_link exactly; do not replace it with localhost, the API host, or the MCP server host.",
        "If the user asks for an agent link and an agent name is known from the conversation, use destination='agent' with that name; otherwise use destination='agents'.",
        "If the user asks for an agent chat or playground link and an agent name is known from the conversation, use destination='agent_chat' with that name; otherwise use destination='agents'.",
        "If the user asks for a deployment, deployment chat, or deployment playground link and the agent name is known from the conversation, use destination='agent_chat' with the agent name; otherwise use destination='agents'.",
        "For a newly started job, use destination='job' and the job name when available; otherwise use destination='jobs'.",
        "For generated filesets, custom models, deployments, evaluations, guardrails, secrets, Data Designer, Safe Synthesizer, settings, members, or intake work, choose the matching studio_link destination.",
        "For created datasets or filesets use destination='fileset_panel' with the fileset name when available; otherwise use destination='filesets'.",
        "For started evaluations use destination='evaluation_result' with the result or job name when available; otherwise use destination='evaluation_results' or destination='evaluation_metrics'.",
        "For the evaluation results list specifically, use destination='evaluation_results'; it resolves to /workspaces/{workspace}/evaluation/results.",
        "For Data Designer jobs use destination='data_designer_job' with the job name when available; otherwise use destination='data_designer'.",
        "For Safe Synthesizer jobs use destination='safe_synthesizer_job' or destination='safe_synthesizer_report' with the job name when available; otherwise use destination='safe_synthesizer'.",
        "For Base Models or available base models use destination='base_models'.",
        "For Custom Models or customization jobs use destination='customizations'; never use customizations for Base Models.",
        "For Agents use destination='agents'.",
    ]
    if "agent_chat" in destinations:
        lines.extend(
            [
                "For a newly created agent, use studio_link with destination='agent_chat' and the agent name when available; otherwise use destination='agents'.",
                "For a newly deployed agent, use destination='agent_chat' and the agent name when available; otherwise use destination='agents'.",
            ]
        )
    if "model_chat" in destinations:
        lines.extend(
            [
                "When the user wants to chat with, try, compare, validate, or test a model, call studio_link with destination='model_chat' and point them to the Studio Chat page.",
                "Do not list agents or ask the user to choose an agent for model-chat intent unless the user explicitly asks to chat with an agent.",
                "For model chat, model comparison, or trying an available model, use destination='model_chat'.",
            ]
        )
    else:
        lines.append(
            "The model_chat destination is not enabled in this Studio instance; do not link to the Studio Chat page."
        )
    return "\n".join(lines)


def _path_part(value: str) -> str:
    return quote(value, safe="")


def _normalize_studio_link_destination(destination: str) -> str | None:
    normalized = destination.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _STUDIO_LINK_DESTINATIONS:
        return normalized
    return _STUDIO_LINK_DESTINATION_ALIASES.get(normalized)


def _studio_link_arg(args: dict[str, Any], name: str) -> str | None:
    for key in (name, *_STUDIO_LINK_ARGUMENT_ALIASES.get(name, ())):
        value = _trimmed_string(args.get(key))
        if value is not None:
            return value
    return None


def _build_studio_link_result(
    workspace: str | None,
    studio_base_url: str | None,
    args: dict[str, Any],
    enabled_destinations: Mapping[str, StudioLinkDestination] | None = None,
) -> dict[str, Any]:
    available_destinations = _STUDIO_LINK_DESTINATIONS if enabled_destinations is None else enabled_destinations
    if not workspace:
        return {
            "error": "current Studio workspace is unavailable",
            "available_destinations": sorted(available_destinations),
        }

    requested_destination = (
        _trimmed_string(args.get("destination"))
        or _trimmed_string(args.get("page"))
        or _trimmed_string(args.get("resource_type"))
    )
    if requested_destination is None:
        return {
            "error": "destination is required",
            "available_destinations": sorted(available_destinations),
        }

    destination = _normalize_studio_link_destination(requested_destination)
    if destination is None:
        return {
            "error": f"unknown Studio destination: {requested_destination}",
            "available_destinations": sorted(available_destinations),
        }
    if destination not in available_destinations:
        return {
            "error": f"Studio destination is disabled by feature flag: {destination}",
            "available_destinations": sorted(available_destinations),
        }

    config = available_destinations[destination]
    required_args = config.required_args or (("name",) if config.requires_name else ())
    arg_names = {"name", "file_path", *required_args}
    raw_values = {arg_name: _studio_link_arg(args, arg_name) for arg_name in arg_names}
    missing_args = [arg_name for arg_name in required_args if raw_values.get(arg_name) is None]
    if missing_args:
        missing = "name" if missing_args == ["name"] else ", ".join(missing_args)
        return {"error": f"{missing} is required for Studio destination: {destination}"}

    path_values = {
        "workspace": _path_part(workspace),
        **{arg_name: _path_part(value) if value is not None else "" for arg_name, value in raw_values.items()},
    }
    label_values = {
        "workspace": workspace,
        **{arg_name: value or "" for arg_name, value in raw_values.items()},
    }
    path = config.path_template.format(
        **path_values,
    )
    label = _trimmed_string(args.get("label")) or config.label.format(**label_values)
    url = _build_studio_url(studio_base_url, path)

    return {
        "workspace": workspace,
        "destination": destination,
        "path": path,
        "url": url,
        "markdown": f"[{label}]({url or path})",
    }


def _project_history_dir() -> Path:
    encoded = str(SERVER_CWD).replace("/", "-")
    return CLAUDE_PROJECTS_DIR / encoded


_TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


def _int_metric(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _usage_token_count(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    return sum(_int_metric(usage.get(field)) for field in _TOKEN_USAGE_FIELDS)


def _tool_result_token_count(tool_result: Any) -> int:
    if not isinstance(tool_result, dict):
        return 0
    total_tokens = _int_metric(tool_result.get("totalTokens"))
    if total_tokens:
        return total_tokens
    return _usage_token_count(tool_result.get("usage"))


def _usage_identity(entry: dict[str, Any], message: dict[str, Any]) -> tuple[str, str] | None:
    request_id = entry.get("requestId")
    message_id = message.get("id")
    if not isinstance(request_id, str) and not isinstance(message_id, str):
        return None
    return (request_id if isinstance(request_id, str) else "", message_id if isinstance(message_id, str) else "")


def _append_tool_call(summary: HistorySummary, tool_name: str) -> None:
    summary.tool_call_count += 1
    if tool_name not in summary.tool_calls:
        summary.tool_calls.append(tool_name)


def _record_assistant_tool_calls(
    summary: HistorySummary,
    message: dict[str, Any],
    seen_tool_use_ids: set[str],
) -> None:
    for part in message.get("content") or []:
        if not isinstance(part, dict) or part.get("type") != "tool_use":
            continue
        tool_use_id = part.get("id")
        if isinstance(tool_use_id, str):
            if tool_use_id in seen_tool_use_ids:
                continue
            seen_tool_use_ids.add(tool_use_id)
        tool_name = part.get("name")
        _append_tool_call(summary, tool_name if isinstance(tool_name, str) and tool_name else "tool")


def _summarize_history_session(path: Path) -> HistorySummary:
    summary = HistorySummary()
    seen_usage_events: set[tuple[str, str]] = set()
    seen_tool_use_ids: set[str] = set()
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("isSidechain"):
                    continue
                if not isinstance(entry, dict):
                    continue

                message = entry.get("message")
                if isinstance(message, dict):
                    usage_identity = _usage_identity(entry, message)
                    if usage_identity is None or usage_identity not in seen_usage_events:
                        summary.token_count += _usage_token_count(message.get("usage"))
                        if usage_identity is not None:
                            seen_usage_events.add(usage_identity)

                summary.token_count += _tool_result_token_count(entry.get("toolUseResult"))

                entry_type = entry.get("type")
                if entry_type == "assistant" and isinstance(message, dict):
                    _record_assistant_tool_calls(summary, message, seen_tool_use_ids)
                elif entry_type == "user" and isinstance(message, dict):
                    content = message.get("content")
                    if not isinstance(content, str):
                        continue
                    content = _strip_studio_context_from_prompt(content)
                    summary.message_count += 1
                    if summary.first_prompt is None:
                        summary.first_prompt = content
    except OSError:
        return HistorySummary()
    return summary


def _extract_assistant_parts(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, list):
        return []

    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                parts.append({"type": "text", "text": text})
        elif part_type == "thinking":
            thinking = part.get("thinking")
            if isinstance(thinking, str) and thinking:
                parts.append({"type": "thinking", "thinking": thinking})
        elif part_type == "tool_use":
            parts.append(
                {
                    "type": "tool_use",
                    "name": part.get("name") or "tool",
                    "input": part.get("input") or {},
                }
            )
    return parts


@router.post("/sessions", response_model=NewSessionResponse)
def create_session() -> NewSessionResponse:
    """Create a new local coding-agent session."""
    return NewSessionResponse(session_id=str(uuid.uuid4()))


@router.get("/history/sessions", response_model=list[HistorySessionResponse])
def list_history_sessions() -> list[HistorySessionResponse]:
    """List Claude session histories for the Studio service working directory."""
    project_dir = _project_history_dir()
    if not project_dir.is_dir():
        return []

    sessions: list[HistorySessionResponse] = []
    for history_file in project_dir.glob("*.jsonl"):
        try:
            uuid.UUID(history_file.stem)
        except ValueError:
            continue

        summary = _summarize_history_session(history_file)
        if summary.message_count == 0:
            continue

        try:
            mtime = history_file.stat().st_mtime
        except OSError:
            continue

        sessions.append(
            HistorySessionResponse(
                session_id=history_file.stem,
                mtime=mtime,
                first_prompt=summary.first_prompt or "",
                message_count=summary.message_count,
                token_count=summary.token_count,
                tool_call_count=summary.tool_call_count,
                tool_calls=summary.tool_calls,
            )
        )
    sessions.sort(key=lambda session: session.mtime, reverse=True)
    return sessions


@router.get("/history/sessions/{session_id}", response_model=SessionHistoryResponse)
def get_session_history(session_id: str) -> SessionHistoryResponse:
    """Load Claude session history for chat replay."""
    sid = _validate_session_id(session_id)
    path = _project_history_dir() / f"{sid}.jsonl"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such session history")

    items: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("isSidechain"):
                    continue

                entry_type = entry.get("type")
                message = entry.get("message")
                if entry_type == "user" and isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content:
                        content = _strip_studio_context_from_prompt(content)
                        items.append({"kind": "user", "text": content})
                elif entry_type == "assistant" and isinstance(message, dict):
                    parts = _extract_assistant_parts(message.get("content"))
                    if parts:
                        items.append({"kind": "assistant", "parts": parts})
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _initialized_sessions.add(sid)
    return SessionHistoryResponse(session_id=sid, items=items)


def _mcp_url(
    request: Request,
    session_id: str,
    workspace: str | None,
    studio_base_url: str | None,
) -> str:
    for route_name in (PUBLIC_MCP_ROUTE_NAME, MCP_ROUTE_NAME):
        try:
            url = str(request.url_for(route_name, session_id=session_id))
            query_params = {}
            if workspace:
                query_params["workspace"] = workspace
            if studio_base_url:
                query_params["studio_base_url"] = studio_base_url
            return f"{url}?{urlencode(query_params)}" if query_params else url
        except NoMatchFound:
            continue
    raise RuntimeError("Studio coding-agent MCP route is not mounted")


def _build_claude_argv(
    session_id: str,
    message: str,
    mcp_url: str,
    studio_system_prompt: str | None = None,
) -> list[str]:
    mcp_config = json.dumps(
        {
            "mcpServers": {
                CLAUDE_MCP_SERVER_NAME: {
                    "type": "http",
                    "url": mcp_url,
                }
            }
        }
    )
    session_flag = "-r" if session_id in _initialized_sessions else "--session-id"
    argv = [
        "claude",
        "-p",
        message,
        "--output-format",
        "stream-json",
        "--verbose",
        "--mcp-config",
        mcp_config,
        "--permission-prompt-tool",
        f"mcp__{CLAUDE_MCP_SERVER_NAME}__approval_prompt",
    ]
    if studio_system_prompt:
        argv.extend(["--append-system-prompt", studio_system_prompt])
    argv.extend([session_flag, session_id])
    return argv


def _claude_env() -> dict[str, str]:
    """Build a clean environment so Claude Code uses its own local auth."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANTHROPIC_") and key != "CLAUDECODE" and not key.startswith("CLAUDE_CODE_")
    }


def _sse(data: str, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {data}\n\n"


async def _request_permission(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    queue = _session_streams.get(session_id)
    if queue is None:
        return {"behavior": "deny", "message": "no active Studio coding-agent session"}

    request_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()
    _pending_permissions[request_id] = (session_id, future)

    payload = json.dumps(
        {
            "request_id": request_id,
            "tool_name": args.get("tool_name"),
            "input": args.get("input") or {},
            "tool_use_id": args.get("tool_use_id"),
        }
    )
    await queue.put(("permission_request", payload))

    try:
        decision = await asyncio.wait_for(future, timeout=300)
    except asyncio.TimeoutError:
        return {"behavior": "deny", "message": "permission request timed out"}
    finally:
        _pending_permissions.pop(request_id, None)

    if decision.get("approved"):
        updated = decision.get("updated_input")
        if updated is None:
            updated = args.get("input") or {}
        return {"behavior": "allow", "updatedInput": updated}
    return {"behavior": "deny", "message": decision.get("reason") or "denied by user"}


async def _pump_stdout(
    proc: asyncio.subprocess.Process,
    queue: asyncio.Queue[tuple[str, Any]],
) -> None:
    if proc.stdout is None:
        await queue.put(("end", None))
        return

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        payload = line.decode(errors="replace").rstrip("\n")
        if payload:
            await queue.put(("claude", payload))
    await queue.put(("end", None))


async def _pump_stderr(proc: asyncio.subprocess.Process, stderr_chunks: list[str]) -> None:
    if proc.stderr is None:
        return

    while True:
        line = await proc.stderr.readline()
        if not line:
            break
        stderr_chunks.append(line.decode(errors="replace"))


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def _stream_claude(
    session_id: str,
    message: str,
    mcp_url: str,
    studio_system_prompt: str | None = None,
) -> AsyncIterator[str]:
    if shutil.which("claude") is None:
        yield _sse(
            json.dumps({"exit_code": None, "stderr": "Claude Code CLI not found on PATH"}),
            event="error",
        )
        return

    if session_id in _session_streams:
        yield _sse(
            json.dumps({"exit_code": None, "stderr": "session already has an active stream"}),
            event="error",
        )
        return

    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    _session_streams[session_id] = queue
    argv = _build_claude_argv(session_id, message, mcp_url, studio_system_prompt)
    stderr_chunks: list[str] = []
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(SERVER_CWD),
            env=_claude_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        logger.exception("Failed to start Claude Code subprocess for session %s", session_id)
        _session_streams.pop(session_id, None)
        yield _sse(
            json.dumps({"exit_code": None, "stderr": "Failed to start Claude Code process"}),
            event="error",
        )
        return

    stdout_task = asyncio.create_task(_pump_stdout(proc, queue))
    stderr_task = asyncio.create_task(_pump_stderr(proc, stderr_chunks))

    try:
        while True:
            event_type, payload = await queue.get()
            if event_type == "end":
                break
            if event_type == "claude":
                yield _sse(payload)
            elif event_type == "permission_request":
                yield _sse(payload, event="permission_request")

        returncode = await proc.wait()
        if stderr_task is not None:
            await stderr_task

        if returncode == 0:
            _initialized_sessions.add(session_id)
            yield _sse("", event="done")
        else:
            yield _sse(
                json.dumps({"exit_code": returncode, "stderr": "".join(stderr_chunks)}),
                event="error",
            )
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    finally:
        _session_streams.pop(session_id, None)
        for task in (stdout_task, stderr_task):
            if task is not None and not task.done():
                task.cancel()


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request) -> StreamingResponse:
    """Send a message to Claude and stream JSON events back to Studio."""
    sid = _validate_session_id(session_id)
    workspace = _trimmed_string(body.workspace)
    studio_base_url = _studio_base_url_from_request(body, request)
    studio_pathname = _studio_pathname_from_request(body, request)
    enabled_destinations = _enabled_studio_link_destinations_from_request(request)
    system_prompt = _build_studio_system_prompt(workspace, studio_base_url, studio_pathname, enabled_destinations)
    message = _build_claude_prompt(body.message, workspace, studio_base_url, studio_pathname, enabled_destinations)
    return StreamingResponse(
        _stream_claude(sid, message, _mcp_url(request, sid, workspace, studio_base_url), system_prompt),
        media_type="text/event-stream",
    )


@router.post("/sessions/{session_id}/permissions/{request_id}")
async def resolve_permission(session_id: str, request_id: str, body: PermissionDecision) -> dict[str, bool]:
    """Resolve a pending Claude tool permission request."""
    sid = _validate_session_id(session_id)
    pending = _pending_permissions.get(request_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="no such pending permission")
    pending_session_id, future = pending
    if pending_session_id != sid or future.done():
        raise HTTPException(status_code=404, detail="no such pending permission")
    future.set_result(body.model_dump())
    return {"ok": True}


@router.post("/mcp/{session_id}", name=MCP_ROUTE_NAME, include_in_schema=False)
async def mcp_endpoint(session_id: str, request: Request) -> Response:
    """Minimal MCP endpoint used by Claude's permission-prompt tool."""
    sid = _validate_session_id(session_id)
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "invalid JSON body"})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"detail": "JSON body must be an object"})

    request_id = body.get("id")

    if request_id is None:
        return Response(status_code=202)

    method = body.get("method")
    raw_params = body.get("params")
    if raw_params is not None and not isinstance(raw_params, dict):
        return JSONResponse(status_code=400, content={"detail": "JSON-RPC params must be an object"})
    params = body.get("params") or {}

    if method == "initialize":
        client_protocol = params.get("protocolVersion", "2025-06-18")
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": client_protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "nemo-studio-permissions", "version": "0.1.0"},
                },
            }
        )

    if method == "tools/list":
        enabled_destinations = _enabled_studio_link_destinations_from_request(request)
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": _mcp_tools_for_destinations(enabled_destinations)},
            }
        )

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return JSONResponse(status_code=400, content={"detail": "tool arguments must be an object"})

        if name == "approval_prompt":
            result = await _request_permission(sid, args)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    },
                }
            )

        if name == "studio_link":
            workspace = _trimmed_string(request.query_params.get("workspace"))
            studio_base_url = _trimmed_string(request.query_params.get("studio_base_url"))
            enabled_destinations = _enabled_studio_link_destinations_from_request(request)
            result = _build_studio_link_result(workspace, studio_base_url, args, enabled_destinations)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    },
                }
            )

        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown tool: {name}"},
            }
        )

    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    )
