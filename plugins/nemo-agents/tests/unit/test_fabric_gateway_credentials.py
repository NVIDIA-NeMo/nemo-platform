# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy

from nemo_agents_plugin.fabric.gateway_credentials import (
    PLATFORM_IGW_API_KEY_ENV,
    PLATFORM_IGW_API_KEY_PLACEHOLDER,
    bind_platform_gateway_model_credential,
    platform_gateway_credential_env,
)

_IGW_URL = "http://platform/apis/inference-gateway/v2/workspaces/default/openai/-/v1"


def test_selected_harness_model_binding_takes_precedence_over_shared_model() -> None:
    config = {
        "default_harness": "codex",
        "harnesses": {
            "codex": {
                "model": {
                    "provider": "nvidia",
                    "model": "harness-model",
                    "base_url": _IGW_URL,
                    "api_key_env": "HARNESS_API_KEY",
                }
            }
        },
        "models": {
            "default": {
                "provider": "openai",
                "model": "shared-model",
                "base_url": _IGW_URL,
                "api_key_env": "SHARED_API_KEY",
            }
        },
    }

    assert platform_gateway_credential_env(config) == {"HARNESS_API_KEY": PLATFORM_IGW_API_KEY_PLACEHOLDER}


def test_shared_model_without_key_uses_runtime_only_binding_without_mutating_config() -> None:
    config = {
        "default_harness": "codex",
        "harnesses": {"codex": {}},
        "models": {"default": {"provider": "nvidia", "model": "test-model", "base_url": _IGW_URL}},
    }
    original = copy.deepcopy(config)

    assert platform_gateway_credential_env(config) == {PLATFORM_IGW_API_KEY_ENV: PLATFORM_IGW_API_KEY_PLACEHOLDER}
    assert config == original


def test_explicit_third_party_endpoint_does_not_receive_placeholder() -> None:
    config = {
        "models": {
            "default": {
                "provider": "openai",
                "model": "gpt-test",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            }
        }
    }

    assert platform_gateway_credential_env(config) == {}


def test_translated_igw_model_receives_runtime_only_key_reference() -> None:
    model = {"provider": "nvidia", "model": "test-model", "base_url": _IGW_URL}

    resolved = bind_platform_gateway_model_credential(model)

    assert resolved["api_key_env"] == PLATFORM_IGW_API_KEY_ENV
    assert "api_key_env" not in model


def test_translated_direct_model_is_unchanged() -> None:
    model = {
        "provider": "nvidia",
        "model": "test-model",
        "base_url": "https://integrate.api.nvidia.com/v1",
    }

    assert bind_platform_gateway_model_credential(model) == model
