# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local, dependency-free tool-policy predicates for the Relay PoC.

The allowlist predicates (``is_tool_allowed`` / ``disallowed_tool_names``) are a
byte-for-byte copy of ``nemo_guardrails_plugin.tool_rails.predicates`` from the
shipped IGW plugin. The remaining predicates (``is_tool_blocked`` /
``argument_violations``) mirror the deterministic argument logic that lives in
the IGW plugin's ``tool_rails/actions.py`` -- but that code is coupled to
``nemoguardrails`` (``@action`` + ``RailsConfig``), so it is re-expressed here as
pure functions.

Everything is vendored so the PoC installs with no ``nemoguardrails`` /
``nemo-platform`` dependency, and so this branch can ship as a self-contained
demo PR that does not depend on the (unmerged) IGW tool-rails work. The proper
follow-up is to promote all of these into one small, standalone, dependency-free
package that BOTH the IGW plugin and this Relay plugin import, restoring a single
tested source of truth.
"""

import json
from collections.abc import Iterable
from typing import Any


def is_tool_allowed(tool_name: str, allowed_tools: Iterable[str] | None) -> bool:
    """Return whether a tool name is permitted.

    An absent or empty allowlist permits every tool, matching the IGW
    ``check_tool_allowlist`` action.
    """
    allowed = list(allowed_tools or [])
    if not allowed:
        return True
    return tool_name in allowed


def disallowed_tool_names(tool_names: Iterable[str], allowed_tools: Iterable[str] | None) -> list[str]:
    """Return the subset of ``tool_names`` that the allowlist rejects.

    Empty when the allowlist is absent/empty (everything allowed) or when all
    names are permitted.
    """
    allowed = list(allowed_tools or [])
    if not allowed:
        return []
    return [name for name in tool_names if name not in allowed]


def is_tool_blocked(tool_name: str, blocked_tools: Iterable[str] | None) -> bool:
    """Return whether a tool name is explicitly denied.

    A blocklist is an explicit deny: it takes precedence over the allowlist, so a
    tool that appears on both is blocked. An absent or empty blocklist denies
    nothing.
    """
    return tool_name in set(blocked_tools or [])


def _as_object(args: Any) -> dict[str, Any] | None:
    """Coerce tool-call arguments to a dict, or ``None`` when they are not an object.

    Arguments arrive either already decoded or as a JSON string. Only object
    arguments are supported; malformed JSON, arrays, and scalars return ``None``
    so the caller can fail closed -- matching the IGW ``_parse_tool_arguments``.
    """
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return args if isinstance(args, dict) else None


def argument_violations(args: Any, tool_rules: dict[str, dict[str, Any]] | None) -> list[str]:
    """Return human-readable reasons a tool call's arguments violate its rules.

    ``tool_rules`` maps an argument name to a rule dict with optional
    ``blocked_keywords`` (case-insensitive substring match) and ``max_length``
    (maximum character length of the argument's string value). Mirrors the IGW
    ``check_tool_arguments`` action. Returns ``[]`` when the arguments pass.

    Fails closed: when rules exist but the arguments are not a JSON object, a
    single violation is returned rather than silently allowing the call.
    """
    if not tool_rules:
        return []

    parsed = _as_object(args)
    if parsed is None:
        return ["arguments are not a JSON object"]

    violations: list[str] = []
    for arg_name, arg_rules in tool_rules.items():
        value = str(parsed.get(arg_name, ""))
        blocked = [keyword.upper() for keyword in (arg_rules.get("blocked_keywords") or [])]
        hit = next((keyword for keyword in blocked if keyword in value.upper()), None)
        if hit is not None:
            violations.append(f"argument {arg_name!r} contains blocked keyword {hit!r}")
        max_length = arg_rules.get("max_length")
        if max_length is not None and len(value) > max_length:
            violations.append(f"argument {arg_name!r} exceeds max_length {max_length}")
    return violations


def normalize_command(command: str) -> str:
    """Normalize a shell command string for exact-match comparison.

    Deterministic, intentionally minimal normalization -- this is not a shell
    parser. It only collapses insignificant whitespace and strips a leading
    ``./`` from each token so that ``touch  ./foo.txt`` and ``touch foo.txt``
    compare equal. It does *not* interpret quoting, env vars, globbing, or
    command chaining; a production matcher would need a real parse.
    """
    tokens = []
    for token in command.strip().split():
        if token.startswith("./") and len(token) > 2:
            token = token[2:]
        tokens.append(token)
    return " ".join(tokens)


def is_command_denied(command: str, denied_commands: Iterable[str] | None) -> bool:
    """Return whether a command matches any entry in the denylist.

    Both the candidate command and each denylist entry are passed through
    :func:`normalize_command`, so the match is on the *normalized equivalent*
    rather than a raw substring. ``touch foo.txt`` matches ``touch  ./foo.txt``
    but not ``touch foo.txt.bak`` (exactness, no over-matching). An absent or
    empty denylist denies nothing.
    """
    denied = {normalize_command(entry) for entry in (denied_commands or [])}
    return bool(denied) and normalize_command(command) in denied


def denied_command_violation(
    args: Any,
    command_arg: str,
    denied_commands: Iterable[str] | None,
) -> str | None:
    """Return a reason a tool call's command is denied, or ``None`` to allow.

    Reads the command string from the ``command_arg`` argument and matches it
    (normalized) against ``denied_commands``. Fails closed like
    :func:`argument_violations`: when a denylist exists but the arguments are not
    a JSON object, the call is blocked rather than silently allowed.
    """
    denied = list(denied_commands or [])
    if not denied:
        return None
    parsed = _as_object(args)
    if parsed is None:
        return "arguments are not a JSON object"
    command = str(parsed.get(command_arg, ""))
    if is_command_denied(command, denied):
        return f"command {command!r} is denied"
    return None
