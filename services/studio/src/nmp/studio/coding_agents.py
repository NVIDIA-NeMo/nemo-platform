# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local coding-agent bridge for Studio."""

import asyncio
import json
import logging
import os
import shutil
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
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


_STUDIO_LINK_DESTINATIONS: dict[str, StudioLinkDestination] = {
    "dashboard": StudioLinkDestination("Workspace dashboard", "/workspaces/{workspace}/dashboard"),
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
    "agent_deployments": StudioLinkDestination(
        "Agent deployments",
        "/workspaces/{workspace}/agent-deployments",
        aliases=("agent_deployment_list",),
    ),
    "agent_deployment": StudioLinkDestination(
        "Agent deployment {name}",
        "/workspaces/{workspace}/agent-deployments/{name}",
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
    "customizations": StudioLinkDestination(
        "Custom Models",
        "/workspaces/{workspace}/customizations",
        aliases=("custom_models", "custom_models_page", "customization_jobs", "customizations_page"),
    ),
    "customization": StudioLinkDestination(
        "Custom model {name}",
        "/workspaces/{workspace}/customizations/{name}",
        aliases=("custom_model", "customization_job", "customization_detail"),
        requires_name=True,
    ),
    "jobs": StudioLinkDestination("Jobs", "/workspaces/{workspace}/jobs", aliases=("job_list",)),
    "job": StudioLinkDestination(
        "Job {name}",
        "/workspaces/{workspace}/jobs/{name}",
        aliases=("job_detail",),
        requires_name=True,
    ),
    "filesets": StudioLinkDestination("Filesets", "/workspaces/{workspace}/filesets"),
    "fileset": StudioLinkDestination(
        "Fileset {name}",
        "/workspaces/{workspace}/filesets/{name}/detail",
        aliases=("fileset_detail", "dataset", "dataset_detail"),
        requires_name=True,
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
    "data_designer": StudioLinkDestination(
        "Data Designer",
        "/workspaces/{workspace}/data-designer",
        aliases=("data_designer_jobs",),
    ),
    "safe_synthesizer": StudioLinkDestination(
        "Safe Synthesizer",
        "/workspaces/{workspace}/safe-synthesizer",
        aliases=("safe_synthesizer_jobs",),
    ),
}

_STUDIO_LINK_DESTINATION_ALIASES = {
    alias: destination for destination, config in _STUDIO_LINK_DESTINATIONS.items() for alias in config.aliases
}


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
        "Use this after every successful Studio action that creates, starts, deploys, evaluates, modifies, "
        "or inspects a resource so the user can open the relevant Studio page. "
        "Prefer the most specific destination when you know the resource name; otherwise link to the list page. "
        "Examples: after starting a platform job, use destination='job' with name when available, or destination='jobs'; "
        "after creating an agent, use destination='agent' with name when available, or destination='agents'. "
        "Include the returned markdown link exactly in your final response."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": (
                    "Studio destination. Supported values: agents, agent, agent_deployments, "
                    "agent_deployment, agent_evaluations, agent_evaluation, agent_monitor, "
                    "agent_optimizations, customizations, customization, dashboard, jobs, job, filesets, fileset, deployments, "
                    "deployment, inference_providers, guardrails, secrets, data_designer, safe_synthesizer."
                ),
            },
            "name": {
                "type": "string",
                "description": "Resource name for detail destinations such as agent, job, fileset, or deployment.",
            },
            "label": {
                "type": "string",
                "description": "Optional markdown link label. Defaults to the destination label.",
            },
        },
        "required": ["destination"],
    },
}

