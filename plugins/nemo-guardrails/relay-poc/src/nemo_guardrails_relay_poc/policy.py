# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-agnostic guardrail policy for the NeMo Guardrails Relay PoC.

This module builds the callbacks a Relay plugin registers, but it never imports
the Relay worker SDK. That keeps the policy fully unit-testable on its own and
draws a clean line between *what to enforce* (here) and *where to enforce it*
(``worker.py``).

Three surfaces are demonstrated:

* **Deterministic tool policy** — hard-blocks a tool call at the real execution
  boundary using the same deterministic predicates the shipped IGW plugin uses
  (allowlist, blocklist, and per-argument keyword/length rules), vendored
  dependency-free in ``_predicates`` for the PoC. No model call.
* **Deterministic argument rewrite** — redacts PII in configured tool arguments
  before the tool runs (proves rewrite-and-continue, which IGW cannot do).
* **Model-backed LLM input rail** — calls the NeMo Guardrails ``/checks``
  service to judge the prompt (content-safety), the one place the library earns
  its cost. The PoC backs it with a mock check (no network).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from nemo_guardrails_relay_poc._predicates import (
    argument_violations,
    denied_command_violation,
    is_tool_allowed,
    is_tool_blocked,
)

logger = logging.getLogger(__name__)

Json = Any

DEFAULT_CHECKS_PATH = "/apis/guardrails/v2/workspaces/{workspace}/checks"

# Deliberately conservative PoC patterns. Production redaction should use the
# platform's Presidio-backed sensitive-data rail rather than regexes.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[REDACTED_EMAIL]", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("[REDACTED_SSN]", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("[REDACTED_PHONE]", re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")),
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolPolicy:
    """Deterministic tool policy parsed from plugin config."""

    #: When non-empty, only these tool names may run (allowlist).
    allowed_tools: list[str] = field(default_factory=list)
    #: Explicit deny; takes precedence over the allowlist.
    blocked_tools: list[str] = field(default_factory=list)
    #: tool_name -> arg_name -> {"blocked_keywords": [...], "max_length": int}
    argument_rules: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    #: tool_name -> list of argument names whose string values should be PII-redacted
    redact_args: dict[str, list[str]] = field(default_factory=dict)
    #: tool_name -> list of exact (normalized) command strings to block for that tool
    denied_commands: dict[str, list[str]] = field(default_factory=dict)
    #: argument name that carries the command string for command-denylist tools
    command_arg: str = "command"


@dataclass(slots=True)
class LlmInputRailConfig:
    """Model-backed LLM input rail settings parsed from plugin config."""

    enabled: bool = False
    base_url: str = "http://localhost:8080"
    workspace: str = "default"
    config_id: str = "system/content-safety"
    model: str = ""
    timeout_s: float = 10.0
    #: On a transport/service error, block (fail closed) to match IGW behavior.
    fail_closed: bool = True
    checks_path: str = DEFAULT_CHECKS_PATH


def parse_tool_policy(config: dict[str, Any]) -> ToolPolicy:
    raw = config.get("tool_policy") or {}
    allowed = raw.get("allowed_tools") or []
    blocked = raw.get("blocked_tools") or []
    arguments = raw.get("arguments") or {}
    redact = raw.get("redact_args") or {}
    denied = raw.get("denied_commands") or {}
    defaults = ToolPolicy()
    return ToolPolicy(
        allowed_tools=[str(name) for name in allowed],
        blocked_tools=[str(name) for name in blocked],
        argument_rules={
            str(tool): {str(arg): dict(rules) for arg, rules in (arg_rules or {}).items()}
            for tool, arg_rules in arguments.items()
        },
        redact_args={str(tool): [str(arg) for arg in args] for tool, args in redact.items()},
        denied_commands={str(tool): [str(cmd) for cmd in (cmds or [])] for tool, cmds in denied.items()},
        command_arg=str(raw.get("command_arg", defaults.command_arg)),
    )


def parse_llm_input_rail(config: dict[str, Any]) -> LlmInputRailConfig:
    raw = config.get("llm_input_rail") or {}
    defaults = LlmInputRailConfig()
    return LlmInputRailConfig(
        enabled=bool(raw.get("enabled", False)),
        base_url=str(raw.get("base_url", defaults.base_url)),
        workspace=str(raw.get("workspace", defaults.workspace)),
        config_id=str(raw.get("config_id", defaults.config_id)),
        model=str(raw.get("model", defaults.model)),
        timeout_s=float(raw.get("timeout_s", defaults.timeout_s)),
        fail_closed=bool(raw.get("fail_closed", defaults.fail_closed)),
        checks_path=str(raw.get("checks_path", defaults.checks_path)),
    )


# ---------------------------------------------------------------------------
# Surface 1: deterministic tool block (conditional execution guardrail)
# ---------------------------------------------------------------------------


