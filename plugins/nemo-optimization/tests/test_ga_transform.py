# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any

import pytest
from nemo_optimization.backends.ga.transform import ModelPromptTransformer, PromptTransformError


def test_model_prompt_transformer_uses_openai_compatible_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            del exc_type, exc, traceback

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"```text\\nImproved prompt\\n```"}}]}'

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setenv("PROMPT_OPTIMIZER_API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    transformer = ModelPromptTransformer(
        payload={
            "models": {
                "prompt_optimizer": {
                    "provider": "openai",
                    "base_url": "https://example.test/v1",
                    "model": "gpt-test",
                    "api_key_env": "PROMPT_OPTIMIZER_API_KEY",
                    "settings": {"temperature": 0.2, "max_tokens": 77, "timeout_s": 12.0},
                }
            }
        },
        model_name="prompt_optimizer",
    )

    result = transformer.mutate(
        prompt_name="system_prompt",
        prompt="Base prompt.",
        purpose="Answer accurately.",
        prompt_format=None,
        feedback=None,
    )

    assert result == "Improved prompt"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["timeout"] == 12.0
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "gpt-test"
    assert captured["body"]["temperature"] == 0.2
    assert captured["body"]["max_tokens"] == 77


def test_model_prompt_transformer_rejects_secret_refs_for_direct_adapter() -> None:
    with pytest.raises(PromptTransformError, match="api_key_env, not api_key_secret"):
        ModelPromptTransformer(
            payload={
                "models": {
                    "prompt_optimizer": {
                        "provider": "openai",
                        "base_url": "https://example.test/v1",
                        "model": "gpt-test",
                        "api_key_secret": "PROMPT_OPTIMIZER_SECRET",
                    }
                }
            },
            model_name="prompt_optimizer",
        )