_MCP_TOOLS = [_APPROVAL_TOOL, _STUDIO_LINK_TOOL]


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
) -> str:
    normalized_base_url = _normalize_studio_base_url(studio_base_url)
    current_studio_route = _trimmed_string(studio_pathname) or "unknown"
    return "\n".join(
        [
            STUDIO_CONTEXT_START,
            "You are being invoked from inside NeMo Studio's Code Agent chat.",
            f"Current Studio workspace: {workspace or 'unknown'}",
            f"Studio UI base URL: {normalized_base_url or 'unknown'}",
            f"Current Studio route path: {current_studio_route}",
            "When the user asks for a Studio page link, do not ask them for the base URL.",
            "Always use the current Studio workspace for Studio UI links unless the user explicitly names another workspace.",
            "Do not infer the Studio workspace from the local username, account name, API response defaults, or filesystem paths.",
            "Use the mcp__nemo_studio__studio_link tool for Studio UI links whenever possible.",
            "Use the returned markdown from studio_link exactly; do not replace it with localhost, the API host, or the MCP server host.",
            "The MCP server URL is an internal callback for tools, not the Studio UI base URL.",
            "If you must construct a Studio UI link manually, prefer a relative Markdown link that starts with /workspaces/ or /models/.",
            "After any successful Studio action, include a Studio link in the response.",
            "For a newly started job, use studio_link with destination='job' and the job name when available; otherwise use destination='jobs'.",
            "For a newly created or deployed agent, use destination='agent' or destination='agent_deployment' when the name is known; otherwise use destination='agents' or destination='agent_deployments'.",
            "For generated filesets, custom models, deployments, evaluations, guardrails, secrets, Data Designer, or Safe Synthesizer work, choose the matching studio_link destination.",
            "For Custom Models use destination='customizations'; for Agents use destination='agents'.",
            "Return Studio links as Markdown links.",
            STUDIO_CONTEXT_END,
            "",
            STUDIO_CONTEXT_USER_REQUEST_PREFIX,
            message,
        ]
    )


def _path_part(value: str) -> str:
    return quote(value, safe="")


def _normalize_studio_link_destination(destination: str) -> str | None:
    normalized = destination.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _STUDIO_LINK_DESTINATIONS:
        return normalized
    return _STUDIO_LINK_DESTINATION_ALIASES.get(normalized)


def _build_studio_link_result(
    workspace: str | None,
    studio_base_url: str | None,
    args: dict[str, Any],
) -> dict[str, Any]:
    if not workspace:
        return {
            "error": "current Studio workspace is unavailable",
            "available_destinations": sorted(_STUDIO_LINK_DESTINATIONS),
        }

    requested_destination = (
        _trimmed_string(args.get("destination"))
        or _trimmed_string(args.get("page"))
        or _trimmed_string(args.get("resource_type"))
    )
    if requested_destination is None:
        return {
            "error": "destination is required",
            "available_destinations": sorted(_STUDIO_LINK_DESTINATIONS),
        }

    destination = _normalize_studio_link_destination(requested_destination)
    if destination is None:
        return {
            "error": f"unknown Studio destination: {requested_destination}",
            "available_destinations": sorted(_STUDIO_LINK_DESTINATIONS),
        }

    config = _STUDIO_LINK_DESTINATIONS[destination]
    name = _trimmed_string(args.get("name")) or _trimmed_string(args.get("resource_name"))
    if config.requires_name and name is None:
        return {"error": f"name is required for Studio destination: {destination}"}

    path = config.path_template.format(
        workspace=_path_part(workspace),
        name=_path_part(name or ""),
    )
    label = _trimmed_string(args.get("label")) or config.label.format(name=name or "")
    url = _build_studio_url(studio_base_url, path)

    return {
        "workspace": workspace,
        "destination": destination,
        "path": path,
        "url": url,
        "markdown": f"[{label}]({path})",
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


def _build_claude_argv(session_id: str, message: str, mcp_url: str) -> list[str]:
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
    return [
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
        session_flag,
        session_id,
    ]


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


async def _stream_claude(session_id: str, message: str, mcp_url: str) -> AsyncIterator[str]:
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
    argv = _build_claude_argv(session_id, message, mcp_url)
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
    studio_base_url = _normalize_studio_base_url(body.studio_base_url)
    studio_pathname = _trimmed_string(body.studio_pathname)
    message = _build_claude_prompt(body.message, workspace, studio_base_url, studio_pathname)
    return StreamingResponse(
        _stream_claude(sid, message, _mcp_url(request, sid, workspace, studio_base_url)),
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
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": _MCP_TOOLS},
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
            result = _build_studio_link_result(workspace, studio_base_url, args)
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