def build_tool_policy_guardrail(policy: ToolPolicy) -> Callable[[str, Json], str | None]:
    """Return a Relay tool conditional-execution callback for deterministic policy.

    Returns ``None`` to allow the tool call or a human-readable string to block
    it. Three deterministic checks run in order, each using the same predicates
    the IGW plugin uses:

    1. **blocklist** -- an explicit deny (``blocked_tools``) that overrides the
       allowlist,
    2. **allowlist** -- when ``allowed_tools`` is non-empty, only those names run,
    3. **argument rules** -- per-tool ``blocked_keywords`` / ``max_length`` checks
       on the call's arguments,
    4. **command denylist** -- per-tool exact (normalized) command match against
       the ``command_arg`` argument, for shell/bash-style tools.

    The decision needs only the tool name and arguments, which is all Relay's
    tool guardrail hook provides today.
    """

    def guardrail(tool_name: str, args: Json) -> str | None:
        if is_tool_blocked(tool_name, policy.blocked_tools):
            return f"blocked: tool {tool_name!r} is on the blocklist {sorted(policy.blocked_tools)}"
        if not is_tool_allowed(tool_name, policy.allowed_tools):
            return f"blocked: tool {tool_name!r} is not on the allowlist {sorted(policy.allowed_tools)}"
        violations = argument_violations(args, policy.argument_rules.get(tool_name))
        if violations:
            return f"blocked: tool {tool_name!r} argument policy violated ({'; '.join(violations)})"
        command_violation = denied_command_violation(args, policy.command_arg, policy.denied_commands.get(tool_name))
        if command_violation:
            return f"blocked: tool {tool_name!r} {command_violation}"
        return None

    return guardrail


# ---------------------------------------------------------------------------
# Surface 2: deterministic argument rewrite (request intercept)
# ---------------------------------------------------------------------------


def redact_pii(text: str) -> str:
    """Redact obvious PII from a string. PoC-grade; not a substitute for Presidio."""
    for replacement, pattern in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def build_redact_args_intercept(policy: ToolPolicy) -> Callable[[str, Json], Json]:
    """Return a Relay tool request-intercept callback that redacts configured args.

    Only touches tools/arguments named in ``policy.redact_args``; everything else
    passes through unchanged.
    """

    def intercept(tool_name: str, args: Json) -> Json:
        arg_names = policy.redact_args.get(tool_name)
        if not arg_names or not isinstance(args, dict):
            return args
        updated = dict(args)
        for arg_name in arg_names:
            value = updated.get(arg_name)
            if isinstance(value, str):
                updated[arg_name] = redact_pii(value)
        return updated

    return intercept


# ---------------------------------------------------------------------------
# Surface 3: model-backed LLM input rail (calls the Guardrails service)
# ---------------------------------------------------------------------------


# Maps LangChain message ``type`` values to OpenAI-style ``role`` values.
_LANGCHAIN_TYPE_TO_ROLE = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}


def _coerce_content(value: Any) -> str:
    """Coerce a message ``content`` field (str, or list of blocks) to text."""
    return value if isinstance(value, str) else str(value)


def _normalize_message(message: Any) -> dict[str, Any]:
    """Normalize one message to OpenAI ``{"role", "content"}`` shape.

    Handles two inputs the same way:

    * OpenAI-style dicts (``{"role", "content"}``) pass through unchanged -- this
      is what the out-of-process worker receives from the gateway.
    * LangChain-serialized dicts (``{"type": "human", "data": {"content": ...}}``)
      are converted -- this is what the in-process middleware produces.
    """
    if not isinstance(message, dict):
        return {"role": getattr(message, "role", "") or "", "content": _coerce_content(getattr(message, "content", ""))}
    if "role" in message or "content" in message:
        return message
    data = message.get("data")
    if isinstance(data, dict):
        msg_type = message.get("type") or data.get("type") or ""
        return {
            "role": _LANGCHAIN_TYPE_TO_ROLE.get(msg_type, msg_type),
            "content": _coerce_content(data.get("content", "")),
        }
    return message


def _raw_messages(request: Json) -> list[Any]:
    """Pull the raw message list out of a request, before normalization."""
    if isinstance(request, dict):
        if isinstance(request.get("messages"), list):
            return request["messages"]
        for key in ("content", "body"):
            body = request.get(key)
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except (json.JSONDecodeError, ValueError):
                    continue
            if isinstance(body, dict) and isinstance(body.get("messages"), list):
                return body["messages"]
        return []

    # In-process path: the embedded runtime passes a typed request object, not a
    # JSON dict. ``LLMRequest`` exposes the JSON payload on ``.content`` (a dict
    # containing "messages"); some request types instead expose message objects
    # on ``.messages``. Handle both.
    payload = getattr(request, "content", None)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            payload = None
    if isinstance(payload, dict):
        raw = _raw_messages(payload)
        if raw:
            return raw

    messages = getattr(request, "messages", None)
    if isinstance(messages, list):
        return messages
    return []


