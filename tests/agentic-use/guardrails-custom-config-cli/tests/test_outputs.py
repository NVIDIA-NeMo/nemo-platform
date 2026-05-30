# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Verify that the agent created a custom guardrail configuration with keyword-based
input and output rails using a real LLM for content evaluation.

Checks:
- harbor-custom-config exists with correct description
- Config has both input and output rails configured
- Config uses the guardrails-llm model
- Config has prompts for self_check_input (fruit blocking) and self_check_output (bread blocking)
- Input rail blocks messages mentioning fruit
- Normal messages pass through both rails
- Output rail blocks responses about baking bread
- Agent performed the expected CRUD and inference operations
"""

import base64
import json
import os

import pytest
from nemo_platform import NeMoPlatform
from trace_reader import get_session

WORKSPACE = "default"
CONFIG_NAME = "harbor-custom-config"
CONFIG_ID = f"{WORKSPACE}/{CONFIG_NAME}"
MODEL = "default/guardrails-llm"


def _make_unsigned_jwt() -> str:
    """Create an unsigned JWT (alg=none) for local quickstart auth."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "verifier@harbor.local", "email": "verifier@harbor.local"}).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}."


@pytest.fixture
def client() -> NeMoPlatform:
    nmp_base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
    return NeMoPlatform(base_url=nmp_base_url, workspace=WORKSPACE, access_token=_make_unsigned_jwt())


@pytest.fixture
def config(client: NeMoPlatform):
    """Retrieve the agent-created guardrail config."""
    return client.guardrail.configs.retrieve(name=CONFIG_NAME)


# --- Config structure checks ---


def test_config_exists(config) -> None:
    """Test that harbor-custom-config was created."""
    assert config.name == CONFIG_NAME, f"Expected config name '{CONFIG_NAME}', got '{config.name}'"
    print(f"Config exists: {config.name}")


def test_config_description_updated(config) -> None:
    """Test that the config description was updated."""
    assert config.description == "Updated custom guardrail config", (
        f"Expected description 'Updated custom guardrail config', got '{config.description}'"
    )


def test_config_has_input_rails(config) -> None:
    """Test that the config has input rails configured."""
    data = config.data
    assert data is not None, "Config data should not be None"
    rails = data.rails
    input_rails = rails.input if rails else None
    input_flows = input_rails.flows if input_rails else []
    assert any("self check input" in f for f in input_flows), (
        f"Expected 'self check input' in input rail flows, got {input_flows}"
    )
    print(f"Input rails configured: {input_flows}")


def test_config_has_output_rails(config) -> None:
    """Test that the config has output rails configured."""
    data = config.data
    assert data is not None, "Config data should not be None"
    rails = data.rails
    output_rails = rails.output if rails else None
    output_flows = output_rails.flows if output_rails else []
    assert any("self check output" in f for f in output_flows), (
        f"Expected 'self check output' in output rail flows, got {output_flows}"
    )
    print(f"Output rails configured: {output_flows}")


def test_config_uses_guardrails_model(config) -> None:
    """Test that the config uses the guardrails-llm model."""
    data = config.data
    assert data is not None, "Config data should not be None"
    models = data.models or []
    model_names = [getattr(m, "model", "") for m in models]
    assert any("guardrails-llm" in name for name in model_names), (
        f"Expected a model containing 'guardrails-llm', got {model_names}"
    )
    print(f"Models configured: {model_names}")


def test_config_has_input_prompt_about_fruit(config) -> None:
    """Test that the self_check_input prompt checks for fruit mentions."""
    data = config.data
    assert data is not None, "Config data should not be None"
    prompts = data.prompts or []
    input_prompts = [p for p in prompts if "self_check_input" in getattr(p, "task", "")]
    assert len(input_prompts) > 0, (
        f"Expected a prompt with task 'self_check_input', got tasks: {[getattr(p, 'task', None) for p in prompts]}"
    )
    content = (getattr(input_prompts[0], "content", "") or "").lower()
    assert "fruit" in content, f"Expected self_check_input prompt to mention 'fruit', got: {content[:200]}"


