# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MCP tool catalog for Studio coding-agent sessions."""

from typing import Any

CLAUDE_MCP_SERVER_NAME = "nemo_studio"

APPROVAL_TOOL_NAME = "approval_prompt"
STUDIO_LINK_TOOL_NAME = "studio_link"
SELECT_AGENT_TOOL_NAME = "select_agent"
SELECT_EVAL_CONFIG_TOOL_NAME = "select_eval_config"
SELECT_DATASET_FILE_TOOL_NAME = "select_dataset_file"
SELECT_MODEL_TOOL_NAME = "select_model"
JOB_PROGRESS_TOOL_NAME = "job_progress"

APPROVAL_TOOL: dict[str, Any] = {
    "name": APPROVAL_TOOL_NAME,
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

SELECT_AGENT_TOOL: dict[str, Any] = {
    "name": SELECT_AGENT_TOOL_NAME,
    "description": (
        "Ask the Studio user to choose an agent from a visual dropdown. "
        "Use this instead of plain text prompting when a Studio workflow needs a concrete agent name."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "default_agent": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

SELECT_EVAL_CONFIG_TOOL: dict[str, Any] = {
    "name": SELECT_EVAL_CONFIG_TOOL_NAME,
    "description": (
        "Ask the Studio user to choose an evaluation YAML file from a visual fileset file picker. "
        "Use this instead of plain text prompting when an agent evaluation workflow needs an eval config. "
        "Returns eval_config_fileset and eval_config. If the user does not have a config yet, "
        "Studio may return needs_eval_config=true so you can help create one. "
        "Studio may also return use_sample_eval_config=true with a sample eval_config and eval_config_fileset."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "agent": {"type": "string"},
            "default_agent": {"type": "string"},
            "accepted_file_types": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    },
}

SELECT_DATASET_FILE_TOOL: dict[str, Any] = {
    "name": SELECT_DATASET_FILE_TOOL_NAME,
    "description": (
        "Ask the Studio user to choose a dataset file from a visual fileset file picker. "
        "Use this instead of plain text prompting when a workflow needs source data, "
        "for example while helping create an evaluation config. Returns dataset_fileset and dataset_path."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "accepted_file_types": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    },
}

SELECT_MODEL_TOOL: dict[str, Any] = {
    "name": SELECT_MODEL_TOOL_NAME,
    "description": (
        "Ask the Studio user to choose a model from a visual model picker. "
        "Use this instead of plain text prompting when a Studio workflow needs a concrete model name. "
        "Returns model by default. You may pass output_key to request a different response key."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "default_model": {"type": "string"},
            "output_key": {"type": "string"},
            "display_label": {"type": "string"},
            "field_label": {"type": "string"},
            "placeholder": {"type": "string"},
            "required_message": {"type": "string"},
            "submit_label": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

JOB_PROGRESS_TOOL: dict[str, Any] = {
    "name": JOB_PROGRESS_TOOL_NAME,
    "description": (
        "Show a compact Studio progress card for a long-running job. "
        "Call this only after a real Studio job has been started and you know its job_name. "
        "Pass job_type or source when known so Studio can link to the best detail page."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "job_name": {"type": "string"},
            "job_type": {
                "type": "string",
                "description": (
                    "Optional job category, such as customization, data_designer, "
                    "safe_synthesizer, evaluator, or agent_evaluation."
                ),
            },
            "source": {
                "type": "string",
                "description": "Optional platform job source, such as customization or data-designer.",
            },
            "title": {"type": "string"},
            "description": {"type": "string"},
            "workspace": {"type": "string"},
        },
        "required": ["job_name"],
        "additionalProperties": False,
    },
}

MCP_TOOLS: list[dict[str, Any]] = [
    APPROVAL_TOOL,
    SELECT_AGENT_TOOL,
    SELECT_EVAL_CONFIG_TOOL,
    SELECT_DATASET_FILE_TOOL,
    SELECT_MODEL_TOOL,
    JOB_PROGRESS_TOOL,
]

STUDIO_UI_TOOL_NAMES = (
    SELECT_AGENT_TOOL_NAME,
    SELECT_EVAL_CONFIG_TOOL_NAME,
    SELECT_DATASET_FILE_TOOL_NAME,
    SELECT_MODEL_TOOL_NAME,
    JOB_PROGRESS_TOOL_NAME,
    STUDIO_LINK_TOOL_NAME,
)

STUDIO_CODING_AGENT_CONTEXT = "\n".join(
    [
        "You are running inside NeMo Studio's Code Agent chat.",
        "NeMo Studio and the NeMo Platform API are already running for this workspace.",
        "Do not spend time starting the platform or checking whether Studio is up unless the user asks.",
        "Your local shell and file tools may be sandboxed; use the normal Studio approval flow when needed.",
        (
            "When you need to prompt the user for input, use a Studio UI tool instead of writing a "
            "plain-text question whenever a suitable tool exists."
        ),
        (
            "Use mcp__nemo_studio__select_agent for agent names, "
            "mcp__nemo_studio__select_model for model names, "
            "mcp__nemo_studio__select_dataset_file for dataset or source files, and "
            "mcp__nemo_studio__select_eval_config for evaluation config files."
        ),
        (
            "For broader clarification, multiple-choice, yes/no, or freeform questions, use Claude "
            "Code's AskUserQuestion tool rather than writing a questionnaire in markdown."
        ),
        (
            "Only fall back to plain chat questions when no suitable UI tool is available, the user "
            "already provided the value, or the UI tool returns skipped or error."
        ),
        (
            "Set UI tool titles, descriptions, display labels, and output_key values to match the "
            "current workflow while keeping the tools reusable."
        ),
        (
            "When you start a long-running Studio job and a matching progress/status MCP tool is "
            "available, call it after job creation with the job id or name so Studio can render "
            "progress inline. Use mcp__nemo_studio__job_progress for Studio jobs."
        ),
    ]
)


def qualified_mcp_tool_name(tool_name: str, server_name: str = CLAUDE_MCP_SERVER_NAME) -> str:
    """Return Claude Code's fully qualified MCP tool name for a Studio tool."""
    return f"mcp__{server_name}__{tool_name}"


def allowed_mcp_tools(server_name: str = CLAUDE_MCP_SERVER_NAME) -> list[str]:
    """Return the Studio UI tools Claude may call without an approval prompt."""
    return [qualified_mcp_tool_name(tool_name, server_name) for tool_name in STUDIO_UI_TOOL_NAMES]


def permission_prompt_tool(server_name: str = CLAUDE_MCP_SERVER_NAME) -> str:
    """Return the fully qualified approval prompt tool name."""
    return qualified_mcp_tool_name(APPROVAL_TOOL_NAME, server_name)