def extract_messages(request: Json) -> list[dict[str, Any]]:
    """Best-effort extraction of OpenAI-style messages from a Relay LLM request.

    A Relay LLM request carries the provider body in a few possible shapes. We
    check, in order: a top-level ``messages``; a ``content``/``body`` field that
    is a dict or JSON string; and, for the in-process typed ``LLMRequest``, the
    payload on ``.content`` or message objects on ``.messages``. Every message is
    normalized to OpenAI ``{"role", "content"}`` shape (see ``_normalize_message``),
    so both the gateway (OpenAI-style) and the LangChain middleware
    (LangChain-serialized) feed the rail the same shape. Returns ``[]`` when
    nothing matches.
    """
    return [_normalize_message(message) for message in _raw_messages(request)]


class GuardrailsServiceClient:
    """Thin async client for the NeMo Guardrails ``/checks`` endpoint."""

    def __init__(self, cfg: LlmInputRailConfig, *, token: str | None = None) -> None:
        self._cfg = cfg
        self._token = token

    @property
    def url(self) -> str:
        return self._cfg.base_url.rstrip("/") + self._cfg.checks_path.format(workspace=self._cfg.workspace)

    async def check(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """POST messages to the checks endpoint and return the parsed response."""
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": messages,
            "guardrails": {"config_id": self._cfg.config_id},
        }
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        async with httpx.AsyncClient(timeout=self._cfg.timeout_s) as client:
            resp = await client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()


def _blocked_rail_names(check_response: dict[str, Any]) -> list[str]:
    rails_status = check_response.get("rails_status") or {}
    return [name for name, status in rails_status.items() if (status or {}).get("status") == "blocked"]


def _error_verdict(cfg: LlmInputRailConfig) -> str | None:
    """Verdict when the check backend errors: block if configured to fail closed."""
    if cfg.fail_closed:
        return "blocked: guardrails service unavailable (failing closed)"
    return None


def _response_verdict(response: dict[str, Any]) -> str | None:
    """Map a ``/checks``-shaped response to a block reason (or ``None`` to allow)."""
    if response.get("status") == "blocked":
        rails = _blocked_rail_names(response)
        detail = f" ({', '.join(rails)})" if rails else ""
        return f"blocked: input rail{detail}"
    return None


CheckFn = Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]]


def build_llm_input_rail(
    cfg: LlmInputRailConfig,
    check_fn: CheckFn,
) -> Callable[[Json], Awaitable[str | None]]:
    """Return a Relay LLM conditional-execution callback backed by the Guardrails service.

    ``check_fn`` is injected (normally :meth:`GuardrailsServiceClient.check`) so
    the rail can be unit-tested without a live service.
    """

    async def rail(request: Json) -> str | None:
        messages = extract_messages(request)
        if not messages:
            logger.debug("llm_input_rail: no messages found in request; allowing")
            return None
        try:
            response = await check_fn(messages)
        except Exception as exc:  # noqa: BLE001 - guardrail must decide, not raise
            logger.warning("llm_input_rail: guardrails check failed: %s", exc)
            return _error_verdict(cfg)
        return _response_verdict(response)

    return rail


# ---------------------------------------------------------------------------
# In-process variant + mock content-safety check
# ---------------------------------------------------------------------------
#
# The embedded (in-process) runtime invokes conditional-execution guardrails as
# plain *synchronous* callables inside its own event loop, and hands them a
# typed ``LLMRequest`` object rather than JSON. The sync rail below mirrors the
# async one exactly, but takes a synchronous check so it never ``await``s. For
# now the demo injects ``mock_content_safety_check`` (no network); swapping in a
# real synchronous client, or moving to the async rail against a running
# service, is a drop-in change because the response shape is identical.


SyncCheckFn = Callable[[list[dict[str, Any]]], dict[str, Any]]


def build_llm_input_rail_sync(
    cfg: LlmInputRailConfig,
    check_fn: SyncCheckFn,
) -> Callable[[Json], str | None]:
    """Return a synchronous LLM conditional-execution callback for the embedded runtime."""

    def rail(request: Json) -> str | None:
        messages = extract_messages(request)
        if not messages:
            logger.debug("llm_input_rail: no messages found in request; allowing")
            return None
        try:
            response = check_fn(messages)
        except Exception as exc:  # noqa: BLE001 - guardrail must decide, not raise
            logger.warning("llm_input_rail: check failed: %s", exc)
            return _error_verdict(cfg)
        return _response_verdict(response)

    return rail


#: PoC stand-in "unsafe" phrases. A real deployment sends the prompt to a
#: content-safety model via the Guardrails service; this list exists only so the
#: demo can block deterministically with no network call.
DEFAULT_UNSAFE_TERMS: tuple[str, ...] = ("bomb", "weapon", "explosive")


def mock_content_safety_check(
    messages: list[dict[str, Any]],
    *,
    unsafe_terms: tuple[str, ...] = DEFAULT_UNSAFE_TERMS,
) -> dict[str, Any]:
    """Mock the Guardrails ``/checks`` content-safety verdict without a network call.

    Returns the same response shape the real service returns, so replacing this
    with :meth:`GuardrailsServiceClient.check` later requires no other changes.
    """
    joined = " ".join(str(message.get("content", "")) for message in messages).lower()
    if any(term in joined for term in unsafe_terms):
        return {"status": "blocked", "rails_status": {"content safety check input": {"status": "blocked"}}}
    return {"status": "success", "rails_status": {}}
