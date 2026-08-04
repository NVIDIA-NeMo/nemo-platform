# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Analyst model_config — self-contained ANALYST_* resolution."""

from collections.abc import Iterator

import pytest
from nemo_insights_plugin import model_config
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel


@pytest.fixture(autouse=True)
def _clear_analyst_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in (
        "ANALYST_API_BASE",
        "ANALYST_API_KEY",
        "ANALYST_MODEL_NAME",
        "INFERENCE_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "NEMO_DEFAULT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def test_defaults_base_and_model_require_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_API_KEY", "sk-gateway")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    assert model_config.api_base() == model_config.GATEWAY_ANTHROPIC_BASE
    assert model_config.model_name() == model_config.DEFAULT_MODEL
    with pytest.raises(ValueError, match="ANALYST_API_KEY"):
        model_config.api_key()


def test_explicit_analyst_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYST_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("ANALYST_API_KEY", "sk-analyst")
    monkeypatch.setenv("ANALYST_MODEL_NAME", "gpt-5.5")

    assert model_config.api_base() == "https://api.openai.com/v1"
    assert model_config.api_key() == "sk-analyst"
    assert model_config.model_name() == "gpt-5.5"
    assert not model_config.uses_anthropic_messages()
    model, settings = model_config.build_model_and_settings()
    assert isinstance(model, OpenAIChatModel)
    assert settings.get("anthropic_thinking") is None


def test_build_anthropic_model_on_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYST_API_KEY", "sk-analyst")
    model, settings = model_config.build_model_and_settings()
    assert isinstance(model, AnthropicModel)
    assert settings["anthropic_thinking"] == {"type": "adaptive"}


def test_log_model_config_masks_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYST_API_KEY", "sk-abcdefghijkl")
    rendered = model_config.log_model_config()
    assert "sk-abcdefghijkl" not in rendered
    assert "ijkl" in rendered


def test_does_not_bridge_nemo_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYST_API_KEY", "sk-analyst")
    monkeypatch.setenv("NEMO_DEFAULT_MODEL", "openai/openai/openai/gpt-5.5")
    assert model_config.model_name() == model_config.DEFAULT_MODEL
