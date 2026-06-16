# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Artifact extraction for Studio coding-agent chat history."""

import json
import re
from typing import Any

from nmp.studio import studio_links
from pydantic import BaseModel, Field


class ChatSelectionArtifactResponse(BaseModel):
    """A user selection captured during the chat."""

    label: str
    value: str


class ChatFileArtifactResponse(BaseModel):
    """A file touched by the local coding agent."""

    action: str
    path: str


class ChatLinkArtifactResponse(BaseModel):
    """A Studio link requested by the local coding agent."""

    label: str
    destination: str | None = None
    href: str | None = None


class ChatJobArtifactResponse(BaseModel):
    """A Studio job referenced during the chat."""

    name: str
    job_type: str | None = None
    source: str | None = None
    href: str | None = None


class ChatArtifactsResponse(BaseModel):
    """Structured chat metadata shown in Studio's artifacts pane."""

    agent: str | None = None
    model: str | None = None
    model_source: str | None = None
    coding_agent_model: str | None = None
    workspace: str | None = None
    selections: list[ChatSelectionArtifactResponse] = Field(default_factory=list)
    files: list[ChatFileArtifactResponse] = Field(default_factory=list)
    links: list[ChatLinkArtifactResponse] = Field(default_factory=list)
    jobs: list[ChatJobArtifactResponse] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


_ANSWER_PAIR_RE = re.compile(r'"((?:\\.|[^"\\])*)"\s*=\s*"((?:\\.|[^"\\])*)"')
_INLINE_CODE_VALUE_RE = re.compile(r"(`+)(?P<value>.*?)\1", re.DOTALL)
_MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<href>[^)]+)\)")
_FILE_CHANGE_TOOL_ACTIONS = {
    "Edit": "Edited",
    "MultiEdit": "Edited",
    "Write": "Wrote",
}
_STUDIO_CONTEXT_WORKSPACE_RE = re.compile(r"^Current Studio workspace:\s*(?P<workspace>.+)$", re.MULTILINE)
_SPEC_HEADINGS = {
    "behavior",
    "change scope",
    "evaluation setup",
    "framework",
    "harness",
    "model",
    "name",
    "open questions",
    "purpose",
    "role",
    "scope",
    "signals",
    "success criteria",
    "tools",
}


