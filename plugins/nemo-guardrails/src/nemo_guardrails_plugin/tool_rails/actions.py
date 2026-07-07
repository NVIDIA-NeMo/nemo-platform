# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in tool rail actions for the NeMo Guardrails plugin.

Each action is registered via import_paths so the nemoguardrails library
discovers them at LLMRails build time. Policy is read from
config.custom_data so users can configure it per GuardrailConfig without
writing custom Colang.
"""

import json
import logging

from nemoguardrails.actions import action
from nemoguardrails.rails.llm.config import RailsConfig

logger = logging.getLogger(__name__)


def _context_data(context: dict | None) -> dict:
    return context or {}


def _custom_data(config: RailsConfig | None) -> dict:
    return (config.custom_data if config else None) or {}


def _tool_calls(context: dict | None) -> list[dict]:
    return _context_data(context).get("tool_calls") or []


def _tool_name(tool_call: dict) -> str:
    return tool_call.get("function", {}).get("name", "")


def _parse_tool_arguments(tool_call: dict, *, action_name: str) -> dict | None:
    """Return OpenAI tool-call arguments as a dict, or None when invalid.

    Tool-call arguments can arrive as either an already-decoded object or a JSON
    string. The tool rails only support object arguments, so malformed JSON,
    arrays, scalars, and other shapes fail closed.
    """
    raw_args = tool_call.get("function", {}).get("arguments") or {}
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


def _tool_schema_by_name(declared_tools: list[dict]) -> dict[str, dict]:
    return {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in declared_tools
        if tool.get("function", {}).get("name") and tool.get("function", {}).get("parameters")
    }


def _validate_tool_result_exchange(prior_calls_by_id: dict[str, dict], tool_results: list[dict]) -> bool:
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
    context: dict | None = None,
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
        context_data = _context_data(context)
        tool_calls = _tool_calls(context)
        custom_data = _custom_data(config)
        allowed_tools = custom_data.get("tool_allowlist", {}).get("allowed_tools") or []

        if not allowed_tools:
            return True

        # tool_output context: tool_calls list set by process_bot_tool_call flow
        if tool_calls:
            tool_names = [_tool_name(tc) for tc in tool_calls]
            result = all(name in allowed_tools for name in tool_names)
            logger.debug(
                "check_tool_allowlist: tool_names=%s allowed_tools=%s result=%s",
                tool_names,
                allowed_tools,
                result,
            )
            return result
        # tool_input context: process_user_tool_messages sets $tool_name per iteration
        tool_name = context_data.get("tool_name")
        if tool_name is not None:
            result = tool_name in allowed_tools
            logger.debug(
                "check_tool_allowlist: tool_name=%s allowed_tools=%s result=%s",
                tool_name,
                allowed_tools,
                result,
            )
            return result
        return True
    except Exception:
        logger.exception("check_tool_allowlist failed unexpectedly; blocking")
        return False


@action(is_system_action=True)
async def check_tool_arguments(
    context: dict | None = None,
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
                value = str(args.get(arg_name, ""))
                blocked = [kw.upper() for kw in (arg_rules.get("blocked_keywords") or [])]
                if any(kw in value.upper() for kw in blocked):
                    logger.debug(
                        "check_tool_arguments: blocking tool=%s argument=%s value=%r blocked_keywords=%s",
                        name,
                        arg_name,
                        value,
                        arg_rules.get("blocked_keywords") or [],
                    )
                    return False
                max_length = arg_rules.get("max_length")
                if max_length is not None and len(value) > max_length:
                    logger.debug(
                        "check_tool_arguments: blocking tool=%s argument=%s value_length=%s max_length=%s",
                        name,
                        arg_name,
                        len(value),
                        max_length,
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
    context: dict | None = None,
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
        import jsonschema

        context_data = _context_data(context)
        tool_calls = _tool_calls(context)
        declared_tools = context_data.get("declared_tools") or []

        if not tool_calls:
            return True
        if not declared_tools:
            logger.warning("check_tool_schema: tool calls present but request declared no tools; blocking")
            return False

        schema_by_name = _tool_schema_by_name(declared_tools)

        for tc in tool_calls:
            name = _tool_name(tc)
            schema = schema_by_name.get(name)
            if not schema:
                logger.warning("check_tool_schema: no declared schema for tool %r; blocking", name)
                return False

            args = _parse_tool_arguments(tc, action_name="check_tool_schema")
            if args is None:
                return False

            try:
                jsonschema.validate(instance=args, schema=schema)
            except jsonschema.ValidationError as exc:
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
    context: dict | None = None,
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

        current_calls_by_id: dict[str, dict] = {}
        current_results: list[dict] = []
        saw_tool_result = False

        for message in messages:
            role = message.get("role")
            if role == "assistant":
                if not _validate_tool_result_exchange(current_calls_by_id, current_results):
                    return False
                tool_calls = message.get("tool_calls") or []
                current_calls_by_id = {tc["id"]: tc for tc in tool_calls if "id" in tc}
                current_results = []
            elif role == "tool":
                saw_tool_result = True
                current_results.append(message)
            elif role != "tool" and current_results:
                if not _validate_tool_result_exchange(current_calls_by_id, current_results):
                    return False
                current_calls_by_id = {}
                current_results = []

        if not _validate_tool_result_exchange(current_calls_by_id, current_results):
            return False

        if not saw_tool_result:
            return True

        return True
    except Exception:
        logger.exception("check_tool_result_linkage failed unexpectedly; blocking")
        return False
