# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read and normalize captured agent artifacts."""

import json
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class FinalAnswer(BaseModel):
    """Normalized final-answer extraction result."""

    model_config = ConfigDict(extra="forbid")

    extracted: bool
    text: str = ""
    source: str | None = None


class AgentArtifacts(BaseModel):
    """Captured files emitted by an agent run."""

    model_config = ConfigDict(extra="forbid")

    agent_log_dir: Path
    workspace_dir: Path | None = None
    final_answer: FinalAnswer
    raw_text: str = ""
    atif_trajectory_path: Path | None = None
    virtual_workspace_files: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_dir(cls, agent_log_dir: str | Path, *, workspace_dir: str | Path | None = None) -> Self:
        """Load known agent artifacts from a mounted ``/logs/agent`` directory."""
        root = Path(agent_log_dir)
        workspace = Path(workspace_dir) if workspace_dir is not None else None
        virtual_workspace_files = _read_virtual_workspace_files(root)
        _materialize_virtual_workspace_files(workspace, virtual_workspace_files)
        final_answer = _read_final_answer(root)
        raw_text = _read_raw_text(root, virtual_workspace_files=virtual_workspace_files)
        atif_trajectory_path = _find_atif_trajectory(root)
        return cls(
            agent_log_dir=root,
            workspace_dir=workspace,
            final_answer=final_answer,
            raw_text=raw_text,
            atif_trajectory_path=atif_trajectory_path,
            virtual_workspace_files=virtual_workspace_files,
        )

    def workspace_artifact(self, relative_path: str | Path) -> Path | None:
        """Return a workspace artifact path when it stays inside the workspace."""
        if self.workspace_dir is None:
            return None
        candidate = self.workspace_dir / relative_path
        try:
            candidate.resolve().relative_to(self.workspace_dir.resolve())
        except ValueError:
            return None
        return candidate

    def workspace_file_text(self, relative_path: str | Path) -> str | None:
        """Return text for a real or log-reconstructed workspace file."""
        path = self.workspace_artifact(relative_path)
        if path is not None and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            return text or None

        key = _workspace_relative_path(str(relative_path))
        if key is None:
            return None
        text = self.virtual_workspace_files.get(key)
        return text.strip() if text else None


def _read_final_answer(root: Path) -> FinalAnswer:
    structured_path = root / "final_message.json"
    if structured_path.is_file():
        extracted = _final_answer_from_json_text(structured_path.read_text(encoding="utf-8", errors="replace"))
        if extracted.extracted:
            return FinalAnswer(extracted=True, text=extracted.text, source=f"{structured_path.name}:{extracted.source}")
        return FinalAnswer(extracted=False, source=structured_path.name)

    text_path = root / "final_message.txt"
    if text_path.is_file():
        text = text_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return FinalAnswer(extracted=False, source=text_path.name)
        parsed = _final_answer_from_json_text(text)
        if parsed.extracted:
            return FinalAnswer(extracted=True, text=parsed.text, source=f"{text_path.name}:{parsed.source}")
        if _looks_like_json(text):
            return FinalAnswer(extracted=False, source=text_path.name)
        return FinalAnswer(extracted=True, text=text, source=text_path.name)

    for name in ("nat_agent.log", "stdout.txt", "output.txt", "claude-code.txt"):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        parsed = _final_answer_from_json_text(text)
        if parsed.extracted:
            return FinalAnswer(extracted=True, text=parsed.text, source=f"{name}:{parsed.source}")
        if not _looks_like_json(text):
            return FinalAnswer(extracted=True, text=text, source=name)

    return FinalAnswer(extracted=False)


def _read_raw_text(root: Path, *, virtual_workspace_files: dict[str, str]) -> str:
    parts: list[str] = []
    for name in (
        "final_message.txt",
        "nat_agent.log",
        "nat_agent.stderr",
        "stdout.txt",
        "stderr.txt",
        "output.txt",
        "claude-code.txt",
    ):
        path = root / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    parts.extend(virtual_workspace_files.values())
    return "\n".join(parts)


def _final_answer_from_json_text(text: str) -> FinalAnswer:
    stripped = text.strip()
    if not stripped:
        return FinalAnswer(extracted=False)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return _final_answer_from_jsonl(stripped)
    return _final_answer_from_payload(payload, source="json")


