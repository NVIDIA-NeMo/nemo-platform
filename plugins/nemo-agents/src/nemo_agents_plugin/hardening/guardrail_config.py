# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Build a managed NeMo Guardrails config (input rail) from behavioral remediations.

Phase 1 emits a single ``self check input`` rail whose prompt aggregates every
remediation's block instruction (see plan OQ1). Models are supplied per request
(via the check/VirtualModel main model), so no ``models`` entry is needed.
"""
from __future__ import annotations

from typing import Any

from nemo_agents_plugin.hardening.models import GuardrailRemediation

_PROMPT_HEADER = (
    "Your task is to check if the user message below violates any of the "
    "safety policies for this agent.\n\nPolicies (block the message if it matches any):"
)
_PROMPT_FOOTER = (
    '\n\nUser message: "{{ user_input }}"\n\n'
    "Question: Should the user message be blocked (Yes or No)?\nAnswer:"
)


def build_rails_config(remediations: list[GuardrailRemediation]) -> dict[str, Any]:
    """Return the ``data`` dict for a GuardrailConfig with one self-check input rail.

    Each remediation contributes one bullet to the self_check_input policy. With
    no remediations, returns a config with an empty policy list (the rail still
    parses and blocks nothing).
    """
    bullets = "\n".join(f"- {r.guardrail_prompt.strip()}" for r in remediations)
    content = f"{_PROMPT_HEADER}\n{bullets}{_PROMPT_FOOTER}"
    return {
        "rails": {"input": {"flows": ["self check input"]}},
        "prompts": [{"task": "self_check_input", "content": content}],
    }
