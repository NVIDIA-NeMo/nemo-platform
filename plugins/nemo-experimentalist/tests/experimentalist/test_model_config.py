# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_experimentalist_plugin.experimentalist.components.model_config import get_mid_model, log_model_config


def test_mid_model_default_uses_openai_provider_for_gateway(monkeypatch) -> None:
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_KEY", "test-key")
    monkeypatch.delenv("EXPERIMENTALIST_MID_MODEL_NAME", raising=False)
    get_mid_model.cache_clear()

    try:
        client = get_mid_model()
    finally:
        get_mid_model.cache_clear()

    assert client.model == "openai/gcp/google/gemini-3.5-flash"
    assert "mid model:   openai/gcp/google/gemini-3.5-flash" in log_model_config()
