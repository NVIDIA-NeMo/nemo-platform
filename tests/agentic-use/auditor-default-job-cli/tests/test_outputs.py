# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Verify that the agent created an audit target and invoked a default audit via CLI.

The inference provider is pre-configured by the Dockerfile setup script.
Tests focus on the auditor workflow: target creation, config creation, audit invocation.

Tests:
- Audit target exists and references a model through the pre-configured provider
- Audit config exists
- Agent trajectory shows config discovery and audit invocation
"""

import base64
import json
import os

import pytest
from nemo_platform import NeMoPlatform
from trace_reader import get_session

WORKSPACE = "default"
TARGET_NAME = "audit-target"
CONFIG_NAME = "default"


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


# --- Audit target checks ---


def test_audit_target_exists(client: NeMoPlatform) -> None:
    """Verify the audit target was created."""
    targets = client.auditor.targets.list(workspace=WORKSPACE)
    target_names = [t["name"] for t in targets["data"]]
    assert TARGET_NAME in target_names, f"Target '{TARGET_NAME}' not found. Found: {target_names}"


def test_audit_target_model(client: NeMoPlatform) -> None:
    """Verify the audit target references the correct model."""
    target = client.auditor.targets.get(workspace=WORKSPACE, name=TARGET_NAME)
    assert target.model is not None and len(target.model) > 0, f"Target '{TARGET_NAME}' has no model configured"
    print(f"Target model: {target.model}, type: {target.type}")


# --- Audit config checks ---


def test_audit_config_exists(client: NeMoPlatform) -> None:
    """Verify the audit config was created."""
    config = client.auditor.configs.get(workspace=WORKSPACE, name=CONFIG_NAME)
    assert config.name == CONFIG_NAME, f"Expected config '{CONFIG_NAME}', got '{config.name}'"


def test_audit_config_has_probe_spec(client: NeMoPlatform) -> None:
    """Verify the audit config has probes configured."""
    config = client.auditor.configs.get(workspace=WORKSPACE, name=CONFIG_NAME)
    assert config.plugins.probe_spec, f"Config '{CONFIG_NAME}' has no probe_spec configured"
    print(f"Config probe_spec: {config.plugins.probe_spec}")


# --- Agent trajectory checks ---


def test_agent_invoked_audit() -> None:
    """Verify the agent invoked the audit with the config and target."""
    session = get_session()
    commands = session.get_bash_commands()

    has_audit_run = any(
        all(p in cmd for p in ["auditor", "audit", "run", CONFIG_NAME, TARGET_NAME]) for cmd in commands
    )

    assert has_audit_run, f"Agent never invoked auditor audit run with config and target. Commands: {commands}"


def test_agent_created_config() -> None:
    """Verify the agent created or interacted with an audit config."""
    session = get_session()
    commands = session.get_bash_commands()

    has_config_create = any(all(p in cmd for p in ["auditor", "config"]) and "create" in cmd for cmd in commands)

    has_config_list = any(all(p in cmd for p in ["auditor", "config"]) and "list" in cmd for cmd in commands)

    has_config_get = any(
        all(p in cmd for p in ["auditor", "config"]) and ("get" in cmd or "default" in cmd) for cmd in commands
    )

    assert has_config_create or has_config_list or has_config_get, (
        "Agent never created or discovered an audit config. Expected the agent to create or find the default config."
    )
