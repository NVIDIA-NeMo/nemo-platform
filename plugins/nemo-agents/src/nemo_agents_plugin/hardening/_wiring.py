# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Builders for the pieces of the hardening loop that touch live platform systems.

Isolated here so the loop and stages stay pure and testable. Verified call chains:
- inference: ``platform.models.get_openai_client()`` returns an OpenAI client
  pointed at the inference gateway (there is no first-party chat-completions
  method); ``models/resources.py:83``.
- guardrail apply: ``platform.guardrail.configs.create/update`` (a config is
  create-once then update-in-place across rounds).
- guardrail check: ``platform.guardrail.check(messages=, model=, guardrails=)``
  returns a response whose ``status`` is ``blocked`` / ``success`` / ``unknown``.
"""
from __future__ import annotations

from typing import Any, Callable


def build_completion_fn(platform: Any, *, model: str) -> Callable[[str, str], str]:
    """Return ``complete(system, user) -> str`` backed by the inference gateway."""
    client = platform.models.get_openai_client()

    def complete(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    return complete


def build_apply_config(platform: Any, *, workspace: str, name: str) -> Callable[[dict], None]:
    """Return ``apply_config(data)`` that creates the managed config once, then updates it.

    Rounds accumulate rules, so the config is created on the first apply and
    updated in place afterward (the check endpoint reads it by ``workspace/name``).
    """
    state = {"created": False}

    def apply_config(data: dict) -> None:
        if not state["created"]:
            platform.guardrail.configs.create(workspace=workspace, name=name, data=data, exist_ok=True)
            state["created"] = True
        platform.guardrail.configs.update(name, workspace=workspace, data=data)

    return apply_config


def _status_str(response: Any) -> str:
    status = getattr(response, "status", "")
    value = getattr(status, "value", status)
    return str(value).lower()


def build_check(platform: Any, *, workspace: str, config_name: str, model: str) -> Callable[[str], str]:
    """Return ``check(user_message) -> status`` that runs the managed config's rails.

    Status is normalized to ``blocked`` / ``success`` / ``unknown``. Verification
    runs in isolation against the config; no agent process is involved.
    """
    config_ref = f"{workspace}/{config_name}"

    def check(user_message: str) -> str:
        response = platform.guardrail.check(
            messages=[{"role": "user", "content": user_message}],
            model=model,
            guardrails={"config_ids": [config_ref]},
        )
        return _status_str(response)

    return check
