# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""In-process **language-binding plugin** form of the guardrails policy.

This is the in-process twin of ``worker.py``. Both are thin adapters over the
same host-agnostic ``policy.py``, but they are two different Relay plugin *types*:

* ``worker.py`` is a **gRPC Worker Plugin (Python)** -- an out-of-process worker
  the CLI loads via ``relay-plugin.toml`` / ``nemo-relay plugins add``. The
  gateway that loads it only drives LLM calls through managed execution, so it
  covers the LLM boundary.
* ``GuardrailsPlugin`` here is a **Language Binding Plugin (Python)** -- an
  in-process plugin the application registers directly with the embedded
  ``nemo_relay`` runtime (``nemo_relay.plugin.register`` + ``initialize``). Because
  it runs in the agent's own process, its guardrails fire on both the model call
  *and* the tool calls that ``NemoRelayMiddleware`` routes through managed
  execution -- i.e. every surface we've built.

Activation (what a consuming agent does):

    import nemo_relay
    from nemo_guardrails_relay_poc.inprocess import PLUGIN_KIND, GuardrailsPlugin

    nemo_relay.plugin.register(PLUGIN_KIND, GuardrailsPlugin())
    await nemo_relay.plugin.initialize(
        nemo_relay.plugin.PluginConfig(
            components=[nemo_relay.plugin.ComponentSpec(kind=PLUGIN_KIND, config={...})],
        )
    )
    # ... run the agent with NemoRelayMiddleware ...
    nemo_relay.plugin.clear()

Importing this module requires the ``nemo-relay`` package (the embedded runtime).
The worker never imports it, so the Relay-managed worker venv stays lightweight.
"""

from __future__ import annotations

from typing import Any

import nemo_relay
from nemo_guardrails_relay_poc.policy import (
    build_llm_input_rail_sync,
    build_redact_args_intercept,
    build_tool_policy_guardrail,
    mock_content_safety_check,
    parse_llm_input_rail,
    parse_tool_policy,
)

#: Stable plugin ``kind``. Operators match config components to this string.
PLUGIN_KIND = "nemo_guardrails.relay_poc"


class GuardrailsPlugin:
    """Language-binding plugin that enforces the guardrails policy in-process.

    Implements the ``nemo_relay.plugin.Plugin`` protocol (``validate`` +
    ``register``). ``register`` installs up to three runtime surfaces through the
    component-scoped ``PluginContext``:

    * a tool conditional-execution guardrail (allowlist / blocklist / argument
      keyword+length hard-block),
    * a tool request intercept (argument PII redaction), when configured, and
    * an LLM conditional-execution guardrail (model-based input rail), when enabled.

    The input rail uses a mock content-safety check (no network) for the PoC;
    swap in the real Guardrails service client without touching this class.
    """

    def validate(self, plugin_config: Any) -> list[dict[str, str]]:
        diagnostics: list[dict[str, str]] = []
        if not isinstance(plugin_config, dict):
            return [
                {
                    "level": "error",
                    "code": f"{PLUGIN_KIND}.invalid_config",
                    "component": PLUGIN_KIND,
                    "message": "plugin config must be a JSON object",
                }
            ]

        tool_policy = plugin_config.get("tool_policy")
        if tool_policy is not None and not isinstance(tool_policy, dict):
            diagnostics.append(
                {
                    "level": "error",
                    "code": f"{PLUGIN_KIND}.invalid_tool_policy",
                    "component": PLUGIN_KIND,
                    "field": "tool_policy",
                    "message": "tool_policy must be a JSON object",
                }
            )
        elif isinstance(tool_policy, dict):
            denied_commands = tool_policy.get("denied_commands")
            if denied_commands is not None and not isinstance(denied_commands, dict):
                diagnostics.append(
                    {
                        "level": "error",
                        "code": f"{PLUGIN_KIND}.invalid_denied_commands",
                        "component": PLUGIN_KIND,
                        "field": "tool_policy.denied_commands",
                        "message": "tool_policy.denied_commands must be a JSON object (tool_name -> [commands])",
                    }
                )

        rail = plugin_config.get("llm_input_rail")
        if rail is not None:
            if not isinstance(rail, dict):
                diagnostics.append(
                    {
                        "level": "error",
                        "code": f"{PLUGIN_KIND}.invalid_llm_input_rail",
                        "component": PLUGIN_KIND,
                        "field": "llm_input_rail",
                        "message": "llm_input_rail must be a JSON object",
                    }
                )
            elif rail.get("enabled") and not rail.get("model"):
                diagnostics.append(
                    {
                        "level": "error",
                        "code": f"{PLUGIN_KIND}.missing_model",
                        "component": PLUGIN_KIND,
                        "field": "llm_input_rail.model",
                        "message": "llm_input_rail.model is required when the rail is enabled",
                    }
                )
        return diagnostics

    def register(self, plugin_config: Any, context: nemo_relay.plugin.PluginContext) -> None:
        if not isinstance(plugin_config, dict):
            raise TypeError("plugin config must be a JSON object")

        tool_policy = parse_tool_policy(plugin_config)
        rail_cfg = parse_llm_input_rail(plugin_config)

        # Surface 1: deterministic hard-block at the tool execution boundary
        # (allowlist + blocklist + per-argument keyword/length rules).
        context.register_tool_conditional_execution_guardrail(
            "tool_policy",
            0,
            build_tool_policy_guardrail(tool_policy),
        )

        # Surface 2: deterministic argument rewrite before the tool runs.
        if tool_policy.redact_args:
            context.register_tool_request_intercept(
                "redact_tool_args",
                0,
                False,
                build_redact_args_intercept(tool_policy),
            )

        # Surface 3: model-based LLM input rail. PoC uses a mock check (no network);
        # the real path swaps in GuardrailsServiceClient.check via the async rail.
        if rail_cfg.enabled:
            context.register_llm_conditional_execution_guardrail(
                "content_safety_input",
                0,
                build_llm_input_rail_sync(rail_cfg, mock_content_safety_check),
            )
