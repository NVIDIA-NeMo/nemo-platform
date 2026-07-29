# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from nemo_agents_plugin.fabric.streaming import iter_openai_chat_completion_sse


async def _content_chunks() -> AsyncIterator[str]:
    yield "hel"
    yield ""
    yield "lo"


def _event_payload(event: str) -> dict[str, object]:
    assert event.startswith("data: ")
    assert event.endswith("\n\n")
    return json.loads(event.removeprefix("data: ").removesuffix("\n\n"))


@pytest.mark.asyncio
async def test_iter_openai_chat_completion_sse_frames_content_chunks() -> None:
    events = [
        event
        async for event in iter_openai_chat_completion_sse(
            completion_id="chatcmpl-test",
            content_chunks=_content_chunks(),
            model="test-model",
        )
    ]

    assert len(events) == 5
    assert events[-1] == "data: [DONE]\n\n"

    first_chunk = _event_payload(events[0])
    assert first_chunk["id"] == "chatcmpl-test"
    assert first_chunk["object"] == "chat.completion.chunk"
    assert first_chunk["model"] == "test-model"
    assert first_chunk["choices"] == [{"index": 0, "delta": {"role": "assistant"}}]

    second_chunk = _event_payload(events[1])
    assert second_chunk["choices"] == [{"index": 0, "delta": {"content": "hel"}}]

    third_chunk = _event_payload(events[2])
    assert third_chunk["choices"] == [{"index": 0, "delta": {"content": "lo"}}]

    terminal_chunk = _event_payload(events[3])
    assert terminal_chunk["choices"] == [{"index": 0, "delta": {}, "finish_reason": "stop"}]
