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
from pathlib import Path
from typing import Any

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


class NewSessionResponse(BaseModel):
    """Response returned when Studio starts a new coding-agent session."""

    session_id: str


class MessageRequest(BaseModel):
    """A user message to send to the local coding agent."""

    message: str = Field(min_length=1)


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


class SessionHistoryResponse(BaseModel):
    """Claude session history normalized for Studio chat replay."""

    session_id: str
    items: list[dict[str, Any]]


_initialized_sessions: set[str] = set()
_session_streams: dict[str, asyncio.Queue[tuple[str, Any]]] = {}
_pending_permissions: dict[str, asyncio.Future[dict[str, Any]]] = {}


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


def _project_history_dir() -> Path:
    encoded = str(SERVER_CWD).replace("/", "-")
    return CLAUDE_PROJECTS_DIR / encoded


def _first_user_prompt_and_count(path: Path) -> tuple[str | None, int]:
    first_prompt: str | None = None
    count = 0
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
                if entry.get("type") != "user" or entry.get("isSidechain"):
                    continue
                content = (entry.get("message") or {}).get("content")
                if not isinstance(content, str):
                    continue
                count += 1
                if first_prompt is None:
                    first_prompt = content
    except OSError:
        return None, 0
    return first_prompt, count


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

        first_prompt, count = _first_user_prompt_and_count(history_file)
        if count == 0:
            continue

        try:
            mtime = history_file.stat().st_mtime
        except OSError:
            continue

        sessions.append(
            HistorySessionResponse(
                session_id=history_file.stem,
                mtime=mtime,
                first_prompt=first_prompt or "",
                message_count=count,
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
                        items.append({"kind": "user", "text": content})
                elif entry_type == "assistant" and isinstance(message, dict):
                    parts = _extract_assistant_parts(message.get("content"))
                    if parts:
                        items.append({"kind": "assistant", "parts": parts})
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _initialized_sessions.add(sid)
    return SessionHistoryResponse(session_id=sid, items=items)


def _mcp_url(request: Request, session_id: str) -> str:
    for route_name in (PUBLIC_MCP_ROUTE_NAME, MCP_ROUTE_NAME):
        try:
            return str(request.url_for(route_name, session_id=session_id))
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
    _pending_permissions[request_id] = future

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
    except OSError as exc:
        _session_streams.pop(session_id, None)
        yield _sse(json.dumps({"exit_code": None, "stderr": str(exc)}), event="error")
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
    return StreamingResponse(
        _stream_claude(sid, body.message, _mcp_url(request, sid)),
        media_type="text/event-stream",
    )


@router.post("/sessions/{session_id}/permissions/{request_id}")
async def resolve_permission(session_id: str, request_id: str, body: PermissionDecision) -> dict[str, bool]:
    """Resolve a pending Claude tool permission request."""
    _validate_session_id(session_id)
    future = _pending_permissions.get(request_id)
    if future is None or future.done():
        raise HTTPException(status_code=404, detail="no such pending permission")
    future.set_result(body.model_dump())
    return {"ok": True}


@router.post("/mcp/{session_id}", name=MCP_ROUTE_NAME, include_in_schema=False)
async def mcp_endpoint(session_id: str, request: Request) -> Response:
    """Minimal MCP endpoint used by Claude's permission-prompt tool."""
    sid = _validate_session_id(session_id)
    body = await request.json()
    request_id = body.get("id")

    if request_id is None:
        return Response(status_code=202)

    method = body.get("method")
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
                "result": {"tools": [_APPROVAL_TOOL]},
            }
        )

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name != "approval_prompt":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"unknown tool: {name}"},
                }
            )

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

    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    )
