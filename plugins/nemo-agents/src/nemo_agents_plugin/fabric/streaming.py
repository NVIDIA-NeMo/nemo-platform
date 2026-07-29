# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenAI-compatible SSE framing for Fabric-backed streaming responses.

Server-Sent Events (SSE) stream newline-delimited HTTP frames. OpenAI Chat
Completions streams encode each JSON chunk as ``data: <json>`` and terminate
with ``data: [DONE]``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterable, AsyncIterator

from nemo_agents_plugin.fabric.serving_models import (
    ChatCompletionStreamChoice,
    ChatCompletionStreamDelta,
    ChatCompletionStreamResponse,
)


async def iter_openai_chat_completion_sse(
    *,
    completion_id: str,
    content_chunks: AsyncIterable[str],
    model: str = "unknown-model",
) -> AsyncIterator[str]:
    """Serialize assistant text deltas as OpenAI Chat Completions SSE frames."""
    yield _to_sse_frame(
        ChatCompletionStreamResponse(
            id=completion_id,
            model=model,
            choices=[
                ChatCompletionStreamChoice(
                    delta=ChatCompletionStreamDelta(role="assistant"),
                )
            ],
        )
    )

    async for content in content_chunks:
        if not content:
            continue
        yield _to_sse_frame(
            ChatCompletionStreamResponse(
                id=completion_id,
                model=model,
                choices=[
                    ChatCompletionStreamChoice(
                        delta=ChatCompletionStreamDelta(content=content),
                    )
                ],
            )
        )

    yield _to_sse_frame(
        ChatCompletionStreamResponse(
            id=completion_id,
            model=model,
            choices=[
                ChatCompletionStreamChoice(
                    delta=ChatCompletionStreamDelta(),
                    finish_reason="stop",
                )
            ],
        )
    )
    yield "data: [DONE]\n\n"


def _to_sse_frame(chunk: ChatCompletionStreamResponse) -> str:
    data = chunk.model_dump(mode="json", exclude_none=True)
    return f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