def test_config_has_output_prompt_about_bread(config) -> None:
    """Test that the self_check_output prompt checks for bread baking content."""
    data = config.data
    assert data is not None, "Config data should not be None"
    prompts = data.prompts or []
    output_prompts = [p for p in prompts if "self_check_output" in getattr(p, "task", "")]
    assert len(output_prompts) > 0, (
        f"Expected a prompt with task 'self_check_output', got tasks: {[getattr(p, 'task', None) for p in prompts]}"
    )
    content = (getattr(output_prompts[0], "content", "") or "").lower()
    assert "bread" in content or "baking" in content, (
        f"Expected self_check_output prompt to mention 'bread' or 'baking', got: {content[:200]}"
    )


# --- Functional inference checks ---


def test_input_rail_blocks_fruit_mention(client: NeMoPlatform) -> None:
    """Test that a message mentioning fruit is blocked by the input rail.

    The self_check_input prompt tells the LLM to block messages mentioning fruit.
    A message about apples should trigger a 'Yes' response from the self-check,
    causing guardrails to mark the request blocked.
    """
    response = client.guardrail.check(
        model=MODEL,
        messages=[{"role": "user", "content": "Tell me about the health benefits of apples"}],
        guardrails={"config_id": CONFIG_ID},
        max_tokens=256,
        temperature=0,
    )
    assert response.status == "blocked", f"Message mentioning fruit should be blocked, got: {response.status}"
    print(f"Input rail correctly blocked fruit mention: {response.status}")


def test_normal_message_passes_through(client: NeMoPlatform) -> None:
    """Test that a normal message (no fruit, no bread) passes through both rails.

    A geography question doesn't mention fruit (passes input rail) and the response
    won't be about bread baking (passes output rail).
    """
    response = client.guardrail.check(
        model=MODEL,
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        guardrails={"config_id": CONFIG_ID},
        max_tokens=256,
        temperature=0,
    )
    assert response.status == "success", f"Normal message should NOT be blocked, got: {response.status}"
    print(f"Normal message passed through: {response.status}")


def test_output_rail_blocks_bread_content(client: NeMoPlatform) -> None:
    """Test that a response about baking bread is blocked by the output rail.

    The message doesn't mention fruit (passes input rail), but asking about bread
    baking will elicit a response about baking bread, which the output self-check
    should mark as blocked.
    """
    response = client.guardrail.check(
        model=MODEL,
        messages=[{"role": "user", "content": "Give me a step-by-step guide for baking sourdough bread"}],
        guardrails={"config_id": CONFIG_ID},
        max_tokens=256,
        temperature=0,
    )
    assert response.status == "blocked", f"Response about baking bread should be blocked, got: {response.status}"
    print(f"Output rail correctly blocked bread content: {response.status}")


# --- Trajectory check ---


def test_agent_performed_operations() -> None:
    """Verify the agent performed the expected CRUD and inference operations via trajectory."""
    session = get_session()
    commands = session.get_bash_commands()

    def has_command(*patterns: str) -> bool:
        return any(all(p in cmd for p in patterns) for cmd in commands)

    # Agent should have set up the inference provider
    assert has_command("secrets", "create", "nvidia-api-key") or has_command("secret", "create", "nvidia-api-key"), (
        f"Agent did not create the nvidia-api-key secret. Commands: {commands}"
    )

    # Agent should have listed or inspected existing configs
    assert has_command("guardrail", "configs"), f"Agent did not interact with guardrail configs. Commands: {commands}"

    # Agent should have created the custom config
    assert has_command("guardrail", "configs", "create", "harbor-custom-config"), (
        f"Agent did not create 'harbor-custom-config'. Commands: {commands}"
    )

    # Agent should have retrieved the config
    assert has_command("guardrail", "configs", "get", "harbor-custom-config"), (
        f"Agent did not retrieve 'harbor-custom-config'. Commands: {commands}"
    )

    # Agent should have updated the config
    assert has_command("guardrail", "configs", "update", "harbor-custom-config"), (
        f"Agent did not update 'harbor-custom-config'. Commands: {commands}"
    )

    # Agent should have made at least one guardrail inference call (check or chat)
    made_inference = has_command("guardrail", "check") or has_command("guardrail", "chat")
    assert made_inference, f"Agent did not make any guardrail inference call (check or chat). Commands: {commands}"

    print(f"All trajectory checks passed. Total commands: {len(commands)}")
