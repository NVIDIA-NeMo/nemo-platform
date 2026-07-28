# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_eval_author_plugin import model_config


@pytest.fixture(autouse=True)
def _clear_model_cache() -> None:
    model_config.get_smart_model.cache_clear()
    model_config.get_mid_model.cache_clear()
    model_config.get_fast_model.cache_clear()


def test_api_base_prefers_eval_author_over_experimentalist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://experimentalist.example/v1")
    monkeypatch.setenv("AUTHOR_API_KEY", "eval-key")

    assert model_config._api_base() == "https://eval-author.example/v1"


def test_api_base_falls_back_to_experimentalist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTHOR_API_BASE", raising=False)
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://experimentalist.example/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_KEY", "exp-key")

    assert model_config._api_base() == "https://experimentalist.example/v1"


def test_api_key_accepts_inference_key_on_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://inference-api.nvidia.com/v1")
    monkeypatch.delenv("AUTHOR_API_KEY", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)
    monkeypatch.setenv("INFERENCE_API_KEY", "sk-gateway")

    assert model_config._api_key() == "sk-gateway"


def test_api_key_requires_credentials_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://custom.example/v1")
    monkeypatch.delenv("AUTHOR_API_KEY", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)
    monkeypatch.delenv("INFERENCE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="AUTHOR_API_KEY"):
        model_config._api_key()


def test_bridge_author_env_fills_unset_experimentalist_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("AUTHOR_API_KEY", "eval-key")
    monkeypatch.delenv("EXPERIMENTALIST_API_BASE", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)

    model_config.bridge_author_env_to_experimentalist()

    assert (
        model_config.os.environ["EXPERIMENTALIST_API_BASE"]
        == "https://eval-author.example/v1"
    )
    assert model_config.os.environ["EXPERIMENTALIST_API_KEY"] == "eval-key"


def test_bridge_author_env_does_not_overwrite_existing_experimentalist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://experimentalist.example/v1")

    model_config.bridge_author_env_to_experimentalist()

    assert (
        model_config.os.environ["EXPERIMENTALIST_API_BASE"]
        == "https://experimentalist.example/v1"
    )
