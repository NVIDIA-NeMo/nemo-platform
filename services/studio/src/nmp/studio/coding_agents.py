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
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from nmp.studio import studio_links
from nmp.studio.coding_agent_artifacts import (
    ChatArtifactsResponse,
    record_answer_selections,
    record_coding_agent_model,
    record_spec_text_artifacts,
    record_tool_artifacts,
    record_tool_name,
    record_user_tool_result_artifacts,
    record_workspace_artifact,
    string_value,
)
from nmp.studio.coding_agent_mcp_tools import (
    APPROVAL_TOOL_NAME,
    CLAUDE_MCP_SERVER_NAME,
    JOB_PROGRESS_TOOL_NAME,
    MCP_TOOLS,
    SELECT_AGENT_TOOL_NAME,
    SELECT_DATASET_FILE_TOOL_NAME,
    SELECT_EVAL_CONFIG_TOOL_NAME,
    SELECT_MODEL_TOOL_NAME,
    STUDIO_CODING_AGENT_CONTEXT,
    STUDIO_LINK_TOOL_NAME,
    allowed_mcp_tools,
    permission_prompt_tool,
)
from nmp.studio.coding_agent_skills import ClaudeSkillResponse, DuplicateSkillError, list_claude_skill_responses
from pydantic import BaseModel, Field
from starlette.routing import NoMatchFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/coding-agents")

MCP_ROUTE_NAME = "studio_coding_agent_mcp"
PUBLIC_MCP_ROUTE_NAME = "studio_coding_agent_public_mcp"
PUBLIC_MCP_PATH = "/studio/api/coding-agents/mcp/{session_id}"

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


class AgentInputDecision(BaseModel):
    """Studio's value for a pending local-agent UI input request."""

    skipped: bool = False
    value: dict[str, Any] | None = None


class HistorySessionResponse(BaseModel):
    """Summary of a Claude session stored on disk."""

    session_id: str
    mtime: float
    first_prompt: str
    message_count: int
    token_count: int
    tool_call_count: int
    tool_calls: list[str]
    chat_artifacts: ChatArtifactsResponse


class SessionHistoryResponse(BaseModel):
    """Claude session history normalized for Studio chat replay."""

    session_id: str
    items: list[dict[str, Any]]
    chat_artifacts: ChatArtifactsResponse


_initialized_sessions: set[str] = set()
_session_streams: dict[str, asyncio.Queue[tuple[str, Any]]] = {}
_pending_permissions: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
_pending_agent_inputs: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
_AGENT_INPUT_RESPONSE_RESERVED_KEYS = frozenset({"message", "status"})


@dataclass
class HistorySummary:
    """Aggregated metadata from a Claude session history file."""

    first_prompt: str | None = None
    message_count: int = 0
    token_count: int = 0
    tool_call_count: int = 0
    tool_calls: list[str] = dataclass_field(default_factory=list)
    chat_artifacts: ChatArtifactsResponse = dataclass_field(default_factory=ChatArtifactsResponse)


