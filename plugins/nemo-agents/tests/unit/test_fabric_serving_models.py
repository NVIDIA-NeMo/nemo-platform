# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

import pytest
from nemo_agents_plugin.fabric.serving_models import ChatCompletionRequest
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"messages": []}, "List should have at least 1 item"),
        (
            {"messages": [{"role": "assistant", "content": "hello"}]},
            "The final chat message must have role 'user'.",
        ),
        (
            {"messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]},
            "Input should be a valid string",
        ),
    ],
)
def test_chat_completion_request_rejects_unsupported_inputs(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ChatCompletionRequest.model_validate(payload)


def test_chat_completion_request_accepts_streaming() -> None:
    request = ChatCompletionRequest.model_validate({"messages": [{"role": "user", "content": "hello"}], "stream": True})

    assert request.stream is True