def _final_answer_from_jsonl(text: str) -> FinalAnswer:
    final_answer = FinalAnswer(extracted=False)
    saw_json_line = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        saw_json_line = True
        candidate = _final_answer_from_payload(event, source="jsonl")
        if candidate.extracted:
            final_answer = candidate
    if final_answer.extracted or saw_json_line:
        return final_answer
    return FinalAnswer(extracted=False)


def _final_answer_from_payload(payload: Any, *, source: str) -> FinalAnswer:
    if not isinstance(payload, dict):
        return FinalAnswer(extracted=False, source=source)

    for key in ("result", "response", "output", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return FinalAnswer(extracted=True, text=value.strip(), source=f"{source}.{key}")

    content = payload.get("content")
    content_text = _content_to_text(content)
    if content_text:
        return FinalAnswer(extracted=True, text=content_text, source=f"{source}.content")

    message = payload.get("message")
    if isinstance(message, dict):
        content_text = _content_to_text(message.get("content"))
        if content_text:
            return FinalAnswer(extracted=True, text=content_text, source=f"{source}.message.content")

    return FinalAnswer(extracted=False, source=source)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = [part.get("text", "") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
    return "".join(parts).strip()


def _looks_like_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _find_atif_trajectory(root: Path) -> Path | None:
    for relative_path in ("trajectory.json", "atif_trajectory.json", "atif/trajectory.json"):
        path = root / relative_path
        if path.exists() and path.is_file():
            return path
    return None


def _read_virtual_workspace_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    path = root / "claude-code.txt"
    if not path.is_file():
        return files

    for event in _iter_jsonl(path):
        _capture_written_files(event, files)
    return files


def _iter_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            continue


def _capture_written_files(event: Any, files: dict[str, str]) -> None:
    if not isinstance(event, dict):
        return

    message = event.get("message")
    if isinstance(message, dict):
        for part in message.get("content", []):
            if isinstance(part, dict):
                _capture_tool_use(part, files)

    tool_result = event.get("tool_use_result")
    if isinstance(tool_result, dict):
        rel_path = _workspace_relative_path(str(tool_result.get("filePath", "")))
        content = tool_result.get("content")
        if rel_path is not None and isinstance(content, str):
            files[rel_path] = content


def _capture_tool_use(part: dict[str, Any], files: dict[str, str]) -> None:
    if part.get("type") != "tool_use":
        return
    name = part.get("name")
    tool_input = part.get("input")
    if not isinstance(name, str) or not isinstance(tool_input, dict):
        return

    rel_path = _workspace_relative_path(str(tool_input.get("file_path", "")))
    if rel_path is None:
        return

    if name == "Write":
        content = tool_input.get("content")
        if isinstance(content, str):
            files[rel_path] = content
        return

    if name == "Edit":
        _apply_edit(files, rel_path, tool_input)
        return

    if name == "MultiEdit":
        edits = tool_input.get("edits")
        if isinstance(edits, list):
            for edit in edits:
                if isinstance(edit, dict):
                    _apply_edit(files, rel_path, edit)


def _apply_edit(files: dict[str, str], rel_path: str, edit: dict[str, Any]) -> None:
    old = edit.get("old_string")
    new = edit.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str):
        return
    current = files.get(rel_path)
    if current is None or old not in current:
        return
    count = -1 if edit.get("replace_all") is True else 1
    files[rel_path] = current.replace(old, new, count)


def _workspace_relative_path(file_path: str) -> str | None:
    normalized = file_path.replace("\\", "/").strip()
    if not normalized:
        return None
    if normalized.startswith("/workspace/"):
        normalized = normalized.removeprefix("/workspace/")
    elif normalized.startswith("workspace/"):
        normalized = normalized.removeprefix("workspace/")
    elif normalized.startswith("/"):
        return None

    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _materialize_virtual_workspace_files(workspace: Path | None, files: dict[str, str]) -> None:
    if workspace is None or not workspace.exists():
        return
    workspace_root = workspace.resolve()
    for rel_path, text in files.items():
        candidate = workspace / rel_path
        try:
            candidate.resolve().relative_to(workspace_root)
        except ValueError:
            continue
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(text, encoding="utf-8")
        except OSError:
            continue
