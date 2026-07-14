# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import AsyncIterator
from typing import Any

from nemo_guardrails_plugin.streaming import (
    ChatCompletionChunkMetadata,
    build_final_chat_completion_chunk,
    build_streaming_error_response,
    chunks_to_strings,
    close_async_iterator,
    extract_delta_content,
    parse_streaming_error_token,
    strings_to_chunks,
)


async def _collect(iterator: AsyncIterator[Any]) -> list[Any]:
    return [item async for item in iterator]


class TestExtractDeltaContent:
    def test_extracts_content_from_first_choice_delta(self) -> None:
        chunk = {"choices": [{"delta": {"content": "hello"}}]}

        assert extract_delta_content(chunk) == "hello"

    def test_returns_empty_string_for_non_content_chunks(self) -> None:
        assert extract_delta_content({"choices": [{"delta": {"role": "assistant"}}]}) == ""
        assert extract_delta_content({"choices": [{"delta": {"content": None}}]}) == ""
        assert extract_delta_content({"choices": []}) == ""
        assert extract_delta_content({"usage": {"total_tokens": 1}}) == ""


class TestChunksToStrings:
    async def test_yields_only_content_tokens_and_captures_metadata(self) -> None:
        metadata = ChatCompletionChunkMetadata()

        async def chunks() -> AsyncIterator[dict[str, Any]]:
            yield {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "system_fingerprint": "fp-abc",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
            yield {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "choices": [{"index": 0, "delta": {"content": "Hel"}, "finish_reason": None}],
            }
            yield {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": None}],
            }
            yield {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }

        assert await _collect(chunks_to_strings(chunks(), metadata)) == ["Hel", "lo"]
        assert metadata.response is not None
        assert metadata.response.id == "chatcmpl-123"
        assert metadata.response.created == 123
        assert metadata.response.model == "served-model"
        assert metadata.response.system_fingerprint == "fp-abc"
        assert metadata.finish_reason == "stop"


class TestStringsToChunks:
    async def test_wraps_tokens_and_preserves_metadata(self) -> None:
        metadata = ChatCompletionChunkMetadata()
        metadata.update_from_chunk(
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "system_fingerprint": "fp-abc",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
        )

        async def tokens() -> AsyncIterator[str]:
            yield "Hel"
            yield "lo"

        chunks = await _collect(strings_to_chunks(tokens(), metadata=metadata, model="request-model"))

        assert chunks == [
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "system_fingerprint": "fp-abc",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hel"}}],
            },
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "system_fingerprint": "fp-abc",
                "choices": [{"index": 0, "delta": {"content": "lo"}}],
            },
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "system_fingerprint": "fp-abc",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
        ]

    def test_final_chunk_uses_request_model_when_metadata_is_missing(self) -> None:
        chunk = build_final_chat_completion_chunk(
            metadata=ChatCompletionChunkMetadata(),
            model="request-model",
        )

        assert chunk["model"] == "request-model"
        assert chunk["choices"] == [{"index": 0, "delta": {}, "finish_reason": "stop"}]

    def test_final_chunk_uses_upstream_finish_reason(self) -> None:
        metadata = ChatCompletionChunkMetadata()
        metadata.update_from_chunk(
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 123,
                "model": "served-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
            }
        )

        chunk = build_final_chat_completion_chunk(metadata=metadata, model="request-model")

        assert chunk["choices"] == [{"index": 0, "delta": {}, "finish_reason": "length"}]

    async def test_error_token_is_returned_without_wrapping(self) -> None:
        metadata = ChatCompletionChunkMetadata()

        async def tokens() -> AsyncIterator[str]:
            yield (
                '{"error":{"message":"Blocked by self check output rails.",'
                '"type":"guardrails_violation","param":"self check output","code":"content_blocked"}}'
            )
            yield "should not be emitted"

        chunks = await _collect(strings_to_chunks(tokens(), metadata=metadata, model="request-model"))

        assert chunks == [
            {
                "error": {
                    "message": "Blocked by self check output rails.",
                    "type": "guardrails_violation",
                    "param": "self check output",
                    "code": "content_blocked",
                }
            }
        ]


class TestParseStreamingErrorToken:
    def test_returns_error_dict_for_nemoguardrails_error_token(self) -> None:
        token = (
            '{"error":{"message":"Blocked by self check output rails.",'
            '"type":"guardrails_violation","param":"self check output","code":"content_blocked"}}'
        )

        assert parse_streaming_error_token(token) == {
            "error": {
                "message": "Blocked by self check output rails.",
                "type": "guardrails_violation",
                "param": "self check output",
                "code": "content_blocked",
            }
        }

    def test_returns_none_for_regular_tokens_and_non_error_json(self) -> None:
        assert parse_streaming_error_token("hello") is None
        assert parse_streaming_error_token('{"key": "value"}') is None
        assert parse_streaming_error_token('{"error": "not an object"}') is None


class TestBuildStreamingErrorResponse:
    def test_builds_service_compatible_streaming_error_payload(self) -> None:
        assert build_streaming_error_response(RuntimeError("Streaming failed")) == {
            "error": {
                "message": "Streaming failed",
                "type": "RuntimeError",
                "param": "",
                "code": "500",
            }
        }


class TestCloseAsyncIterator:
    async def test_closes_iterator_when_supported(self) -> None:
        closed = False

        async def generator() -> AsyncIterator[int]:
            nonlocal closed
            try:
                yield 1
            finally:
                closed = True

        iterator = generator()
        assert await iterator.__anext__() == 1

        await close_async_iterator(iterator)

        assert closed is True
