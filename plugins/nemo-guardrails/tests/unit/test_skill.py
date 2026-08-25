# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the API-first Guardrails skill."""

import json
import re

from nemo_guardrails_plugin.skills import get_skills_path


def test_guardrails_skill_is_api_first_and_generic() -> None:
    skill_dir = get_skills_path() / "guardrails-plugin"
    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    assert "## API workflow" in skill_text
    assert "/apis/guardrails/v2/workspaces/{workspace}/checks" in skill_text
    assert "/apis/inference-gateway/v2/workspaces/{workspace}/openai/-/v1/chat/completions" in skill_text
    assert '"status": "blocked"' in skill_text
    assert "never attach an unvalidated config to a VirtualModel" in skill_text
    assert "## CLI Quickstart" not in skill_text
    assert "nemo guardrail configs create" not in skill_text
    assert "demo-unguarded" not in skill_text
    assert "demo-guarded" not in skill_text
    assert "demo-no-fruit" not in skill_text
    assert "bananas" not in skill_text
    assert not re.search(r"\bdemo\b", skill_text, flags=re.IGNORECASE)

    json_blocks = re.findall(r"```json\n(.*?)\n```", skill_text, flags=re.DOTALL)
    assert json_blocks
    for block in json_blocks:
        json.loads(block)


def test_guardrails_skill_has_routing_tests() -> None:
    tests_path = get_skills_path() / "guardrails-plugin" / "tests.json"
    payload = json.loads(tests_path.read_text(encoding="utf-8"))

    assert payload["skill"] == "guardrails-plugin"
    assert any(test["type"] == "explicit" for test in payload["tests"])
    assert any(test["type"] == "implicit" for test in payload["tests"])
    assert any(test["type"] == "negative-control" for test in payload["tests"])