def string_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _append_unique_string(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _clean_artifact_value(value: str) -> str:
    stripped = value.strip()
    match = _INLINE_CODE_VALUE_RE.search(stripped)
    if not match:
        return stripped
    unwrapped = match.group("value").strip()
    return unwrapped or stripped


def record_tool_name(artifacts: ChatArtifactsResponse, tool_name: str) -> None:
    _append_unique_string(artifacts.tools, tool_name)


def record_coding_agent_model(artifacts: ChatArtifactsResponse, model: str | None) -> None:
    if not model:
        return
    artifacts.coding_agent_model = model


def _set_spec_model(artifacts: ChatArtifactsResponse, model: str) -> None:
    artifacts.model = _clean_artifact_value(model)
    artifacts.model_source = "spec"


def _set_selection_artifact(artifacts: ChatArtifactsResponse, label: str, value: str) -> None:
    cleaned_value = _clean_artifact_value(value)
    if label == "Agent":
        artifacts.agent = cleaned_value
    elif label == "Model":
        artifacts.model = cleaned_value
        artifacts.model_source = "selection"

    for index, selection in enumerate(artifacts.selections):
        if selection.label == label:
            artifacts.selections[index] = ChatSelectionArtifactResponse(
                label=label,
                value=cleaned_value,
            )
            return
    artifacts.selections.append(ChatSelectionArtifactResponse(label=label, value=cleaned_value))


def _selection_label(question: str, header: str | None = None) -> str:
    combined = f"{header or ''} {question}".lower()
    if "agent" in combined:
        return "Agent"
    if "model" in combined:
        return "Model"
    if "deployment" in combined:
        return "Deployment"
    if "fileset" in combined:
        return "Fileset"
    if "dataset" in combined:
        return "Dataset"
    if "provider" in combined:
        return "Provider"

    label = header or question.strip().rstrip("?")
    return label[:40] if len(label) > 40 else label


def _decode_answer_pair_value(value: str) -> str:
    try:
        decoded = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace('\\"', '"').replace("\\\\", "\\")
    return decoded if isinstance(decoded, str) else value


def record_answer_selections(
    artifacts: ChatArtifactsResponse,
    text: str,
    question_labels: dict[str, str] | None = None,
) -> None:
    for match in _ANSWER_PAIR_RE.finditer(text):
        question = _decode_answer_pair_value(match.group(1)).strip()
        answer = _decode_answer_pair_value(match.group(2)).strip()
        if not question or not answer:
            continue
        label = question_labels.get(question) if question_labels else None
        _set_selection_artifact(artifacts, label or _selection_label(question), answer)


def _ask_user_question_labels(input_value: Any) -> dict[str, str]:
    if not isinstance(input_value, dict):
        return {}

    questions = input_value.get("questions")
    if not isinstance(questions, list):
        question = string_value(input_value.get("question"))
        if not question:
            return {}
        return {question: _selection_label(question, string_value(input_value.get("header")))}

    labels: dict[str, str] = {}
    for question_value in questions:
        if not isinstance(question_value, dict):
            continue
        question = string_value(question_value.get("question"))
        if not question:
            continue
        labels[question] = _selection_label(question, string_value(question_value.get("header")))
    return labels


def _upsert_file_artifact(artifacts: ChatArtifactsResponse, action: str, path: str) -> None:
    for index, file_artifact in enumerate(artifacts.files):
        if file_artifact.path == path:
            artifacts.files[index] = ChatFileArtifactResponse(action=action, path=path)
            return
    artifacts.files.append(ChatFileArtifactResponse(action=action, path=path))


def _markdown_link_parts(value: str) -> tuple[str | None, str | None]:
    match = _MARKDOWN_LINK_RE.search(value)
    if not match:
        return None, None
    return match.group("label").strip() or None, match.group("href").strip() or None


def _studio_link_artifact_from_input(
    input_value: dict[str, Any],
    workspace: str | None,
) -> ChatLinkArtifactResponse | None:
    destination = (
        string_value(input_value.get("destination"))
        or string_value(input_value.get("page"))
        or string_value(input_value.get("resource_type"))
    )
    label = string_value(input_value.get("label")) or destination
    href = string_value(input_value.get("href")) or string_value(input_value.get("url"))

    if workspace:
        result = studio_links.build_studio_link_result(workspace, None, input_value)
        if "markdown" in result:
            markdown_label, markdown_href = _markdown_link_parts(str(result["markdown"]))
            label = string_value(input_value.get("label")) or markdown_label or label
            href = string_value(result.get("url")) or string_value(result.get("path")) or markdown_href or href
            destination = string_value(result.get("destination")) or destination

    if not label:
        return None

    return ChatLinkArtifactResponse(label=label, destination=destination, href=href)


def _append_link_artifact(artifacts: ChatArtifactsResponse, input_value: Any) -> None:
    if not isinstance(input_value, dict):
        return
    artifact = _studio_link_artifact_from_input(input_value, artifacts.workspace)
    if artifact is None:
        return

    for link in artifacts.links:
        if link.label == artifact.label and link.destination == artifact.destination:
            if artifact.href and not link.href:
                link.href = artifact.href
            return
    artifacts.links.append(artifact)


def _upsert_job_artifact(
    artifacts: ChatArtifactsResponse,
    name: str,
    job_type: str | None = None,
    source: str | None = None,
    href: str | None = None,
) -> None:
    for index, job in enumerate(artifacts.jobs):
        if job.name != name:
            continue
        artifacts.jobs[index] = ChatJobArtifactResponse(
            name=name,
            job_type=job_type or job.job_type,
            source=source or job.source,
            href=href or job.href,
        )
        return

    artifacts.jobs.append(ChatJobArtifactResponse(name=name, job_type=job_type, source=source, href=href))


def _append_job_artifact(artifacts: ChatArtifactsResponse, input_value: Any) -> None:
    if not isinstance(input_value, dict):
        return

    name = string_value(input_value.get("job_name")) or string_value(input_value.get("name"))
    if not name:
        return

    _upsert_job_artifact(
        artifacts,
        name=name,
        job_type=string_value(input_value.get("job_type")) or string_value(input_value.get("type")),
        source=string_value(input_value.get("source")),
        href=string_value(input_value.get("href")) or string_value(input_value.get("url")),
    )


def _normalize_spec_line(line: str) -> str:
    normalized = line.strip()
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    normalized = re.sub(r"^\s*[-*]\s+", "", normalized)
    return normalized.replace("**", "").strip()


def _normalize_heading(line: str) -> str:
    return _normalize_spec_line(line).removesuffix(":").strip().lower()


def _inline_spec_value(text: str, label: str) -> str | None:
    prefix = f"{label.lower()}:"
    for line in text.splitlines():
        normalized = _normalize_spec_line(line)
        if not normalized.lower().startswith(prefix):
            continue
        return string_value(normalized[len(prefix) :])
    return None


def _clean_spec_value(value: str) -> str:
    normalized = _normalize_spec_line(value)
    without_parenthetical = re.sub(r"\s+\([^)]*\)\s*$", "", normalized).strip()
    return _clean_artifact_value(without_parenthetical or normalized)


def _section_spec_value(text: str, heading: str) -> str | None:
    lines = text.splitlines()
    target_heading = heading.lower()
    for index, line in enumerate(lines):
        if _normalize_heading(line) != target_heading:
            continue
        for value_line in lines[index + 1 :]:
            normalized = _normalize_spec_line(value_line)
            if not normalized:
                continue
            if _normalize_heading(normalized) in _SPEC_HEADINGS:
                return None
            return _clean_spec_value(normalized)
    return None


def record_spec_text_artifacts(artifacts: ChatArtifactsResponse, text: str) -> None:
    agent_name = _inline_spec_value(text, "Name") or _inline_spec_value(text, "Draft Spec")
    if agent_name:
        artifacts.agent = _clean_spec_value(agent_name)

    model = _section_spec_value(text, "Model") or _inline_spec_value(text, "Model")
    if model:
        _set_spec_model(artifacts, _clean_spec_value(model))


def record_tool_artifacts(
    artifacts: ChatArtifactsResponse,
    tool_name: str,
    input_value: Any,
    tool_use_id: str | None,
    question_labels_by_tool_use_id: dict[str, dict[str, str]],
) -> None:
    if tool_name == "AskUserQuestion" and tool_use_id:
        labels = _ask_user_question_labels(input_value)
        if labels:
            question_labels_by_tool_use_id[tool_use_id] = labels

    action = _FILE_CHANGE_TOOL_ACTIONS.get(tool_name)
    if action and isinstance(input_value, dict):
        path = string_value(input_value.get("file_path")) or string_value(input_value.get("path"))
        if path:
            _upsert_file_artifact(artifacts, action, path)

    if tool_name == "studio_link" or tool_name.endswith("__studio_link"):
        _append_link_artifact(artifacts, input_value)
        if isinstance(input_value, dict):
            destination = (
                string_value(input_value.get("destination"))
                or string_value(input_value.get("page"))
                or string_value(input_value.get("resource_type"))
            )
            if destination == "job":
                _append_job_artifact(artifacts, input_value)

    if tool_name == "job_progress" or tool_name.endswith("__job_progress"):
        _append_job_artifact(artifacts, input_value)


def record_workspace_artifact(artifacts: ChatArtifactsResponse, content: str) -> None:
    if artifacts.workspace:
        return
    match = _STUDIO_CONTEXT_WORKSPACE_RE.search(content)
    if match:
        artifacts.workspace = match.group("workspace").strip()


def record_user_tool_result_artifacts(
    artifacts: ChatArtifactsResponse,
    content: Any,
    question_labels_by_tool_use_id: dict[str, dict[str, str]],
) -> None:
    if not isinstance(content, list):
        return

    for part in content:
        if not isinstance(part, dict) or part.get("type") != "tool_result":
            continue
        result_text = string_value(part.get("content"))
        if not result_text:
            continue
        tool_use_id = string_value(part.get("tool_use_id"))
        labels = question_labels_by_tool_use_id.get(tool_use_id or "")
        record_answer_selections(artifacts, result_text, labels)
