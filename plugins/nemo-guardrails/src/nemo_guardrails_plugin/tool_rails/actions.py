# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in tool rail actions for the NeMo Guardrails plugin.

Each action is registered explicitly when the plugin builds an ``LLMRails``
instance. Policy is read from ``config.custom_data`` so users can configure it
per GuardrailConfig without writing custom Colang.
"""

import json
import logging
from typing import Any

import jsonschema
from nemoguardrails.actions import action
from nemoguardrails.rails.llm.config import RailsConfig

logger = logging.getLogger(__name__)

_MISSING = object()


def _context_data(context: dict[str, Any] | None) -> dict[str, Any]:
    return context or {}


def _custom_data(config: RailsConfig | None) -> dict[str, Any]:
    return (config.custom_data if config else None) or {}


def _tool_calls(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    tool_calls = _context_data(context).get("tool_calls")
    if tool_calls is None:
        return []
    if not isinstance(tool_calls, list) or not all(isinstance(tool_call, dict) for tool_call in tool_calls):
        raise ValueError("context.tool_calls must be a list of objects")
    return tool_calls


def _tool_name(tool_call: dict[str, Any]) -> str:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return ""
    name = function.get("name")
    return name if isinstance(name, str) else ""


def _tool_names_from_context(context: dict[str, Any] | None) -> list[str]:
    tool_calls = _tool_calls(context)
    if tool_calls:
        return [_tool_name(tool_call) for tool_call in tool_calls]

    tool_name = _context_data(context).get("tool_name")
    if tool_name is None:
        return []
    if not isinstance(tool_name, str):
        raise ValueError("context.tool_name must be a string")
    return [tool_name]


def _parse_tool_arguments(tool_call: dict[str, Any], *, action_name: str) -> dict[str, Any] | None:
    """Return OpenAI tool-call arguments as a dict, or None when invalid.

    Tool-call arguments can arrive as either an already-decoded object or a JSON
    string. The tool rails only support object arguments, so malformed JSON,
    arrays, scalars, and other shapes fail closed.
    """
    function = tool_call.get("function")
    if not isinstance(function, dict):
        logger.warning("%s: missing function object; blocking", action_name)
        return None

    raw_args = function.get("arguments", {})
    if isinstance(raw_args, str):
        try:
            parsed_args = json.loads(raw_args)
        except (json.JSONDecodeError, ValueError):
            logger.warning("%s: malformed JSON arguments for tool %r; blocking", action_name, _tool_name(tool_call))
            return None
        if not isinstance(parsed_args, dict):
            logger.warning(
                "%s: JSON arguments for tool %r are not an object; blocking", action_name, _tool_name(tool_call)
            )
            return None
        return parsed_args

    if not isinstance(raw_args, dict):
        logger.warning("%s: arguments for tool %r are not an object; blocking", action_name, _tool_name(tool_call))
        return None

    return raw_args


def _tool_schemas_by_name(declared_tools: list[dict[str, Any]]) -> dict[str, dict[str, Any] | bool]:
    """Index declared schemas, rejecting duplicate tool declarations."""
    schemas: dict[str, dict[str, Any] | bool] = {}
    for tool in declared_tools:
        function = tool.get("function")
        if not isinstance(function, dict):
            continue

        name = function.get("name")
        schema = function.get("parameters", _MISSING)
        if not isinstance(name, str) or not name or schema is _MISSING:
            continue
        if name in schemas:
            raise ValueError(f"duplicate declaration for tool {name!r}")

        schemas[name] = schema
    return schemas


def _argument_violation(value: Any, rules: dict[str, Any]) -> str | None:
    """Return the violated rule name, if any."""
    text = str(value)
    blocked_keywords = rules.get("blocked_keywords") or []
    normalized_text = text.casefold()
    if any(keyword.casefold() in normalized_text for keyword in blocked_keywords):
        return "blocked_keywords"

    max_length = rules.get("max_length")
    if max_length is not None and len(text) > max_length:
        return "max_length"

    return None


def _validate_tool_result_exchange(
    prior_calls_by_id: dict[str, dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> bool:
    """Validate one assistant tool-call exchange and its following tool results.

    Each role="tool" result must refer to a distinct tool_call_id from the
    immediately preceding assistant message, and optional result names must
    match the requested tool names.
    """
    if not tool_results:
        return True

    # Tool results are only meaningful immediately after assistant tool calls.
    if not prior_calls_by_id:
        logger.debug("check_tool_result_linkage: tool results present but no prior assistant tool_calls found")
        return False

    # Within one assistant/tool-result exchange, each result should answer a distinct call.
    result_ids = [m.get("tool_call_id") for m in tool_results if m.get("tool_call_id")]
    if len(result_ids) != len(set(result_ids)):
        logger.debug("check_tool_result_linkage: duplicate tool_call_ids in results")
        return False

    for result in tool_results:
        # Every result must point back to a tool call the assistant actually requested.
        call_id = result.get("tool_call_id")
        if not call_id:
            logger.debug("check_tool_result_linkage: tool result missing tool_call_id")
            return False

        if call_id not in prior_calls_by_id:
            logger.debug("check_tool_result_linkage: tool_call_id %r not found in prior calls", call_id)
            return False

        # If the tool result includes a name, it must agree with the original call.
        result_name = result.get("name")
        if result_name:
            prior_name = prior_calls_by_id[call_id].get("function", {}).get("name")
            if prior_name and result_name != prior_name:
                logger.debug(
                    "check_tool_result_linkage: result name %r does not match prior call name %r",
                    result_name,
                    prior_name,
                )
                return False
    return True


@action(is_system_action=True)
async def check_tool_allowlist(
    context: dict[str, Any] | None = None,
    config: RailsConfig | None = None,
) -> bool:
    """Block tool calls whose name is not on the configured allowlist.

    Reads custom_data.tool_allowlist.allowed_tools (list of str).
    An absent or empty allowlist passes all tool calls.
    Fails closed on any unexpected error.

    Minimal GuardrailConfig example:
    {
      "rails": {"tool_output": {"flows": ["check tool allowlist"]}},
      "custom_data": {"tool_allowlist": {"allowed_tools": ["get_weather"]}}
    }
    """
    try:
        custom_data = _custom_data(config)
        allowed_tools = custom_data.get("tool_allowlist", {}).get("allowed_tools") or []

        if not allowed_tools:
            return True

        tool_names = _tool_names_from_context(context)
        result = all(name in allowed_tools for name in tool_names)
        logger.debug(
            "check_tool_allowlist: tool_names=%s allowed_tools=%s result=%s",
            tool_names,
            allowed_tools,
            result,
        )
        return result
    except Exception:
        logger.exception("check_tool_allowlist failed unexpectedly; blocking")
        return False


@action(is_system_action=True)
async def check_tool_arguments(
    context: dict[str, Any] | None = None,
    config: RailsConfig | None = None,
) -> bool:
    """Block tool calls whose arguments violate per-tool rules.

    Reads custom_data.tool_arguments.<tool_name>.<arg_name>:
      blocked_keywords: list[str]  — case-insensitive substring match
      max_length: int              — maximum character length of the argument value

    Tools or arguments with no configured rules are passed through.
    Fails closed on any unexpected error.

    Minimal GuardrailConfig example:
    {
      "rails": {"tool_output": {"flows": ["check tool arguments"]}},
      "custom_data": {
        "tool_arguments": {
          "query_db": {"query": {"blocked_keywords": ["DROP"], "max_length": 500}}
        }
      }
    }
    """
    try:
        tool_calls = _tool_calls(context)
        custom_data = _custom_data(config)
        rules = custom_data.get("tool_arguments") or {}

        for tc in tool_calls:
            name = _tool_name(tc)
            tool_rules = rules.get(name) or {}
            if not tool_rules:
                continue

            args = _parse_tool_arguments(tc, action_name="check_tool_arguments")
            if args is None:
                return False

            for arg_name, arg_rules in tool_rules.items():
                value = args.get(arg_name, "")
                if violation := _argument_violation(value, arg_rules):
                    logger.debug(
                        "check_tool_arguments: blocking tool=%s argument=%s rule=%s value=%r",
                        name,
                        arg_name,
                        violation,
                        value,
                    )
                    return False

        logger.debug(
            "check_tool_arguments: passed tool_names=%s",
            [_tool_name(tc) for tc in tool_calls],
        )
        return True
    except Exception:
        logger.exception("check_tool_arguments failed unexpectedly; blocking")
        return False


@action(is_system_action=True)
async def check_tool_schema(
    context: dict[str, Any] | None = None,
    config: RailsConfig | None = None,
) -> bool:
    """Validate tool call arguments against the tool's declared JSON Schema.

    Uses declared_tools from context (injected from the request's tools field)
    to find each called tool's parameters schema, then validates arguments with
    jsonschema. Tool calls with no matching declared schema are blocked.
    Fails closed on any unexpected error.

    Minimal GuardrailConfig example:
    {
      "rails": {"tool_output": {"flows": ["check tool schema"]}}
    }
    """
    try:
        context_data = _context_data(context)
        tool_calls = _tool_calls(context)
        declared_tools = context_data.get("declared_tools") or []

        if not tool_calls:
            return True
        if not declared_tools:
            logger.warning("check_tool_schema: tool calls present but request declared no tools; blocking")
            return False

        if not isinstance(declared_tools, list) or not all(isinstance(tool, dict) for tool in declared_tools):
            logger.warning("check_tool_schema: declared_tools must be a list of objects; blocking")
            return False

        try:
            schema_by_name = _tool_schemas_by_name(declared_tools)
        except ValueError as exc:
            logger.warning("check_tool_schema: %s; blocking", exc)
            return False

        for tc in tool_calls:
            name = _tool_name(tc)
            if name not in schema_by_name:
                logger.warning("check_tool_schema: no declared schema for tool %r; blocking", name)
                return False

            schema = schema_by_name[name]
            args = _parse_tool_arguments(tc, action_name="check_tool_schema")
            if args is None:
                return False

            try:
                jsonschema.validate(instance=args, schema=schema)
            except (jsonschema.SchemaError, jsonschema.ValidationError) as exc:
                logger.debug("check_tool_schema: argument validation failed for tool %r: %s", name, exc.message)
                return False

        logger.debug(
            "check_tool_schema: passed tool_names=%s",
            [_tool_name(tc) for tc in tool_calls],
        )
        return True
    except Exception:
        logger.exception("check_tool_schema failed unexpectedly; blocking")
        return False


@action(is_system_action=True)
async def check_tool_result_linkage(
    context: dict[str, Any] | None = None,
    config: RailsConfig | None = None,
) -> bool:
    """Validate that each role:'tool' result links back to a real prior tool call.

    Checks each assistant/tool-result exchange in context.messages:
    - Every tool result has a tool_call_id
    - Every tool_call_id matches a call the LLM actually made in that exchange
    - No duplicate tool_call_ids across results in the same exchange
    - If name is present on the result, it matches the prior call's function name

    Requires messages to be injected into context as context["messages"].
    Fails closed on any unexpected error.

    Minimal GuardrailConfig example:
    {
      "rails": {"tool_input": {"flows": ["check tool result linkage"]}}
    }
    """
    try:
        messages = _context_data(context).get("messages") or []

        current_calls_by_id: dict[str, dict[str, Any]] = {}  # Calls from the current assistant turn.
        current_results: list[dict[str, Any]] = []  # Results to validate against those calls.

        for message in messages:
            role = message.get("role")
            if role == "assistant":
                if not _validate_tool_result_exchange(current_calls_by_id, current_results):
                    return False
                tool_calls = message.get("tool_calls") or []
                current_calls_by_id = {tc["id"]: tc for tc in tool_calls if "id" in tc}
                current_results = []
            elif role == "tool":
                current_results.append(message)
            elif role != "tool" and current_results:
                if not _validate_tool_result_exchange(current_calls_by_id, current_results):
                    return False
                current_calls_by_id = {}
                current_results = []

        if not _validate_tool_result_exchange(current_calls_by_id, current_results):
            return False

        return True
    except Exception:
        logger.exception("check_tool_result_linkage failed unexpectedly; blocking")
        return False