def _mcp_tools_for_destinations(
    destinations: Mapping[str, studio_links.StudioLinkDestination],
) -> list[dict[str, Any]]:
    return [*MCP_TOOLS, studio_links.tool_for_destinations(destinations)]


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
    enabled_destinations: Mapping[str, studio_links.StudioLinkDestination] | None = None,
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
    enabled_destinations: Mapping[str, studio_links.StudioLinkDestination] | None = None,
) -> str:
    normalized_base_url = _normalize_studio_base_url(studio_base_url)
    current_studio_route = _trimmed_string(studio_pathname) or "unknown"
    destinations = studio_links.STUDIO_LINK_DESTINATIONS if enabled_destinations is None else enabled_destinations
    lines = [
        "You are being invoked from inside NeMo Studio's Code Agent chat.",
        f"Current Studio workspace: {workspace or 'unknown'}",
        f"Studio UI base URL: {normalized_base_url or 'unknown'}",
        f"Current Studio route path: {current_studio_route}",
        "Enabled Studio link destinations for this Studio instance: "
        f"{studio_links.destination_description(destinations)}.",
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
        "Studio ships dedicated visual picker tools. When a picker fits, you MUST use it instead of plain text and instead of AskUserQuestion.",
        "Whenever you need the user to name, pick, confirm, or disambiguate an agent (including choosing among deployed agents), you MUST call mcp__nemo_studio__select_agent to render the agent dropdown. Never ask for an agent in plain text and never use AskUserQuestion for an agent choice.",
        "Whenever you need the user to choose a model, you MUST call mcp__nemo_studio__select_model. Never use AskUserQuestion or plain text for a model choice.",
        "Whenever you need a fileset, fileset reference, dataset, or input/source data file (including an anonymizer or evaluation input, or a CSV/Parquet file), you MUST call mcp__nemo_studio__select_dataset_file instead of asking for a fileset reference or '<workspace>/<fileset>#<file>' path in plain text; for an evaluation config file, you MUST call mcp__nemo_studio__select_eval_config.",
        "Treat 'which agent', 'pick an agent', 'choose a model', 'which fileset', and 'what is your fileset reference' as mandatory tool-use requests for the matching select_* tool, exactly like Studio link requests are mandatory studio_link requests.",
        "Set the picker title and description to match the current workflow, for example title='Select agent to audit'.",
        "Only skip a picker when the user already gave the value, the value is already unambiguous from the conversation, or a previous picker call returned skipped or error.",
        "For finite choices that have no dedicated Studio picker (for example deployments, jobs, or next actions) and for yes/no or multiple-choice clarifications, use Claude Code's AskUserQuestion tool so Studio can render clickable options instead of asking the user to type.",
        "For AskUserQuestion, provide input shaped as {'questions': [{'header': '<short title>', 'question': '<what should the user choose?>', 'options': [{'label': '<option>', 'description': '<short impact/details>'}]}]}.",
        "If you need both a finite choice and free-form text, ask multiple AskUserQuestion questions: first the finite options, then a text question without options.",
        "Prefer NeMo Studio MCP tools and Studio views over CLI commands for user-facing follow-up actions, navigation, inspection, and status/result review.",
        "Do not tell the user to run nemo CLI commands, shell commands, curl commands, or status commands to inspect agents, jobs, evaluations, filesets, models, traces, logs, or results when a Studio view, Studio link, or Studio progress card is available for the same purpose.",
        "Use CLI commands only to perform work that has no Studio UI equivalent, when the user explicitly asks for CLI/debugging, or when you must gather data that Studio tools cannot provide.",
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
        "Required job-progress behavior:",
        "Whenever you start, submit, or kick off any platform job and you know its job name, you MUST call mcp__nemo_studio__job_progress with that job name before your final response, once for every job you launch.",
        "Do not replace the job_progress card with a plain-text job summary or by telling the user to run a status command; call job_progress in addition to any Studio link.",
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


def _append_unique_string(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


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
    _append_unique_string(summary.tool_calls, tool_name)
    record_tool_name(summary.chat_artifacts, tool_name)


def _record_assistant_tool_calls(
    summary: HistorySummary,
    message: dict[str, Any],
    seen_tool_use_ids: set[str],
    question_labels_by_tool_use_id: dict[str, dict[str, str]],
) -> None:
    for part in message.get("content") or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            text = string_value(part.get("text"))
            if text:
                record_spec_text_artifacts(summary.chat_artifacts, text)
            continue
        if part.get("type") != "tool_use":
            continue
        tool_use_id = part.get("id")
        if isinstance(tool_use_id, str):
            if tool_use_id in seen_tool_use_ids:
                continue
            seen_tool_use_ids.add(tool_use_id)
        tool_name = part.get("name")
        tool_name = tool_name if isinstance(tool_name, str) and tool_name else "tool"
        _append_tool_call(summary, tool_name)
        record_tool_artifacts(
            summary.chat_artifacts,
            tool_name,
            part.get("input") or {},
            tool_use_id if isinstance(tool_use_id, str) else None,
            question_labels_by_tool_use_id,
        )


def _summarize_history_session(path: Path) -> HistorySummary:
    summary = HistorySummary()
    seen_usage_events: set[tuple[str, str]] = set()
    seen_tool_use_ids: set[str] = set()
    question_labels_by_tool_use_id: dict[str, dict[str, str]] = {}
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
                    record_coding_agent_model(summary.chat_artifacts, string_value(message.get("model")))
                    usage_identity = _usage_identity(entry, message)
                    if usage_identity is None or usage_identity not in seen_usage_events:
                        summary.token_count += _usage_token_count(message.get("usage"))
                        if usage_identity is not None:
                            seen_usage_events.add(usage_identity)

                summary.token_count += _tool_result_token_count(entry.get("toolUseResult"))

                entry_type = entry.get("type")
                if entry_type == "assistant" and isinstance(message, dict):
                    _record_assistant_tool_calls(
                        summary,
                        message,
                        seen_tool_use_ids,
                        question_labels_by_tool_use_id,
                    )
                elif entry_type == "user" and isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        record_workspace_artifact(summary.chat_artifacts, content)
                        record_answer_selections(summary.chat_artifacts, content)
                        content = _strip_studio_context_from_prompt(content)
                        summary.message_count += 1
                        if summary.first_prompt is None:
                            summary.first_prompt = content
                    else:
                        record_user_tool_result_artifacts(
                            summary.chat_artifacts,
                            content,
                            question_labels_by_tool_use_id,
                        )
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
            tool_use = {
                "type": "tool_use",
                "name": part.get("name") or "tool",
                "input": part.get("input") or {},
            }
            tool_use_id = part.get("id")
            if isinstance(tool_use_id, str) and tool_use_id:
                tool_use["id"] = tool_use_id
            parts.append(tool_use)
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
                chat_artifacts=summary.chat_artifacts,
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
    summary = _summarize_history_session(path)
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
    return SessionHistoryResponse(session_id=sid, items=items, chat_artifacts=summary.chat_artifacts)


@router.get("/skills", response_model=list[ClaudeSkillResponse])
def list_claude_skills() -> list[ClaudeSkillResponse]:
    """List NeMo skills that the repo's Claude Code installer exposes."""
    try:
        return list_claude_skill_responses(SERVER_CWD)
    except DuplicateSkillError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
        "--allowedTools",
        ",".join(allowed_mcp_tools(CLAUDE_MCP_SERVER_NAME)),
        "--append-system-prompt",
        STUDIO_CODING_AGENT_CONTEXT,
        "--permission-prompt-tool",
        permission_prompt_tool(CLAUDE_MCP_SERVER_NAME),
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


async def _request_agent_input(session_id: str, kind: str, args: dict[str, Any]) -> dict[str, Any]:
    queue = _session_streams.get(session_id)
    if queue is None:
        return {"status": "error", "message": "no active Studio coding-agent session"}

    request_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()
    _pending_agent_inputs[request_id] = (session_id, future)

    payload = json.dumps(
        {
            "request_id": request_id,
            "kind": kind,
            "input": args,
        }
    )
    await queue.put(("input_request", payload))

    try:
        decision = await asyncio.wait_for(future, timeout=300)
    except asyncio.TimeoutError:
        return {"status": "error", "message": "input request timed out"}
    finally:
        _pending_agent_inputs.pop(request_id, None)

    if decision.get("skipped"):
        return {"status": "skipped"}

    value = decision.get("value")
    if isinstance(value, dict):
        reserved_keys = sorted(_AGENT_INPUT_RESPONSE_RESERVED_KEYS.intersection(value))
        if reserved_keys:
            return {
                "status": "error",
                "message": f"input value included reserved keys: {', '.join(reserved_keys)}",
            }
        return {"status": "submitted", **value}

    return {"status": "error", "message": "input request resolved without a value"}


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
            elif event_type == "input_request":
                yield _sse(payload, event="input_request")

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
    enabled_destinations = studio_links.enabled_destinations_from_request(request)
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


@router.post("/sessions/{session_id}/inputs/{request_id}")
async def resolve_agent_input(session_id: str, request_id: str, body: AgentInputDecision) -> dict[str, bool]:
    """Resolve a pending Claude UI input request."""
    sid = _validate_session_id(session_id)
    pending = _pending_agent_inputs.get(request_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="no such pending input")
    pending_session_id, future = pending
    if pending_session_id != sid or future.done():
        raise HTTPException(status_code=404, detail="no such pending input")
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
        enabled_destinations = studio_links.enabled_destinations_from_request(request)
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

        if name == SELECT_AGENT_TOOL_NAME:
            result = await _request_agent_input(sid, "agent", args)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    },
                }
            )

        if name == SELECT_EVAL_CONFIG_TOOL_NAME:
            result = await _request_agent_input(sid, "eval_config", args)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    },
                }
            )

        if name == SELECT_DATASET_FILE_TOOL_NAME:
            result = await _request_agent_input(sid, "dataset_file", args)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    },
                }
            )

        if name == SELECT_MODEL_TOOL_NAME:
            result = await _request_agent_input(sid, "model", args)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    },
                }
            )

        if name == JOB_PROGRESS_TOOL_NAME:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"status": "rendered"})}],
                    },
                }
            )

        if name == APPROVAL_TOOL_NAME:
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

        if name == STUDIO_LINK_TOOL_NAME:
            workspace = _trimmed_string(request.query_params.get("workspace"))
            studio_base_url = _trimmed_string(request.query_params.get("studio_base_url"))
            enabled_destinations = studio_links.enabled_destinations_from_request(request)
            result = studio_links.build_studio_link_result(workspace, studio_base_url, args, enabled_destinations)
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
