# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Guardrails Relay PoC worker plugin.

Thin ``WorkerPlugin`` that wires the host-agnostic policy in ``policy.py`` onto
Relay's ``PluginContext``. All guardrail logic lives in ``policy.py`` so it can
be unit-tested without the Relay worker SDK; this file only handles config
validation and registration.

Run it via ``relay-plugin.toml`` (see the README). It expects the standard
worker environment variables set by the Relay host.
"""

from __future__ import annotations

import os
from typing import Any

from nemo_guardrails_relay_poc.policy import (
    GuardrailsServiceClient,
    build_llm_input_rail,
    build_redact_args_intercept,
    build_tool_allowlist_guardrail,
    parse_llm_input_rail,
    parse_tool_policy,
)
from nemo_relay_plugin import (
    ConfigDiagnostic,
    DiagnosticLevel,
    Json,
    PluginContext,
    WorkerPlugin,
    serve_plugin,
)

PLUGIN_ID = "nemo_guardrails.relay_poc"


class NemoGuardrailsRelayPoc(WorkerPlugin):
    """Enforce NeMo Guardrails policy inside the Relay execution loop."""

    plugin_id = PLUGIN_ID

    def validate(self, config: Json) -> list[ConfigDiagnostic | dict[str, Any]]:
        diagnostics: list[ConfigDiagnostic | dict[str, Any]] = []
        if not isinstance(config, dict):
            return [
                ConfigDiagnostic(
                    level=DiagnosticLevel.ERROR,
                    code=f"{PLUGIN_ID}.invalid_config",
                    component=PLUGIN_ID,
                    message="plugin config must be a JSON object",
                )
            ]

        tool_policy = config.get("tool_policy")
        if tool_policy is not None and not isinstance(tool_policy, dict):
            diagnostics.append(
                ConfigDiagnostic(
                    level=DiagnosticLevel.ERROR,
                    code=f"{PLUGIN_ID}.invalid_tool_policy",
                    component=PLUGIN_ID,
                    field="tool_policy",
                    message="tool_policy must be a JSON object",
                )
            )

        rail = config.get("llm_input_rail")
        if rail is not None:
            if not isinstance(rail, dict):
                diagnostics.append(
                    ConfigDiagnostic(
                        level=DiagnosticLevel.ERROR,
                        code=f"{PLUGIN_ID}.invalid_llm_input_rail",
                        component=PLUGIN_ID,
                        field="llm_input_rail",
                        message="llm_input_rail must be a JSON object",
                    )
                )
            elif rail.get("enabled") and not rail.get("model"):
                diagnostics.append(
                    ConfigDiagnostic(
                        level=DiagnosticLevel.ERROR,
                        code=f"{PLUGIN_ID}.missing_model",
                        component=PLUGIN_ID,
                        field="llm_input_rail.model",
                        message="llm_input_rail.model is required when the rail is enabled",
                    )
                )
        return diagnostics

    def register(self, ctx: PluginContext, config: Json) -> None:
        if not isinstance(config, dict):
            raise TypeError("plugin config must be a JSON object")

        tool_policy = parse_tool_policy(config)
        rail_cfg = parse_llm_input_rail(config)

        # Surface 1: deterministic hard-block at the tool execution boundary.
        ctx.register_tool_conditional_execution_guardrail(
            "tool_allowlist",
            build_tool_allowlist_guardrail(tool_policy),
        )

        # Surface 2: deterministic argument rewrite before the tool runs.
        if tool_policy.redact_args:
            ctx.register_tool_request_intercept(
                "redact_tool_args",
                build_redact_args_intercept(tool_policy),
            )

        # Surface 3: model-backed LLM input rail via the Guardrails service.
        if rail_cfg.enabled:
            token = os.environ.get("NMP_TOKEN")
            client = GuardrailsServiceClient(rail_cfg, token=token)
            ctx.register_llm_conditional_execution_guardrail(
                "content_safety_input",
                build_llm_input_rail(rail_cfg, client.check),
            )


async def main() -> None:
    """Entrypoint referenced by relay-plugin.toml."""
    await serve_plugin(NemoGuardrailsRelayPoc())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
