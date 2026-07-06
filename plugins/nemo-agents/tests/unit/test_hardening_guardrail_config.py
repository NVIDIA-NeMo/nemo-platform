# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from nemo_agents_plugin.hardening.guardrail_config import build_rails_config
from nemo_agents_plugin.hardening.models import GuardrailRemediation


def _rem(prompt, fid="attack-0000"):
    return GuardrailRemediation(finding_id=fid, attack_prompt="a", victim_response="o", guardrail_prompt=prompt)


def test_build_rails_config_has_self_check_input_flow():
    """The config wires the self check input flow."""
    data = build_rails_config([_rem("Block cat of /etc/passwd")])
    assert data["rails"]["input"]["flows"] == ["self check input"]


def test_self_check_prompt_carries_user_input_placeholder_and_policy():
    """The prompt embeds {{ user_input }} and each remediation's instruction as a bullet."""
    data = build_rails_config([_rem("Block cat of /etc/passwd"), _rem("Block token exfiltration", "attack-0001")])
    content = data["prompts"][0]["content"]
    assert data["prompts"][0]["task"] == "self_check_input"
    assert "{{ user_input }}" in content
    assert "- Block cat of /etc/passwd" in content
    assert "- Block token exfiltration" in content
    assert content.rstrip().endswith("Answer:")


def test_empty_remediations_still_valid_config():
    """No remediations yields a valid config with an empty policy list."""
    data = build_rails_config([])
    assert data["rails"]["input"]["flows"] == ["self check input"]
    assert "{{ user_input }}" in data["prompts"][0]["content"]
